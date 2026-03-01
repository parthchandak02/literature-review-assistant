"""Hybrid semantic + BM25 retriever for the RAG writing phase.

Two retrieval signals are combined via Reciprocal Rank Fusion (RRF):
  - Dense cosine similarity over Gemini text-embedding-004 vectors (768-dim)
  - BM25 lexical matching via bm25s (already a project dependency)

RRF formula (Cormack et al., 2009):
  rrf_score(chunk) = 1 / (k + rank_dense) + 1 / (k + rank_bm25)
  k = 60 (standard constant)

When query_text is not provided, falls back to dense-only for backward compat.
For typical reviews (50-500 papers, 250-5000 chunks), the full hybrid search
completes in < 30ms in-memory.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard constant from Cormack et al. 2009


@dataclass
class RetrievedChunk:
    """A chunk returned by semantic search."""

    chunk_id: str
    paper_id: str
    chunk_index: int
    content: str
    score: float


class RAGRetriever:
    """Hybrid BM25 + dense retriever backed by SQLite chunk store."""

    def __init__(self, db: aiosqlite.Connection, workflow_id: str) -> None:
        self._db = db
        self._workflow_id = workflow_id

    async def _load_all_chunks(
        self,
    ) -> tuple[list[str], list[str], list[int], list[str], list[list[float]]]:
        """Load all chunk embeddings for this workflow from DB."""
        chunk_ids: list[str] = []
        paper_ids: list[str] = []
        chunk_indices: list[int] = []
        contents: list[str] = []
        embeddings: list[list[float]] = []

        async with self._db.execute(
            """
            SELECT chunk_id, paper_id, chunk_index, content, embedding
            FROM paper_chunks_meta
            WHERE workflow_id = ? AND embedding IS NOT NULL
            """,
            (self._workflow_id,),
        ) as cursor:
            async for row in cursor:
                try:
                    vec = json.loads(row[4])
                except (json.JSONDecodeError, TypeError):
                    continue
                chunk_ids.append(row[0])
                paper_ids.append(row[1])
                chunk_indices.append(row[2])
                contents.append(row[3])
                embeddings.append(vec)

        return chunk_ids, paper_ids, chunk_indices, contents, embeddings

    def _compute_bm25_scores(
        self,
        query_text: str,
        contents: list[str],
    ) -> "list[float]":
        """Return per-chunk BM25 scores in original corpus order (higher = better).

        Uses bm25s with sorted=False so that result indices map back to the
        original corpus positions.
        """
        try:
            import bm25s  # project dependency; lazy import for startup perf
        except ImportError:
            logger.warning("bm25s not available; skipping BM25 retrieval")
            return [0.0] * len(contents)

        try:
            import numpy as np
        except ImportError:
            return [0.0] * len(contents)

        if not contents:
            return []

        corpus_tokens = bm25s.tokenize(contents, show_progress=False)
        query_tokens = bm25s.tokenize([query_text], show_progress=False)
        model = bm25s.BM25()
        model.index(corpus_tokens, show_progress=False)

        # sorted=False: result_indices[0] are corpus positions in arbitrary order;
        # result_scores[0] are their corresponding BM25 scores.
        result_indices, result_scores = model.retrieve(
            query_tokens, k=len(contents), sorted=False, show_progress=False
        )

        # Reconstruct scores in original corpus order.
        scores = np.zeros(len(contents), dtype=np.float32)
        for idx, score in zip(result_indices[0], result_scores[0]):
            scores[int(idx)] = float(score)

        return scores.tolist()

    @staticmethod
    def _rrf_scores(
        dense_scores: "list[float]",
        bm25_scores: "list[float]",
        k: int = _RRF_K,
    ) -> "list[float]":
        """Combine dense and BM25 scores via Reciprocal Rank Fusion.

        rank_dense[i] and rank_bm25[i] are 0-based positions in each ranking
        (0 = best). Chunks with identical scores share the same worst rank
        within their tied group, which is a conservative RRF tie-breaking
        convention (avoids artificially boosting tied chunks).
        """
        try:
            import numpy as np
        except ImportError:
            # Fall back to pure-Python RRF if numpy unavailable.
            n = len(dense_scores)
            dense_order = sorted(range(n), key=lambda i: -dense_scores[i])
            bm25_order = sorted(range(n), key=lambda i: -bm25_scores[i])
            rank_d = [0] * n
            rank_b = [0] * n
            for rank, idx in enumerate(dense_order):
                rank_d[idx] = rank
            for rank, idx in enumerate(bm25_order):
                rank_b[idx] = rank
            return [1.0 / (k + rank_d[i]) + 1.0 / (k + rank_b[i]) for i in range(n)]

        import numpy as np

        n = len(dense_scores)
        d = np.array(dense_scores, dtype=np.float64)
        b = np.array(bm25_scores, dtype=np.float64)

        # argsort ascending; reverse for best-first ranking.
        dense_order = np.argsort(d)[::-1]
        bm25_order = np.argsort(b)[::-1]

        # rank_d[i] = position of chunk i in the dense ranking (0 = best).
        rank_d = np.empty(n, dtype=np.float64)
        rank_d[dense_order] = np.arange(n, dtype=np.float64)

        rank_b = np.empty(n, dtype=np.float64)
        rank_b[bm25_order] = np.arange(n, dtype=np.float64)

        rrf = 1.0 / (k + rank_d) + 1.0 / (k + rank_b)
        return rrf.tolist()

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        paper_id_filter: Optional[list[str]] = None,
        query_text: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Return top-K chunks using hybrid BM25 + dense retrieval with RRF.

        Args:
            query_embedding: Query vector of length 768 (from embed_query).
            top_k: Number of results to return.
            paper_id_filter: If provided, restrict results to these paper_ids.
            query_text: If provided, enables BM25 retrieval and RRF fusion.
                        When None, falls back to dense-only (backward compat).

        Returns:
            List of RetrievedChunk sorted by descending RRF (or cosine) score.
        """
        try:
            import numpy as np
        except ImportError:
            logger.warning("numpy not available; returning empty retrieval results")
            return []

        chunk_ids, paper_ids, chunk_indices, contents, embeddings = (
            await self._load_all_chunks()
        )

        if not embeddings:
            return []

        # --- Dense cosine similarity ---
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_vec = query_vec / query_norm

        matrix = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        matrix = matrix / norms
        dense_scores: list[float] = (matrix @ query_vec).tolist()

        # --- Choose final scores ---
        if query_text:
            # Hybrid: BM25 + dense via RRF
            bm25_scores = self._compute_bm25_scores(query_text, contents)
            final_scores = self._rrf_scores(dense_scores, bm25_scores)
            logger.debug(
                "RAG hybrid search: %d chunks, query_text=%r",
                len(contents),
                query_text[:60],
            )
        else:
            # Dense-only fallback (original behaviour)
            final_scores = dense_scores

        # --- Build results, applying paper_id_filter ---
        filter_set = set(paper_id_filter) if paper_id_filter else None

        scored: list[tuple[float, int]] = [
            (final_scores[i], i)
            for i in range(len(chunk_ids))
            if (filter_set is None or paper_ids[i] in filter_set)
        ]

        # Sort descending by score; for RRF all scores are positive so no
        # need for a separate <= 0 guard.
        scored.sort(key=lambda t: -t[0])

        results: list[RetrievedChunk] = []
        for score_val, idx in scored[:top_k]:
            if not query_text and score_val <= 0:
                # Dense-only: skip zero-similarity chunks (filtered or unrelated)
                break
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_ids[idx],
                    paper_id=paper_ids[idx],
                    chunk_index=chunk_indices[idx],
                    content=contents[idx],
                    score=score_val,
                )
            )

        return results

    async def chunk_count(self) -> int:
        """Return total number of stored chunks for this workflow."""
        async with self._db.execute(
            "SELECT COUNT(*) FROM paper_chunks_meta WHERE workflow_id = ?",
            (self._workflow_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row else 0
