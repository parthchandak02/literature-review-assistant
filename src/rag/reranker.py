"""Cross-encoder reranker for RAG retrieval.

After hybrid BM25+dense retrieval produces a top-k candidate set, a cross-encoder
jointly scores each (query, chunk) pair -- capturing fine-grained token-level
relevance that bi-encoders miss.

The cross-encoder model is lazy-loaded on first use to avoid startup overhead.
The model file (~80 MB) is downloaded from HuggingFace on first call.

Reference: Nogueira & Cho (2019) "Passage Re-ranking with BERT".
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_reranker_instance: Optional["CrossEncoderReranker"] = None


class CrossEncoderReranker:
    """Thin wrapper around sentence_transformers.CrossEncoder with lazy loading.

    The underlying model is loaded once and reused for all rerank calls.
    Scoring is CPU-bound; all public methods are async and run the model in
    a thread executor to avoid blocking the event loop.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # loaded lazily on first call

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            logger.info(
                "[reranker] loading model '%s' (may download ~80 MB on first run)",
                self._model_name,
            )
            self._model = CrossEncoder(self._model_name, max_length=512)
            logger.info("[reranker] model '%s' ready", self._model_name)
        except Exception as exc:
            logger.warning("[reranker] model load failed: %s", exc)
            self._model = None

    def _score_sync(self, query: str, chunks: "list[RetrievedChunk]") -> "list[float]":
        """Synchronous scoring -- called from executor thread."""
        self._load_model()
        if self._model is None or not chunks:
            return [c.score for c in chunks]

        pairs = [(query, c.content) for c in chunks]
        t0 = time.monotonic()
        try:
            scores: list[float] = self._model.predict(pairs).tolist()
        except Exception as exc:
            logger.warning("[reranker] predict failed: %s -- using original scores", exc)
            return [c.score for c in chunks]
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[reranker] scored %d chunks in %d ms", len(chunks), elapsed_ms
        )
        return scores

    async def rerank(
        self,
        query: str,
        chunks: "list[RetrievedChunk]",
        top_k: int = 8,
    ) -> "list[RetrievedChunk]":
        """Rerank chunks by cross-encoder score and return the top_k best.

        Args:
            query: The retrieval query text (HyDE doc or research question + section).
            chunks: Candidate chunks from the hybrid retriever (top_k=20 recommended).
            top_k: Number of chunks to return after reranking.

        Returns:
            Up to top_k chunks sorted by descending cross-encoder score.
        """
        if not chunks:
            return chunks

        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(
            None, self._score_sync, query, chunks
        )

        ranked = sorted(
            zip(scores, chunks), key=lambda t: -t[0]
        )

        result = []
        for score_val, chunk in ranked[:top_k]:
            chunk.score = float(score_val)
            result.append(chunk)
        return result


def get_reranker(model_name: str = _DEFAULT_MODEL) -> CrossEncoderReranker:
    """Return the global singleton reranker, creating it if needed."""
    global _reranker_instance
    if _reranker_instance is None or _reranker_instance._model_name != model_name:
        _reranker_instance = CrossEncoderReranker(model_name)
    return _reranker_instance
