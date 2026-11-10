"""Reading PDFs and splitting their text into chunks for retrieval."""

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# The repeated footer on every sample page; it adds nothing to retrieval.
_BOILERPLATE = ("SAMPLE DOCUMENT - FICTIONAL DATA - NOT A REAL LOAN",)

CHUNK_CHARS = 900
OVERLAP_CHARS = 150


class InvalidPdf(ValueError):
    pass


@dataclass(frozen=True)
class Chunk:
    page: int  # 1-based
    index: int  # position within the document
    text: str


def page_texts(data: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as e:
        raise InvalidPdf("Not a readable PDF") from e
    return [_clean(p) for p in pages]


def _clean(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and line not in _BOILERPLATE and not line.startswith("Page ")]
    return "\n".join(lines)


def chunk_pages(pages: list[str]) -> list[Chunk]:
    """Split each page into overlapping windows, breaking on line ends where possible."""
    chunks: list[Chunk] = []
    for page_number, text in enumerate(pages, start=1):
        start = 0
        while start < len(text):
            end = min(start + CHUNK_CHARS, len(text))
            if end < len(text):
                newline = text.rfind("\n", start + CHUNK_CHARS // 2, end)
                if newline != -1:
                    end = newline
            piece = text[start:end].strip()
            if piece:
                chunks.append(Chunk(page=page_number, index=len(chunks), text=piece))
            if end >= len(text):
                break
            start = max(end - OVERLAP_CHARS, start + 1)
    return chunks
