"""Tests run against a real Postgres with pgvector and the real embedding model.
Only the Claude calls are faked: extraction returns the sample labels."""

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from loan_file_assistant import service
from loan_file_assistant.app import create_app
from loan_file_assistant.db import Base, create_schema
from loan_file_assistant.embeddings import FastEmbedder
from loan_file_assistant.llm import Answer, Citation, Passage
from loan_file_assistant.schema import FIELD_NAMES, LoanDocumentFields

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://lfa:lfa@127.0.0.1:5434/lfa_test"
)
SAMPLES = Path(__file__).resolve().parents[1] / "samples"
LABELS = json.loads((SAMPLES / "labels.json").read_text())


def sample_pdf(key: str) -> bytes:
    return (SAMPLES / "pdfs" / key).read_bytes()


def labeled_fields(key: str) -> LoanDocumentFields:
    label = LABELS[key]
    return LoanDocumentFields(doc_type=label["doc_type"], **{f: label.get(f) for f in FIELD_NAMES})


class FakeLLM:
    """Extraction returns the labels for a known sample PDF; answers quote the first passage."""

    def __init__(self) -> None:
        self._by_hash = {hashlib.sha256(sample_pdf(k)).hexdigest(): k for k in LABELS}
        self.extract_calls = 0
        self.last_passages: list[Passage] = []

    def extract(self, pdf: bytes, filename: str) -> LoanDocumentFields:
        self.extract_calls += 1
        return labeled_fields(self._by_hash[hashlib.sha256(pdf).hexdigest()])

    def answer(self, question: str, passages: list[Passage]) -> Answer:
        self.last_passages = passages
        top = passages[0]
        return Answer(text=f"From {top.source}.", citations=[Citation(top.source, top.title, top.text[:40])])


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    create_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def embedder():
    return FastEmbedder()


@pytest.fixture(autouse=True)
def _clean(engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE loan_file, document, chunk CASCADE"))


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(engine, embedder, llm, clock, tmp_path, monkeypatch) -> Iterator[TestClient]:
    # Seed from the fake model into a throwaway cache, never the repo's.
    original = service.seed_samples
    monkeypatch.setattr(
        service,
        "seed_samples",
        lambda db, emb, model, now: original(db, emb, model, now, cache_path=tmp_path / "extracted.json"),
    )
    app = create_app(engine=engine, embedder=embedder, llm=llm, clock=clock, daily_model_calls=50)
    with TestClient(app) as c:
        yield c
