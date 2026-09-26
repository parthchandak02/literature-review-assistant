"""Embedding service: uses PydanticAI Embedder for batch text embedding.

Default model and dimension are defined in config/settings.yaml under rag.embed_model
and rag.embed_dim. Pass model/dim explicitly when calling from orchestration so
the live settings are always used rather than the module-level fallback.

Local sentence-transformers models require no API key; cloud embedders use their
provider env vars automatically via PydanticAI.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence

from src.llm.factory import get_embedder
from src.llm.model_fallback import get_fallback_model

logger = logging.getLogger(__name__)

# Module-level fallback values -- used only when the caller does not pass
# explicit model/dim (e.g. standalone scripts). Orchestration always reads
# from config/settings.yaml via RagConfig and passes values explicitly.
_DEFAULT_EMBED_MODEL = ""
_DEFAULT_EMBED_DIM = 768


def _resolve_embed_model(model: str) -> str:
    if model:
        return model
    # Keep model resolution centralized in settings.yaml.
    return get_fallback_model("lite")


def is_null_embedding(vec: Sequence[float] | None) -> bool:
    """True when ``vec`` is missing, empty, or all zeros (unusable for cosine retrieval)."""
    return not vec or not any(vec)


def embedding_json_is_null(raw: str | bytes | None) -> bool:
    """True when a persisted ``paper_chunks_meta.embedding`` JSON value is unusable."""
    if not raw:
        return True
    try:
        vec = json.loads(raw)
    except (TypeError, ValueError):
        return True
    if not isinstance(vec, list):
        return True
    try:
        return is_null_embedding([float(v) for v in vec])
    except (TypeError, ValueError):
        return True


async def embed_texts(
    texts: list[str],
    batch_size: int = 20,
    model: str = _DEFAULT_EMBED_MODEL,
    dim: int = _DEFAULT_EMBED_DIM,
    concurrency: int = 4,
    max_attempts: int = 3,
    retry_base_delay_s: float = 1.0,
) -> list[list[float] | None]:
    """Embed a list of documents using PydanticAI Embedder.

    Sends up to ``concurrency`` batches to the embedding API simultaneously to
    reduce wall-clock time. Output order and length always match ``texts``.

    Each failed batch is retried up to ``max_attempts`` times with exponential
    backoff. Texts whose batch still fails, or whose returned vector is empty or
    all zeros, are returned as ``None``; callers must not persist them.
    """
    if not texts:
        return []

    embedder = get_embedder(_resolve_embed_model(model), dim)
    batches = [(i // batch_size, texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
    sem = asyncio.Semaphore(concurrency)
    attempts = max(1, max_attempts)

    async def _embed_batch(batch_idx: int, batch: list[str]) -> tuple[int, list[list[float] | None]]:
        start = batch_idx * batch_size
        async with sem:
            for attempt in range(1, attempts + 1):
                try:
                    result = await embedder.embed_documents(batch)
                    vecs = [list(vec) for vec in result.embeddings]
                    if len(vecs) != len(batch):
                        raise ValueError(f"embedder returned {len(vecs)} vectors for {len(batch)} texts")
                    return batch_idx, [None if is_null_embedding(v) else v for v in vecs]
                except Exception as exc:
                    if attempt >= attempts:
                        logger.warning(
                            "Embedding batch [%d:%d] failed after %d attempts: %s",
                            start,
                            start + len(batch),
                            attempts,
                            exc,
                        )
                        break
                    logger.info(
                        "Embedding batch [%d:%d] attempt %d/%d failed: %s; retrying",
                        start,
                        start + len(batch),
                        attempt,
                        attempts,
                        exc,
                    )
                    await asyncio.sleep(retry_base_delay_s * (2 ** (attempt - 1)))
        return batch_idx, [None for _ in batch]

    gathered = await asyncio.gather(*[_embed_batch(idx, b) for idx, b in batches])
    all_embeddings: list[list[float] | None] = []
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

    embedder = get_embedder(_resolve_embed_model(model), dim)
    try:
        result = await embedder.embed_query(text[:8000])
        return list(result.embeddings[0])
    except Exception as exc:
        logger.warning("Query embedding failed: %s", exc)
        return [0.0] * dim
