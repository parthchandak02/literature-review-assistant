"""Embedding service: uses PydanticAI Embedder (Gemini) for batch text embedding.

Replaces the previous google-generativeai direct SDK calls with the
pydantic_ai.embeddings.Embedder abstraction, which is natively async and
consistent with the rest of the PydanticAI agent stack.

Default model and dimension are defined in config/settings.yaml under rag.embed_model
and rag.embed_dim. Pass model/dim explicitly when calling from orchestration so
the live settings are always used rather than the module-level fallback.

Auth: GEMINI_API_KEY env var -- read automatically by PydanticAI, no manual wiring.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai.embeddings import Embedder

from src.llm.model_fallback import get_fallback_model

logger = logging.getLogger(__name__)

# Module-level fallback values -- used only when the caller does not pass
# explicit model/dim (e.g. standalone scripts). Orchestration always reads
# from config/settings.yaml via RagConfig and passes values explicitly.
_DEFAULT_EMBED_MODEL = ""
_DEFAULT_EMBED_DIM = 768

# Cache embedder instances by (model, dim) so we never recreate needlessly
# within a single process lifetime.
_embedder_cache: dict[tuple[str, int], Embedder] = {}


def _resolve_embed_model(model: str) -> str:
    if model:
        return model
    # Keep model resolution centralized in settings.yaml.
    return get_fallback_model("lite")


def _get_embedder(model: str = _DEFAULT_EMBED_MODEL, dim: int = _DEFAULT_EMBED_DIM) -> Embedder:
    """Return a cached Embedder for the given model and output dimension."""
    model = _resolve_embed_model(model)
    key = (model, dim)
    if key not in _embedder_cache:
        _embedder_cache[key] = Embedder(model, settings={"dimensions": dim})
    return _embedder_cache[key]


async def embed_texts(
    texts: list[str],
    batch_size: int = 20,
    model: str = _DEFAULT_EMBED_MODEL,
    dim: int = _DEFAULT_EMBED_DIM,
    concurrency: int = 4,
) -> list[list[float]]:
    """Embed a list of documents using PydanticAI Embedder.

    Sends up to ``concurrency`` batches to the embedding API simultaneously to
    reduce wall-clock time. Order is preserved by collecting (batch_idx, vecs)
    tuples and sorting before flattening. Falls back to zero vectors on API
    failure so the workflow never hard-crashes during the embedding phase.
    """
    if not texts:
        return []

    embedder = _get_embedder(model, dim)
    batches = [(i // batch_size, texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
    sem = asyncio.Semaphore(concurrency)

    async def _embed_batch(batch_idx: int, batch: list[str]) -> tuple[int, list[list[float]]]:
        async with sem:
            try:
                result = await embedder.embed_documents(batch)
                return batch_idx, [list(vec) for vec in result.embeddings]
            except Exception as exc:
                start = batch_idx * batch_size
                logger.warning("Embedding batch [%d:%d] failed: %s", start, start + len(batch), exc)
                return batch_idx, [[0.0] * dim for _ in batch]

    gathered = await asyncio.gather(*[_embed_batch(idx, b) for idx, b in batches])
    # Sort by batch_idx to restore original text order
    all_embeddings: list[list[float]] = []
    for _, vecs in sorted(gathered, key=lambda t: t[0]):
        all_embeddings.extend(vecs)
    return all_embeddings


async def embed_query(
    text: str,
    model: str = _DEFAULT_EMBED_MODEL,
    dim: int = _DEFAULT_EMBED_DIM,
) -> list[float]:
    """Embed a single query string for similarity search.

    Returns a float vector of length ``dim``, or a zero vector on failure.
    """
    if not text.strip():
        return [0.0] * dim

    embedder = _get_embedder(model, dim)
    try:
        result = await embedder.embed_query(text[:8000])
        return list(result.embeddings[0])
    except Exception as exc:
        logger.warning("Query embedding failed: %s", exc)
        return [0.0] * dim
