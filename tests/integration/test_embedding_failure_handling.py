"""Failed or zero-vector embeddings are never treated as embedded papers."""

from __future__ import annotations

import json

import pytest
from pydantic_graph import GraphRunContext

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, ExtractionRecord, SourceCategory, StudyDesign
from src.orchestration import embedding_node as embedding_node_mod
from src.orchestration.embedding_node import EmbeddingNode
from src.orchestration.helpers.pre_writing_gate import compute_pre_writing_gate_report
from src.orchestration.state import ReviewState
from tests.integration.conftest import WorkflowDbFixture
from tests.integration.test_graph_transitions import _seed_pre_writing_blocked_state

_GOOD_VEC = [0.1, 0.2, 0.3]


def _record(paper_id: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.QUALITATIVE,
        intervention_description=f"Structured exercise intervention for adults marker-{paper_id}.",
        outcomes=[],
        results_summary={"summary": "Participants reported improved outcomes after the intervention."},
    )


async def _embedding_state(fixture: WorkflowDbFixture, paper_ids: list[str]) -> ReviewState:
    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        for pid in paper_ids:
            await repo.save_paper(
                CandidatePaper(
                    paper_id=pid,
                    title=f"Paper {pid}",
                    authors=["Author"],
                    source_database="openalex",
                    source_category=SourceCategory.DATABASE,
                )
            )
        await db.commit()
    _review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    return ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(fixture.run_root),
        workflow_id=fixture.workflow_id,
        db_path=str(fixture.db_path),
        settings=settings,
        extraction_records=[_record(pid) for pid in paper_ids],
    )


async def _chunks_by_paper(fixture: WorkflowDbFixture) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {}
    async with get_db(str(fixture.db_path)) as db:
        cursor = await db.execute(
            "SELECT paper_id, embedding FROM paper_chunks_meta WHERE workflow_id = ?",
            (fixture.workflow_id,),
        )
        for pid, emb in await cursor.fetchall():
            out.setdefault(str(pid), []).append(json.loads(emb))
    return out


@pytest.mark.asyncio
async def test_failed_paper_is_not_persisted_and_checkpoint_is_partial(
    tmp_workflow_db: WorkflowDbFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _embedding_state(tmp_workflow_db, ["p-ok", "p-fail"])
    calls: list[int] = []

    async def _fake_embed_texts(texts: list[str], **_kwargs: object) -> list[list[float] | None]:
        calls.append(len(texts))
        return [None if "marker-p-fail" in t else list(_GOOD_VEC) for t in texts]

    monkeypatch.setattr(embedding_node_mod, "embed_texts", _fake_embed_texts)
    await EmbeddingNode().run(GraphRunContext(state=state, deps=None))

    chunks = await _chunks_by_paper(tmp_workflow_db)
    assert set(chunks) == {"p-ok"}
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(tmp_workflow_db.workflow_id)
    assert checkpoints["phase_4b_embedding"] == "partial"

    # Resume: the failed paper is retried; the embedded one is skipped.
    async def _ok_embed_texts(texts: list[str], **_kwargs: object) -> list[list[float] | None]:
        calls.append(len(texts))
        return [list(_GOOD_VEC) for _ in texts]

    monkeypatch.setattr(embedding_node_mod, "embed_texts", _ok_embed_texts)
    await EmbeddingNode().run(GraphRunContext(state=state, deps=None))
    chunks = await _chunks_by_paper(tmp_workflow_db)
    assert set(chunks) == {"p-ok", "p-fail"}
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(tmp_workflow_db.workflow_id)
    assert checkpoints["phase_4b_embedding"] == "completed"


@pytest.mark.asyncio
async def test_legacy_zero_vectors_are_replaced_on_resume(
    tmp_workflow_db: WorkflowDbFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _embedding_state(tmp_workflow_db, ["p-zero"])
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        await db.execute(
            """
            INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("legacy-zero", tmp_workflow_db.workflow_id, "p-zero", 0, "old", json.dumps([0.0, 0.0, 0.0])),
        )
        await db.commit()

    async def _ok_embed_texts(texts: list[str], **_kwargs: object) -> list[list[float] | None]:
        return [list(_GOOD_VEC) for _ in texts]

    monkeypatch.setattr(embedding_node_mod, "embed_texts", _ok_embed_texts)
    await EmbeddingNode().run(GraphRunContext(state=state, deps=None))

    chunks = await _chunks_by_paper(tmp_workflow_db)
    assert chunks["p-zero"]
    assert all(any(vec) for vec in chunks["p-zero"])


@pytest.mark.asyncio
async def test_pre_writing_gate_blocks_on_zero_vector_chunks(tmp_workflow_db: WorkflowDbFixture) -> None:
    state = await _seed_pre_writing_blocked_state(tmp_workflow_db, rewinds_exhausted=False)
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        await db.execute(
            """
            INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("zero-1", tmp_workflow_db.workflow_id, "p-gate-1", 0, "Chunk", json.dumps([0.0] * 8)),
        )
        await db.commit()
        repo = WorkflowRepository(db)
        report = await compute_pre_writing_gate_report(state=state, repository=repo, db=db, attempt_number=1)

    checks = {check.name: check for check in report.checks}
    assert checks["rag_chunk_coverage"].ok
    assert not checks["rag_embedding_validity"].ok
    assert not report.ready
    assert report.rewind_phase == "phase_4b_embedding"
