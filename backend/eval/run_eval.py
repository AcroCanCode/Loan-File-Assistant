"""Measures the deployed app against the labeled sample documents.

    uv run python eval/run_eval.py https://<api host>

It uploads each sample PDF to a fresh private loan file (so every document is
extracted by the live model, not read from a cache), then asks the questions in
eval/questions.json. It scores:

- Field accuracy: every extracted field against the labels, including fields
  that should be empty (null). Numbers must match exactly.
- Document type accuracy.
- Retrieval hit rate: the passage holding the answer is among those retrieved.
- Answer accuracy: the answer contains the expected value.

Writes eval/results.json and prints a summary. Costs about 40 model calls.
"""

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LABELS = json.loads((ROOT / "samples" / "labels.json").read_text())
QUESTIONS = json.loads((ROOT / "eval" / "questions.json").read_text())
FIELDS = [
    "borrower_name", "property_address", "purchase_price", "loan_amount", "interest_rate_pct",
    "term_months", "origination_points", "as_is_value", "after_repair_value",
    "rehab_budget_total", "draw_number", "draw_amount_requested",
]


def same(expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) < 0.005
    norm = lambda s: " ".join(str(s).lower().replace(",", " ").replace(".", " ").split())
    return norm(expected) == norm(actual)


def main(base: str) -> None:
    client = httpx.Client(base_url=base.rstrip("/"), timeout=180)
    results: dict = {"documents": [], "questions": []}
    loan_files: dict[str, str] = {}

    for key in sorted(LABELS):
        loan = LABELS[key]["loan"]
        if loan not in loan_files:
            loan_files[loan] = client.post("/loan-files", json={"name": f"Eval {loan}"}).raise_for_status().json()["id"]
        pdf = (ROOT / "samples" / "pdfs" / key).read_bytes()
        started = time.monotonic()
        response = client.post(
            f"/loan-files/{loan_files[loan]}/documents",
            files={"file": (key.split("/")[1], pdf, "application/pdf")},
        ).raise_for_status()
        fields = response.json()["fields"]
        label = LABELS[key]
        misses = {f: {"expected": label.get(f), "actual": fields.get(f)} for f in FIELDS if not same(label.get(f), fields.get(f))}
        results["documents"].append({
            "doc": key,
            "doc_type_ok": fields["doc_type"] == label["doc_type"],
            "fields_correct": len(FIELDS) - len(misses),
            "misses": misses,
            "seconds": round(time.monotonic() - started, 1),
        })
        print(f"{key}: {len(FIELDS) - len(misses)}/{len(FIELDS)}" + (f"  misses: {list(misses)}" if misses else ""))

    for q in QUESTIONS:
        body = client.post(f"/loan-files/{loan_files[q['loan']]}/ask", json={"question": q["question"]}).raise_for_status().json()
        retrieved = [s.split(" p.")[0] for s in body["sources_searched"]]
        answer_ok = all(e.lower() in body["answer"].lower() for e in q["expect"])
        results["questions"].append({
            **q,
            "retrieval_hit": q["source"] in retrieved,
            "rank": retrieved.index(q["source"]) + 1 if q["source"] in retrieved else None,
            "answer_ok": answer_ok,
            "cited": bool(body["citations"]),
            "answer": body["answer"],
        })
        print(f"[{q['loan']}] {q['question']}  retrieval={'hit' if q['source'] in retrieved else 'MISS'}  answer={'ok' if answer_ok else 'WRONG'}")

    docs, qs = results["documents"], results["questions"]
    total_fields = len(docs) * len(FIELDS)
    summary = {
        "documents": len(docs),
        "field_accuracy_pct": round(100 * sum(d["fields_correct"] for d in docs) / total_fields, 1),
        "fields_scored": total_fields,
        "doc_type_accuracy_pct": round(100 * sum(d["doc_type_ok"] for d in docs) / len(docs), 1),
        "questions": len(qs),
        "retrieval_hit_rate_pct": round(100 * sum(q["retrieval_hit"] for q in qs) / len(qs), 1),
        "answer_accuracy_pct": round(100 * sum(q["answer_ok"] for q in qs) / len(qs), 1),
        "answers_with_citations_pct": round(100 * sum(q["cited"] for q in qs) / len(qs), 1),
    }
    results["summary"] = summary
    (ROOT / "eval" / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
