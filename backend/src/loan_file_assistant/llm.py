"""The two Claude calls: extract fields from a PDF, and answer a question from retrieved passages."""

import base64
import os
from dataclasses import dataclass
from typing import Protocol

import anthropic

from loan_file_assistant.schema import LoanDocumentFields

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# On these models, a request declined by a safety classifier is retried on a fallback
# model inside the same call. Other models (Haiku 5.5 among them) don't offer it.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MODELS_WITH_FALLBACK = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

EXTRACT_SYSTEM = """You extract fields from documents in a real estate bridge loan file \
(term sheets, appraisals, rehab budgets, construction draw requests).

Report only what the document states. Use null for any field it doesn't give; never \
compute or infer a value from other numbers. Dollar amounts are whole dollars as integers.

Easy mistakes to avoid:
- borrower_name is the borrowing entity, not a guarantor, appraiser or lender.
- In an appraisal, comparable sale prices are not the subject's value. as_is_value is the \
current market value; after_repair_value is the value after renovation, which may be called \
"prospective market value upon completion".
- In a draw request, draw_amount_requested is this draw only, not amounts previously disbursed."""

ANSWER_SYSTEM = """You answer questions about one real estate bridge loan file, using only the \
passages provided from its documents.

Cite the passages you rely on. If the passages don't contain the answer, say what is missing \
rather than guessing. When a question needs arithmetic (totals, remaining budget, ratios), show \
the numbers you used. Keep answers short: a sentence or two, or a short list."""


class Declined(Exception):
    """The model declined the request (stop_reason "refusal"), even after fallback."""


@dataclass(frozen=True)
class Passage:
    source: str  # "<filename> p.<page>"
    title: str
    text: str


@dataclass(frozen=True)
class Citation:
    source: str
    title: str
    cited_text: str


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[Citation]


class LLM(Protocol):
    def extract(self, pdf: bytes, filename: str) -> LoanDocumentFields: ...

    def answer(self, question: str, passages: list[Passage]) -> Answer: ...


class ClaudeLLM:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL) -> None:
        self._client = client or anthropic.Anthropic()
        self._model = model
        self._fallback: dict = (
            {"betas": [FALLBACK_BETA], "fallbacks": "default"} if model in MODELS_WITH_FALLBACK else {}
        )

    def extract(self, pdf: bytes, filename: str) -> LoanDocumentFields:
        response = self._client.beta.messages.parse(
            model=self._model,
            max_tokens=4000,
            system=EXTRACT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.standard_b64encode(pdf).decode(),
                            },
                            "title": filename,
                        },
                        {"type": "text", "text": "Extract the fields from this document."},
                    ],
                }
            ],
            output_format=LoanDocumentFields,
            **self._fallback,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise Declined(f"Extraction stopped: {response.stop_reason}")
        return response.parsed_output

    def answer(self, question: str, passages: list[Passage]) -> Answer:
        content: list[dict] = [
            {
                "type": "search_result",
                "source": p.source,
                "title": p.title,
                "content": [{"type": "text", "text": p.text}],
                "citations": {"enabled": True},
            }
            for p in passages
        ]
        content.append({"type": "text", "text": question})
        response = self._client.beta.messages.create(
            model=self._model,
            max_tokens=4000,
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": content}],
            **self._fallback,
        )
        if response.stop_reason == "refusal":
            raise Declined("Answer declined")
        parts: list[str] = []
        citations: list[Citation] = []
        seen: set[tuple[str, str]] = set()
        for block in response.content:
            if block.type != "text":
                continue
            parts.append(block.text)
            for c in block.citations or []:
                if c.type == "search_result_location" and (c.source, c.cited_text) not in seen:
                    seen.add((c.source, c.cited_text))
                    citations.append(Citation(source=c.source, title=c.title or "", cited_text=c.cited_text))
        return Answer(text="".join(parts).strip(), citations=citations)
