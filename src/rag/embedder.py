"""Embedding service: uses PydanticAI Embedder (Gemini) for batch text embedding.

Replaces the previous google-generativeai direct SDK calls with the
pydantic_ai.embeddings.Embedder abstraction, which is natively async and
consistent with the rest of the PydanticAI agent stack.

Model: google-gla:text-embedding-004 (768-dim, matching paper_chunks_meta schema).
Auth: GEMINI_API_KEY env var -- read automatically by PydanticAI, no manual wiring.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic_ai.embeddings import Embedder

logger = logging.getLogger(__name__)

_EMBED_MODEL = "google-gla:text-embedding-004"
_EMBED_DIM = 768

_embedder: Optional[Embedder] = None


def _get_embedder() -> Embedder:
    """Return a lazily constructed singleton Embedder."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder(_EMBED_MODEL)
    return _embedder


async def embed_texts(
    texts: list[str],
    api_key: Optional[str] = None,  # kept for backward compat; PydanticAI reads GEMINI_API_KEY
    batch_size: int = 20,
) -> list[list[float]]:
    """Embed a list of documents using PydanticAI Embedder (Gemini text-embedding-004).

    Batches calls to stay within rate limits. Returns a list of 768-dim float
    vectors. Falls back to zero vectors on API failure so the workflow never
    hard-crashes during the embedding phase.
    """
    if not texts:
        return []

    embedder = _get_embedder()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            result = await embedder.embed_documents(batch)
            all_embeddings.extend([list(vec) for vec in result.embeddings])
        except Exception as exc:
            logger.warning("Embedding batch [%d:%d] failed: %s", i, i + batch_size, exc)
            all_embeddings.extend([[0.0] * _EMBED_DIM for _ in batch])

    return all_embeddings


async def embed_query(
    text: str,
    api_key: Optional[str] = None,  # kept for backward compat
) -> list[float]:
    """Embed a single query string for similarity search (input_type=query).

    Returns a 768-dim float vector, or a zero vector on failure.
    """
    if not text.strip():
        return [0.0] * _EMBED_DIM

    embedder = _get_embedder()
    try:
        result = await embedder.embed_query(text[:8000])
        return list(result.embeddings[0])
    except Exception as exc:
        logger.warning("Query embedding failed: %s", exc)
        return [0.0] * _EMBED_DIM
