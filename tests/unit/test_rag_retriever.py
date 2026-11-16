from __future__ import annotations

import json

import aiosqlite
import pytest

from src.rag.retriever import RAGRetriever


async def _build_test_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """
        CREATE TABLE paper_chunks_meta (
            chunk_id TEXT,
            workflow_id TEXT,
            paper_id TEXT,
            chunk_index INTEGER,
            content TEXT,
            embedding TEXT
        )
        """
    )
    rows = [
        ("c1", "wf-test", "p1", 0, "blood pressure improved with intervention", json.dumps([1.0, 0.0])),
        ("c2", "wf-test", "p2", 1, "no meaningful change in primary outcome", json.dumps([0.0, 1.0])),
        ("c3", "wf-test", "p3", 2, "moderate effect with narrow confidence interval", json.dumps([0.7, 0.3])),
    ]
    await db.executemany(
        "INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    await db.commit()
    return db


@pytest.mark.asyncio
async def test_search_loads_corpus_once(monkeypatch: pytest.MonkeyPatch) -> None:
    db = await _build_test_db()
    try:
        retriever = RAGRetriever(db, "wf-test")
        calls = {"n": 0}
        original = retriever._load_all_chunks

        async def _wrapped():
            calls["n"] += 1
            return await original()

        monkeypatch.setattr(retriever, "_load_all_chunks", _wrapped)

        first = await retriever.search([1.0, 0.0], top_k=2)
        second = await retriever.search([0.0, 1.0], top_k=2)

        assert len(first) == 2
        assert len(second) == 2
        assert calls["n"] == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_bm25_model_cached_across_queries() -> None:
    pytest.importorskip("bm25s")
    db = await _build_test_db()
    try:
        retriever = RAGRetriever(db, "wf-test")
        first = await retriever.search([1.0, 0.0], top_k=2, query_text="blood pressure outcome")
        model_obj = retriever._bm25_model
        second = await retriever.search([1.0, 0.0], top_k=2, query_text="confidence interval effect")

        assert len(first) == 2
        assert len(second) == 2
        assert model_obj is not None
        assert retriever._bm25_model is model_obj
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_search_returns_empty_for_zero_query_vector() -> None:
    db = await _build_test_db()
    try:
        retriever = RAGRetriever(db, "wf-test")
        rows = await retriever.search([0.0, 0.0], top_k=3)
        assert rows == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_search_skips_malformed_embedding_rows() -> None:
    db = await _build_test_db()
    try:
        await db.execute(
            "INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
            ("bad-1", "wf-test", "p9", 9, "malformed vector row", "{bad-json"),
        )
        await db.commit()
        retriever = RAGRetriever(db, "wf-test")
        rows = await retriever.search([1.0, 0.0], top_k=5)
        assert rows
        assert all(r.chunk_id != "bad-1" for r in rows)
    finally:
        await db.close()


def test_rrf_scores_assigns_worst_rank_to_tied_scores() -> None:
    scores = RAGRetriever._rrf_scores([0.9, 0.5, 0.5], [0.0, 0.0, 0.0], k=60)
    assert scores[0] == pytest.approx(1.0 / 60 + 1.0 / 62)
    assert scores[1] == pytest.approx(1.0 / 62 + 1.0 / 62)
    assert scores[2] == pytest.approx(1.0 / 62 + 1.0 / 62)
    assert scores[0] > scores[1] == scores[2]

    mixed = RAGRetriever._rrf_scores([0.9, 0.7, 0.7, 0.2], [1.0, 3.0, 3.0, 0.0], k=60)
    assert mixed[0] == pytest.approx(1.0 / 60 + 1.0 / 62)
    assert mixed[1] == pytest.approx(1.0 / 62 + 1.0 / 61)
    assert mixed[2] == pytest.approx(1.0 / 62 + 1.0 / 61)
    assert mixed[3] == pytest.approx(1.0 / 63 + 1.0 / 63)

    assert RAGRetriever._rrf_scores([], []) == []
    with pytest.raises(ValueError):
        RAGRetriever._rrf_scores([0.5], [0.5, 0.1])


@pytest.mark.asyncio
async def test_hybrid_search_preserves_dense_order_when_bm25_scores_tie() -> None:
    pytest.importorskip("bm25s")
    db = await aiosqlite.connect(":memory:")
    try:
        await db.execute(
            """
            CREATE TABLE paper_chunks_meta (
                chunk_id TEXT,
                workflow_id TEXT,
                paper_id TEXT,
                chunk_index INTEGER,
                content TEXT,
                embedding TEXT
            )
            """
        )
        rows = [
            ("c1", "wf-tie", "p1", 0, "alpha beta", json.dumps([1.0, 0.0])),
            ("c2", "wf-tie", "p2", 1, "gamma delta", json.dumps([0.5, 0.866])),
            ("c3", "wf-tie", "p3", 2, "epsilon zeta", json.dumps([0.5, 0.866])),
        ]
        await db.executemany(
            "INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        await db.commit()

        retriever = RAGRetriever(db, "wf-tie")
        results = await retriever.search([1.0, 0.0], top_k=3, query_text="nonexistentterm")
        assert [r.chunk_id for r in results] == ["c1", "c2", "c3"]
        assert results[0].score > results[1].score == pytest.approx(results[2].score)
    finally:
        await db.close()
