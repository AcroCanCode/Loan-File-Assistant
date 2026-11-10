"""Loan File Assistant: extraction and Q&A over real estate bridge loan documents.

Environment:
- DATABASE_URL: Postgres with the pgvector extension available.
- ANTHROPIC_API_KEY: for the Claude calls.
- CLAUDE_MODEL: defaults to claude-opus-5-5 (the demo runs claude-haiku-5-5; see render.yaml).
- CORS_ORIGINS: comma-separated origins the frontend is served from.
- DAILY_MODEL_CALLS: cap on Claude calls per UTC day (default 400).
- PORT: defaults to 8000.
"""

import os


def _list(var: str) -> list[str]:
    return [v.strip() for v in os.environ.get(var, "").split(",") if v.strip()]


def build_app():
    from loan_file_assistant.app import create_app
    from loan_file_assistant.db import make_engine
    from loan_file_assistant.embeddings import FastEmbedder
    from loan_file_assistant.llm import ClaudeLLM

    return create_app(
        engine=make_engine(),
        embedder=FastEmbedder(),
        llm=ClaudeLLM(),
        cors_origins=_list("CORS_ORIGINS"),
        daily_model_calls=int(os.environ.get("DAILY_MODEL_CALLS", "400")),
        seed_in_background=True,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "loan_file_assistant:build_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
    )
