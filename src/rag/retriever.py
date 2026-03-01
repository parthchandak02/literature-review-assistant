"""Semantic retriever: loads chunk embeddings from SQLite and returns top-K results.

Uses numpy cosine similarity for in-memory KNN search. For typical systematic
reviews (50-500 papers, 250-5000 chunks), this completes in < 10ms.
Falls back gracefully if no embeddings exist (returns empty list).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A chunk returned by semantic search."""

    chunk_id: str
    paper_id: str
    chunk_index: int
    content: str
    score: float


class RAGRetriever:
    """Semantic retriever backed by SQLite chunk store."""

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

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        paper_id_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return top-K chunks by cosine similarity to the query embedding.

        Args:
            query_embedding: Query vector of length 768.
            top_k: Number of results to return.
            paper_id_filter: If provided, restrict results to these paper_ids.

        Returns:
            List of RetrievedChunk sorted by descending similarity score.
        """
        try:
            import numpy as np  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("numpy not available; returning empty retrieval results")
            return []

        chunk_ids, paper_ids, chunk_indices, contents, embeddings = (
            await self._load_all_chunks()
        )

        if not embeddings:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_vec = query_vec / query_norm

        matrix = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        matrix = matrix / norms
        scores = matrix @ query_vec

        # Apply paper_id_filter before ranking
        if paper_id_filter:
            filter_set = set(paper_id_filter)
            mask = np.array(
                [1.0 if pid in filter_set else 0.0 for pid in paper_ids],
                dtype=np.float32,
            )
            scores = scores * mask

        top_indices = np.argsort(scores)[::-1][:top_k]
        results: list[RetrievedChunk] = []
        for idx in top_indices:
            score_val = float(scores[idx])
            if score_val <= 0:
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
