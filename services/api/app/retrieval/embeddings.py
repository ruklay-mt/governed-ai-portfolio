"""Voyage AI embeddings (ADR 0005, ADR 0010).

Documents are embedded by `make docs-embed`; at request time only the query is embedded.
"""

from collections.abc import Sequence
from typing import Literal

from voyageai.client import Client

from app.config import Settings

# Fixed by the `vector(1024)` column in migration 0004. Changing it needs a migration and a
# re-embed (ADR 0010).
EMBEDDING_DIM = 1024
# Voyage accepts up to 1,000 texts per request; documents are far fewer, but stay safe.
BATCH_SIZE = 128

InputType = Literal["document", "query"]


class Embedder:
    """Thin wrapper so callers (and tests) depend on one small interface."""

    def __init__(self, settings: Settings) -> None:
        if settings.voyage_api_key is None or not settings.embedding_model:
            raise RuntimeError("VOYAGE_API_KEY and EMBEDDING_MODEL must be set")
        self._client = Client(
            api_key=settings.voyage_api_key.get_secret_value(), max_retries=2, timeout=20
        )
        self._model = settings.embedding_model

    def embed(self, texts: Sequence[str], input_type: InputType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            result = self._client.embed(
                list(texts[start : start + BATCH_SIZE]),
                model=self._model,
                input_type=input_type,
                output_dimension=EMBEDDING_DIM,
            )
            vectors.extend([float(x) for x in vector] for vector in result.embeddings)
        return vectors


def to_pgvector(vector: Sequence[float]) -> str:
    """Format a vector as a pgvector text literal, e.g. '[0.1,0.2]'."""
    if len(vector) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM} dimensions, got {len(vector)}")
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"
