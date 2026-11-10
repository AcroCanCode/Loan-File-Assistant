"""Text embeddings, computed in-process with a small open model (no API key)."""

import os
from typing import Protocol

import numpy as np

DIMENSIONS = 384
MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge models retrieve better when the query carries this instruction.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    def __init__(self) -> None:
        from fastembed import TextEmbedding

        # The Docker image downloads the model at build time into FASTEMBED_CACHE_PATH.
        self._model = TextEmbedding(MODEL_NAME, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_unit(v) for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return _unit(next(iter(self._model.embed([QUERY_PREFIX + text]))))


def _unit(vector) -> list[float]:
    v = np.asarray(vector, dtype=np.float32)
    return (v / (np.linalg.norm(v) or 1.0)).tolist()
