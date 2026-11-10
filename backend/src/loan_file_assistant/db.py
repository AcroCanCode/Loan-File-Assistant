"""Tables: loan files, their documents, and the documents' chunks with embeddings (pgvector)."""

import os
import uuid
from datetime import datetime
from typing import ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from loan_file_assistant.embeddings import DIMENSIONS


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {datetime: DateTime(timezone=True)}


class LoanFile(Base):
    __tablename__ = "loan_file"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    # Sample files are seeded at startup and shared; uploads are private to whoever
    # holds the id, and deleted once expires_at passes.
    is_sample: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime | None] = mapped_column(index=True)
    created_at: Mapped[datetime]


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    loan_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("loan_file.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    page_count: Mapped[int]
    fields: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime]


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        Index(
            "chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int]
    position: Mapped[int]
    text: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://lfa:lfa@127.0.0.1:5434/lfa")
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url.removeprefix(scheme)
    return url


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
