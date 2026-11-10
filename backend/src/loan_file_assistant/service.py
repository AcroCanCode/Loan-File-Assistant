"""Ingesting documents, retrieving passages, and seeding the sample loan files."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from loan_file_assistant.db import Chunk, Document, LoanFile
from loan_file_assistant.embeddings import Embedder
from loan_file_assistant.llm import LLM, Passage
from loan_file_assistant.pdf import chunk_pages, page_texts
from loan_file_assistant.schema import LoanDocumentFields

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
SAMPLE_NAMES = {
    "L1": "1407 Pecan Hollow Dr (fix and flip)",
    "L2": "902 Larkspur Ct (three draws)",
    "L3": "55 Cedar Bend Ln (second-story addition)",
    "L4": "3318 Willow Run (light rehab)",
}
UPLOAD_LIFETIME = timedelta(hours=24)
MAX_PAGES = 15
TOP_K = 6


class TooManyPages(ValueError):
    pass


def ingest(
    db: Session,
    embedder: Embedder,
    loan_file: LoanFile,
    filename: str,
    data: bytes,
    fields: LoanDocumentFields,
    now: datetime,
) -> Document:
    """Store a document with its extracted fields, and its chunks with their embeddings."""
    pages = page_texts(data)
    chunks = chunk_pages(pages)
    vectors = embedder.embed_documents([c.text for c in chunks]) if chunks else []
    doc = Document(
        loan_file_id=loan_file.id,
        filename=filename,
        page_count=len(pages),
        fields=fields.model_dump(mode="json"),
        created_at=now,
    )
    db.add(doc)
    db.flush()
    db.add_all(
        Chunk(document_id=doc.id, page=c.page, position=c.index, text=c.text, embedding=v)
        for c, v in zip(chunks, vectors, strict=True)
    )
    return doc


def check_pages(data: bytes) -> None:
    if len(page_texts(data)) > MAX_PAGES:
        raise TooManyPages(f"PDFs are limited to {MAX_PAGES} pages")


def retrieve(
    db: Session, embedder: Embedder, loan_file_id: uuid.UUID, question: str, k: int = TOP_K
) -> list[Passage]:
    """The k chunks of this loan file closest to the question, by cosine distance."""
    query = embedder.embed_query(question)
    rows = db.execute(
        select(Chunk.text, Chunk.page, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.loan_file_id == loan_file_id)
        .order_by(Chunk.embedding.cosine_distance(query))
        .limit(k)
    ).all()
    return [
        Passage(source=f"{filename} p.{page}", title=_title(filename), text=text)
        for text, page, filename in rows
    ]


def _title(filename: str) -> str:
    return filename.removesuffix(".pdf").replace("_", " ").capitalize()


def delete_expired(db: Session, now: datetime) -> None:
    db.execute(delete(LoanFile).where(LoanFile.expires_at <= now))


def live_uploads(db: Session, now: datetime) -> int:
    return db.scalar(select(func.count()).where(LoanFile.expires_at > now)) or 0


def seed_samples(
    db: Session,
    embedder: Embedder,
    llm: LLM | None,
    now: datetime,
    cache_path: Path = SAMPLES_DIR / "extracted.json",
) -> int:
    """Load the sample loan files once. Uses samples/extracted.json when present, so a
    fresh database costs no API calls; otherwise extracts with the model and saves it."""
    if db.scalar(select(func.count()).where(LoanFile.is_sample)):
        return 0
    cache: dict = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    added = 0
    for loan_id, name in SAMPLE_NAMES.items():
        loan_file = LoanFile(name=name, is_sample=True, created_at=now)
        db.add(loan_file)
        db.flush()
        for pdf in sorted((SAMPLES_DIR / "pdfs" / loan_id).glob("*.pdf")):
            key = f"{loan_id}/{pdf.name}"
            data = pdf.read_bytes()
            if key in cache:
                fields = LoanDocumentFields.model_validate(cache[key])
            elif llm is not None:
                fields = llm.extract(data, pdf.name)
                cache[key] = fields.model_dump(mode="json")
            else:
                raise RuntimeError(f"No cached extraction for {key} and no model to extract it")
            ingest(db, embedder, loan_file, pdf.name, data, fields, now)
            added += 1
    try:
        cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass  # a read-only deploy just extracts again on a fresh database
    return added
