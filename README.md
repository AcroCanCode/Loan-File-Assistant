# Loan File Assistant

Reads the documents in a real estate bridge loan file (term sheets, appraisals, rehab budgets, construction draw requests), pulls out the terms, flags underwriting issues, and answers questions with citations to the page the answer came from.

**Live demo: [loan-file-assistant.vercel.app](https://loan-file-assistant.vercel.app)** · Every document in it is fictional sample data. The API sleeps when idle, so the first load can take about a minute.

## What it does

- **Extraction.** Claude (Haiku 5.5 in the demo) reads each PDF and returns typed fields (borrower, property, loan amount, rate, term, as-is value, after-repair value, rehab budget, draw amounts), validated against a Pydantic schema with structured outputs.
- **Underwriting flags.** Plain code checks the extracted numbers across the whole loan file: loan-to-ARV over 70%, loan-to-cost over 90%, draws exceeding the rehab budget, mismatched property addresses, missing documents. Being code rather than a model makes them repeatable and explainable.
- **Q&A with citations (RAG).** Documents are split into chunks, embedded with a local open model (`bge-small-en-v1.5`), and stored in Postgres with pgvector. A question retrieves the six closest passages from that loan file only, and Claude answers from them with citations.
- **Private uploads.** Visitors can upload their own PDFs to a private loan file that is deleted after 24 hours.

## How well it works

`backend/eval/run_eval.py` runs against the deployed API: it uploads all 20 sample PDFs, so each one is read live, and asks 20 labeled questions. Results from November 10, 2026 (full output in `backend/eval/results.json`):

| Measure | Claude Haiku 5.5 | Claude Opus 5.5 |
|---|---|---|
| Field extraction accuracy (240 fields, nulls included) | **98.3%** | 98.3% |
| Document type accuracy | **100%** | 100% |
| Retrieval: answer passage among those retrieved | **100%** (20/20) | |
| Answers containing the expected value | **95%** (19/20) | |
| Answers with citations | **100%** | |
| Median time to read a document | 6.4 s | |

The demo runs on Haiku 5.5: it matched Opus 5.5 on extraction at about 1/40 of the cost. The Opus column scores the sample documents Opus read when the database was first set up.

What the misses were:
- All four field misses are the same judgment call, made by both models: each term sheet lists a "rehab holdback", which the labels count as the rehab budget and the models leave empty. That's a labeling ambiguity rather than a misread number.
- The one answer marked wrong said "twelve months" where the grader looked for "12 months". The grader matches text exactly, so it's reported as a miss.

The samples include deliberate traps: comparable sale prices next to the subject's value, "previously disbursed" totals next to the current draw amount, and an unapproved change order inside a draw.

## Architecture

```
Next.js (Vercel)  ──▶  FastAPI (Render)  ──▶  Claude API (extraction, answers)
                          │
                          ├─▶ fastembed, in-process (embeddings, no API key)
                          └─▶ Postgres + pgvector (Supabase)
```

| Path | What's there |
|---|---|
| `backend/src/loan_file_assistant/llm.py` | The two Claude calls and their prompts |
| `backend/src/loan_file_assistant/schema.py` | The extraction schema and the underwriting checks |
| `backend/src/loan_file_assistant/service.py` | Ingesting, chunking, retrieval, seeding the samples |
| `backend/samples/generate.py` | Builds the fictional PDFs and their ground-truth labels |
| `backend/eval/` | The eval script and questions |
| `frontend/app/loan-assistant.tsx` | The UI |

## Safety and cost guardrails

- Sample data only, labeled as fictional on every page; visitors are told not to upload real borrower information.
- Uploads are capped at 5 MB and 15 pages, 8 documents per loan file, and deleted after 24 hours.
- Per-address rate limits, a daily cap on model calls, and a spend limit on the API key.
- If a request is declined by Claude's safety classifiers, a server-side fallback model retries it; a final decline returns a clear error.
- Retrieval is scoped to one loan file, so a question can never pull passages from someone else's upload.

## Run it locally

You need Docker, [uv](https://docs.astral.sh/uv/), Node 22, and an Anthropic API key.

```sh
docker run -d --name lfa-db -e POSTGRES_USER=lfa -e POSTGRES_PASSWORD=lfa -e POSTGRES_DB=lfa \
  -p 5434:5432 pgvector/pgvector:pg16

cd backend
uv sync
ANTHROPIC_API_KEY=... CORS_ORIGINS=http://localhost:3000 uv run loan-file-assistant

cd ../frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

The first start extracts the 20 sample documents with Claude (about 20 calls) and caches the results in `backend/samples/extracted.json`.

Tests run against a real Postgres and the real embedding model, with Claude faked:

```sh
docker exec lfa-db psql -U lfa -c "CREATE DATABASE lfa_test"
cd backend && uv run pytest
```

## Built with

Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL + pgvector, fastembed, the Anthropic Python SDK, Next.js, TypeScript, Tailwind CSS. Built with Claude Code.
