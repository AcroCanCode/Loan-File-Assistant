"""The HTTP API."""

import logging
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from loan_file_assistant import service
from loan_file_assistant.db import Document, LoanFile, create_schema
from loan_file_assistant.embeddings import Embedder
from loan_file_assistant.limits import DailyBudget, RateLimiter, rate_limited, spend_model_call
from loan_file_assistant.llm import LLM, Declined
from loan_file_assistant.pdf import InvalidPdf
from loan_file_assistant.schema import Flag, LoanDocumentFields, loan_file_flags

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_DOCS_PER_FILE = 8
MAX_LIVE_UPLOADS = 300

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session, session.begin():
        yield session


Db = Annotated[Session, Depends(get_db, scope="function")]


class LoanFileSummary(BaseModel):
    id: uuid.UUID
    name: str
    document_count: int


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    page_count: int
    fields: LoanDocumentFields


class LoanFileOut(BaseModel):
    id: uuid.UUID
    name: str
    is_sample: bool
    expires_at: datetime | None
    documents: list[DocumentOut]
    flags: list[Flag]


class CreateLoanFile(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = (
        "My loan file"
    )


class Ask(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class CitationOut(BaseModel):
    source: str
    title: str
    cited_text: str


class AnswerOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    # The retrieved passages the answer was drawn from, closest first.
    sources_searched: list[str]


def create_app(
    *,
    engine: Engine,
    embedder: Embedder,
    llm: LLM,
    clock: Clock = system_clock,
    cors_origins: Sequence[str] = (),
    daily_model_calls: int = 400,
    seed: bool = True,
    seed_in_background: bool = False,
) -> FastAPI:
    def seed_samples() -> None:
        with Session(engine) as db, db.begin():
            service.seed_samples(db, embedder, llm, clock())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_schema(engine)
        if seed and seed_in_background:
            # A fresh database's first start reads every sample with the model, which
            # takes minutes; serve requests meanwhile (samples appear when it's done).
            threading.Thread(target=_log_errors(seed_samples), name="seed-samples", daemon=True).start()
        elif seed:
            seed_samples()
        yield

    app = FastAPI(title="Loan File Assistant API", lifespan=lifespan)
    app.state.engine = engine
    app.state.embedder = embedder
    app.state.llm = llm
    app.state.clock = clock
    app.state.rate_limiter = RateLimiter()
    app.state.daily_budget = DailyBudget(daily_model_calls)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    def loan_file_or_404(db: Session, loan_file_id: uuid.UUID) -> LoanFile:
        loan_file = db.get(LoanFile, loan_file_id)
        if loan_file is None or (loan_file.expires_at is not None and loan_file.expires_at <= clock()):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Loan file not found")
        return loan_file

    def loan_file_out(db: Session, loan_file: LoanFile) -> LoanFileOut:
        docs = db.scalars(
            select(Document).where(Document.loan_file_id == loan_file.id).order_by(Document.filename)
        ).all()
        fields = [LoanDocumentFields.model_validate(d.fields) for d in docs]
        return LoanFileOut(
            id=loan_file.id,
            name=loan_file.name,
            is_sample=loan_file.is_sample,
            expires_at=loan_file.expires_at,
            documents=[
                DocumentOut(id=d.id, filename=d.filename, page_count=d.page_count, fields=f)
                for d, f in zip(docs, fields, strict=True)
            ],
            flags=loan_file_flags(fields),
        )

    @app.get("/health")
    def health(db: Db) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/loan-files/samples")
    def samples(db: Db) -> list[LoanFileSummary]:
        rows = db.execute(
            select(LoanFile.id, LoanFile.name, func.count(Document.id))
            .outerjoin(Document, Document.loan_file_id == LoanFile.id)
            .where(LoanFile.is_sample)
            .group_by(LoanFile.id)
            .order_by(LoanFile.name)
        ).all()
        return [LoanFileSummary(id=i, name=n, document_count=c) for i, n, c in rows]

    @app.post(
        "/loan-files",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(rate_limited("create", 10, timedelta(hours=1)))],
    )
    def create_loan_file(db: Db, body: CreateLoanFile | None = None) -> LoanFileOut:
        """A private loan file for uploads. Anyone with its id can use it; it's deleted after a day."""
        now = clock()
        service.delete_expired(db, now)
        if service.live_uploads(db, now) >= MAX_LIVE_UPLOADS:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The demo is busy. Please try again later.")
        loan_file = LoanFile(
            name=(body or CreateLoanFile()).name, created_at=now, expires_at=now + service.UPLOAD_LIFETIME
        )
        db.add(loan_file)
        db.flush()
        return loan_file_out(db, loan_file)

    @app.get("/loan-files/{loan_file_id}")
    def get_loan_file(loan_file_id: uuid.UUID, db: Db) -> LoanFileOut:
        return loan_file_out(db, loan_file_or_404(db, loan_file_id))

    @app.post(
        "/loan-files/{loan_file_id}/documents",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(rate_limited("upload", 20, timedelta(hours=1)))],
    )
    def upload(loan_file_id: uuid.UUID, file: UploadFile, request: Request, db: Db) -> DocumentOut:
        loan_file = loan_file_or_404(db, loan_file_id)
        if loan_file.is_sample:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sample loan files can't be changed")
        count = db.scalar(select(func.count()).where(Document.loan_file_id == loan_file.id)) or 0
        if count >= MAX_DOCS_PER_FILE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"A loan file holds at most {MAX_DOCS_PER_FILE} documents")
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "PDFs are limited to 5 MB")
        if not data.startswith(b"%PDF"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are accepted")
        try:
            service.check_pages(data)
        except InvalidPdf as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
        except service.TooManyPages as e:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from None
        spend_model_call(request)
        filename = (file.filename or "document.pdf").rsplit("/", 1)[-1][:200]
        fields = _call_model(lambda: request.app.state.llm.extract(data, filename))
        doc = service.ingest(db, embedder, loan_file, filename, data, fields, clock())
        return DocumentOut(id=doc.id, filename=doc.filename, page_count=doc.page_count, fields=fields)

    @app.post(
        "/loan-files/{loan_file_id}/ask",
        dependencies=[Depends(rate_limited("ask", 30, timedelta(hours=1)))],
    )
    def ask(loan_file_id: uuid.UUID, body: Ask, request: Request, db: Db) -> AnswerOut:
        loan_file = loan_file_or_404(db, loan_file_id)
        passages = service.retrieve(db, embedder, loan_file.id, body.question)
        if not passages:
            raise HTTPException(status.HTTP_409_CONFLICT, "Add a document to this loan file first")
        spend_model_call(request)
        answer = _call_model(lambda: request.app.state.llm.answer(body.question, passages))
        return AnswerOut(
            answer=answer.text,
            citations=[CitationOut(source=c.source, title=c.title, cited_text=c.cited_text) for c in answer.citations],
            sources_searched=[p.source for p in passages],
        )

    return app


def _log_errors(fn):
    def run() -> None:
        try:
            fn()
        except Exception:
            logging.getLogger(__name__).exception("Seeding the sample loan files failed")

    return run


def _call_model(call):
    try:
        return call()
    except Declined:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The model declined this request") from None
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The model is busy. Please try again.") from None
    except anthropic.APIStatusError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The model request failed") from None
