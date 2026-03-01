"""Embedding service: calls Gemini text-embedding-004 for batch text embedding.

All calls are routed through asyncio.get_event_loop().run_in_executor so
the synchronous google-generativeai SDK does not block the event loop.
Costs are not logged here (called from EmbeddingNode which handles logging).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_EMBED_MODEL = "models/text-embedding-004"
_EMBED_DIM = 768


def _embed_batch_sync(texts: list[str], api_key: Optional[str]) -> list[list[float]]:
    """Synchronous Gemini embedding call -- run in executor to avoid blocking."""
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("google-generativeai not installed; returning zero embeddings")
        return [[0.0] * _EMBED_DIM for _ in texts]

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        logger.warning("No GEMINI_API_KEY; returning zero embeddings")
        return [[0.0] * _EMBED_DIM for _ in texts]

    genai.configure(api_key=key)
    results: list[list[float]] = []
    for text in texts:
        try:
            resp = genai.embed_content(
                model=_EMBED_MODEL,
                content=text[:8000],
                task_type="retrieval_document",
            )
            vec = resp.get("embedding", [0.0] * _EMBED_DIM)
            results.append(list(vec))
        except Exception as exc:
            logger.warning("Embedding call failed for text: %s", exc)
            results.append([0.0] * _EMBED_DIM)
    return results


async def embed_texts(
    texts: list[str],
    api_key: Optional[str] = None,
    batch_size: int = 20,
) -> list[list[float]]:
    """Embed a list of texts using Gemini text-embedding-004.

    Batches calls to stay within rate limits. Returns list of float vectors
    of length 768. Falls back to zero vectors on API failure.
    """
    if not texts:
        return []

    loop = asyncio.get_event_loop()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_result = await loop.run_in_executor(
            None, _embed_batch_sync, batch, api_key
        )
        all_embeddings.extend(batch_result)

    return all_embeddings


async def embed_query(text: str, api_key: Optional[str] = None) -> list[float]:
    """Embed a single query text with task_type=retrieval_query."""
    if not text.strip():
        return [0.0] * _EMBED_DIM

    def _query_sync() -> list[float]:
        try:
            import google.generativeai as genai  # type: ignore[import-untyped]
        except ImportError:
            return [0.0] * _EMBED_DIM
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return [0.0] * _EMBED_DIM
        genai.configure(api_key=key)
        try:
            resp = genai.embed_content(
                model=_EMBED_MODEL,
                content=text[:8000],
                task_type="retrieval_query",
            )
            return list(resp.get("embedding", [0.0] * _EMBED_DIM))
        except Exception as exc:
            logger.warning("Query embedding failed: %s", exc)
            return [0.0] * _EMBED_DIM

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _query_sync)
