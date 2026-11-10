from conftest import sample_pdf


def _samples(client) -> dict[str, str]:
    return {s["name"]: s["id"] for s in client.get("/loan-files/samples").json()}


def _upload(client, loan_file_id: str, key: str, name: str | None = None):
    return client.post(
        f"/loan-files/{loan_file_id}/documents",
        files={"file": (name or key.split("/")[-1], sample_pdf(key), "application/pdf")},
    )


def test_the_four_sample_loan_files_are_seeded(client):
    samples = client.get("/loan-files/samples").json()

    assert len(samples) == 4
    assert sum(s["document_count"] for s in samples) == 20


def test_a_sample_loan_file_shows_its_fields_and_flags(client):
    larkspur = _samples(client)["902 Larkspur Ct (three draws)"]

    body = client.get(f"/loan-files/{larkspur}").json()

    term_sheet = next(d for d in body["documents"] if d["filename"] == "term_sheet.pdf")
    assert term_sheet["fields"]["loan_amount"] == 255_000
    codes = {f["code"] for f in body["flags"]}
    assert codes == {"draws_over_budget"}


def test_flags_catch_a_high_loan_to_arv(client):
    pecan = _samples(client)["1407 Pecan Hollow Dr (fix and flip)"]

    codes = {f["code"] for f in client.get(f"/loan-files/{pecan}").json()["flags"]}

    assert codes == {"arv_ltv_high"}


def test_a_clean_loan_file_has_no_flags(client):
    willow = _samples(client)["3318 Willow Run (light rehab)"]

    assert client.get(f"/loan-files/{willow}").json()["flags"] == []


def test_asking_retrieves_passages_from_that_loan_file_only(client, llm):
    samples = _samples(client)
    larkspur = samples["902 Larkspur Ct (three draws)"]

    answer = client.post(f"/loan-files/{larkspur}/ask", json={"question": "How much was requested in draw 3?"})

    assert answer.status_code == 200
    assert answer.json()["citations"]
    texts = " ".join(p.text for p in llm.last_passages)
    assert "Larkspur" in texts or "Bluebonnet" in texts
    assert "Pecan Hollow" not in texts and "Ridgeline" not in texts


def test_retrieval_finds_the_right_document(client, llm):
    larkspur = _samples(client)["902 Larkspur Ct (three draws)"]

    client.post(f"/loan-files/{larkspur}/ask", json={"question": "What is the after-repair value?"})

    assert llm.last_passages[0].source.startswith("appraisal.pdf")


def test_uploads_go_to_a_private_loan_file_and_are_extracted(client, llm):
    created = client.post("/loan-files", json={"name": "Test file"})
    assert created.status_code == 201
    file_id = created.json()["id"]

    uploaded = _upload(client, file_id, "L4/term_sheet.pdf")

    assert uploaded.status_code == 201
    assert uploaded.json()["fields"]["borrower_name"] == "Mesquite Street Investments LLC"
    body = client.get(f"/loan-files/{file_id}").json()
    assert [d["filename"] for d in body["documents"]] == ["term_sheet.pdf"]
    assert {f["code"] for f in body["flags"]} == {"missing_documents"}


def test_uploaded_files_expire_after_a_day(client, clock):
    file_id = client.post("/loan-files").json()["id"]
    clock.advance(hours=25)

    assert client.get(f"/loan-files/{file_id}").status_code == 404
    client.post("/loan-files")  # creating another deletes expired ones
    assert client.get(f"/loan-files/{file_id}").status_code == 404


def test_sample_loan_files_cannot_be_changed(client):
    pecan = _samples(client)["1407 Pecan Hollow Dr (fix and flip)"]

    assert _upload(client, pecan, "L4/term_sheet.pdf").status_code == 403


def test_only_pdfs_are_accepted(client):
    file_id = client.post("/loan-files").json()["id"]

    response = client.post(
        f"/loan-files/{file_id}/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 415


def test_a_loan_file_holds_at_most_eight_documents(client):
    file_id = client.post("/loan-files").json()["id"]
    keys = ["L2/term_sheet.pdf", "L2/appraisal.pdf", "L2/rehab_budget.pdf", "L2/draw_request_1.pdf",
            "L2/draw_request_2.pdf", "L2/draw_request_3.pdf", "L1/draw_request_1.pdf", "L1/draw_request_2.pdf"]
    for key in keys:
        assert _upload(client, file_id, key).status_code == 201

    assert _upload(client, file_id, "L3/term_sheet.pdf").status_code == 409


def test_asking_an_empty_loan_file_says_to_add_a_document(client, llm):
    file_id = client.post("/loan-files").json()["id"]

    response = client.post(f"/loan-files/{file_id}/ask", json={"question": "What is the loan amount?"})

    assert response.status_code == 409


def test_an_unknown_loan_file_is_not_found(client):
    assert client.get("/loan-files/00000000-0000-0000-0000-000000000000").status_code == 404


def test_asking_is_rate_limited(client):
    pecan = _samples(client)["1407 Pecan Hollow Dr (fix and flip)"]
    for _ in range(30):
        assert client.post(f"/loan-files/{pecan}/ask", json={"question": "Loan amount?"}).status_code == 200

    assert client.post(f"/loan-files/{pecan}/ask", json={"question": "Loan amount?"}).status_code == 429


def test_model_calls_stop_at_the_daily_cap(engine, embedder, llm, clock, tmp_path):
    from fastapi.testclient import TestClient

    from loan_file_assistant.app import create_app

    app = create_app(engine=engine, embedder=embedder, llm=llm, clock=clock, daily_model_calls=1, seed=False)
    with TestClient(app) as c:
        file_id = c.post("/loan-files").json()["id"]
        assert _upload(c, file_id, "L4/term_sheet.pdf").status_code == 201

        assert c.post(f"/loan-files/{file_id}/ask", json={"question": "Loan amount?"}).status_code == 503
        clock.advance(hours=13)  # past midnight UTC, before the file expires
        assert c.post(f"/loan-files/{file_id}/ask", json={"question": "Loan amount?"}).status_code == 200


def test_cors_allows_only_the_frontend(engine, embedder, llm, clock):
    from fastapi.testclient import TestClient

    from loan_file_assistant.app import create_app

    app = create_app(
        engine=engine, embedder=embedder, llm=llm, clock=clock, seed=False, cors_origins=["https://lfa.example.com"]
    )
    with TestClient(app) as c:
        ok = c.options(
            "/loan-files/samples",
            headers={"Origin": "https://lfa.example.com", "Access-Control-Request-Method": "GET"},
        )
        other = c.get("/health", headers={"Origin": "https://evil.example.com"})

    assert ok.headers["access-control-allow-origin"] == "https://lfa.example.com"
    assert "access-control-allow-origin" not in other.headers


def test_background_seeding_serves_requests_while_the_samples_load(engine, embedder, llm, clock):
    import time

    from fastapi.testclient import TestClient

    from loan_file_assistant.app import create_app

    app = create_app(engine=engine, embedder=embedder, llm=llm, clock=clock, seed_in_background=True)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        deadline = time.monotonic() + 60
        while len(c.get("/loan-files/samples").json()) < 4 and time.monotonic() < deadline:
            time.sleep(0.5)

        assert sum(s["document_count"] for s in c.get("/loan-files/samples").json()) == 20
