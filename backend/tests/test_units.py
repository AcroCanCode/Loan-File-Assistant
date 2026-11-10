from conftest import labeled_fields

from loan_file_assistant.pdf import chunk_pages
from loan_file_assistant.schema import DocType, LoanDocumentFields, loan_file_flags


def _fields(**kwargs) -> LoanDocumentFields:
    base = dict.fromkeys(LoanDocumentFields.model_fields, None)
    base.update(kwargs)
    return LoanDocumentFields(**base)


def test_chunks_cover_every_page_with_overlap():
    pages = ["a" * 50 + "\n" + "b" * 2000, "short page"]

    chunks = chunk_pages(pages)

    assert {c.page for c in chunks} == {1, 2}
    assert all(len(c.text) <= 900 for c in chunks)
    assert chunks[-1].text == "short page"
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_ltc_over_the_limit_is_flagged():
    docs = [
        _fields(doc_type=DocType.TERM_SHEET, loan_amount=95_000, purchase_price=90_000, rehab_budget_total=10_000),
        _fields(doc_type=DocType.APPRAISAL, after_repair_value=200_000),
        _fields(doc_type=DocType.REHAB_BUDGET, rehab_budget_total=10_000),
    ]

    assert {f.code for f in loan_file_flags(docs)} == {"ltc_high"}


def test_different_addresses_are_flagged_but_formatting_is_not():
    docs = [
        _fields(doc_type=DocType.TERM_SHEET, property_address="12 Oak St, Austin, TX"),
        _fields(doc_type=DocType.APPRAISAL, property_address="12 oak st. austin tx"),
        _fields(doc_type=DocType.REHAB_BUDGET, property_address="14 Oak St, Austin, TX"),
    ]

    assert "address_mismatch" in {f.code for f in loan_file_flags(docs)}
    assert "address_mismatch" not in {f.code for f in loan_file_flags(docs[:2])}


def test_the_labels_parse_as_extracted_fields():
    assert labeled_fields("L2/draw_request_3.pdf").draw_amount_requested == 21_500


def test_seeding_works_when_the_cache_cannot_be_written(engine, embedder, llm, tmp_path):
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from loan_file_assistant import service

    unwritable = tmp_path / "no-such-folder" / "extracted.json"

    with Session(engine) as db, db.begin():
        added = service.seed_samples(db, embedder, llm, datetime.now(UTC), cache_path=unwritable)

    assert added == 20


class _RecordingClient:
    """Stands in for anthropic.Anthropic, recording the arguments of each call."""

    def __init__(self):
        self.calls = []
        outer = self

        class _Messages:
            def parse(self, **kwargs):
                outer.calls.append(kwargs)
                raise RuntimeError("stop")

        class _Beta:
            messages = _Messages()

        self.beta = _Beta()


def test_the_refusal_fallback_is_sent_only_to_models_that_offer_it():
    import pytest

    from loan_file_assistant.llm import ClaudeLLM

    for model, expect_fallback in [("claude-opus-5-5", True), ("claude-haiku-5-5", False)]:
        client = _RecordingClient()
        with pytest.raises(RuntimeError):
            ClaudeLLM(client=client, model=model).extract(b"%PDF", "x.pdf")
        assert ("fallbacks" in client.calls[0]) is expect_fallback, model
