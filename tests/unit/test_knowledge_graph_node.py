"""Unit tests for Phase 5b KnowledgeGraphNode (`src/orchestration/knowledge_graph_node.py`)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.knowledge_graph.builder import build_paper_graph as real_build_paper_graph
from src.models import CandidatePaper, ExtractionRecord, OutcomeRecord, SourceCategory, StudyDesign
from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
from src.orchestration.nodes.pre_writing_gate import PreWritingGateNode
from src.orchestration.state import ReviewState

_WORKFLOW_ID = "wf-kg-node-test"


class _FakeRunContext:
    def __init__(self) -> None:
        self.starts: list[tuple[str, str, int | None]] = []
        self.statuses: list[str] = []
        self.dones: list[tuple[str, dict[str, object] | None]] = []

    def emit_phase_start(self, phase: str, msg: str, total: int | None = None) -> None:
        self.starts.append((phase, msg, total))

    def log_status(self, message: str) -> None:
        self.statuses.append(message)

    def emit_phase_done(self, phase: str, summary: dict[str, object] | None = None) -> None:
        self.dones.append((phase, summary))


def _paper(paper_id: str, title: str = "Study title") -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        authors=["Smith, J."],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )


def _record(
    paper_id: str,
    outcome: str = "adherence",
    demographics: str = "urban adults",
    intervention: str = "digital reminder",
    design: StudyDesign = StudyDesign.RCT,
) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=design,
        participant_demographics=demographics,
        intervention_description=intervention,
        outcomes=[OutcomeRecord(name=outcome)],
        results_summary={"summary": "Positive effect reported."},
    )


async def _setup_run(
    tmp_path: Path,
    name: str,
    papers: list[CandidatePaper],
    records: list[ExtractionRecord],
    chunks: list[tuple[str, str, int, str | None]] | None = None,
    rc: _FakeRunContext | None = None,
) -> tuple[Path, Path, ReviewState]:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        repo = WorkflowRepository(db)
        await repo.create_workflow(_WORKFLOW_ID, "Knowledge graph test topic", "cfg-hash")
        for paper in papers:
            await repo.save_paper(paper)
        for rec in records:
            await repo.save_extraction_record(_WORKFLOW_ID, rec)
        for c_id, p_id, idx, emb in chunks or []:
            await db.execute(
                "INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                (c_id, _WORKFLOW_ID, p_id, idx, f"Chunk {c_id}", emb),
            )
        await db.commit()
    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id=_WORKFLOW_ID,
        db_path=str(db_path),
        included_papers=papers,
        extraction_records=records,
        run_context=rc,  # type: ignore[arg-type]
    )
    return run_dir, db_path, state


async def _db_counts(db_path: Path) -> tuple[int, int, int, str | None]:
    async with get_db(str(db_path)) as db:
        counts = []
        for tbl in ("paper_relationships", "graph_communities", "research_gaps"):
            row = await (
                await db.execute(f"SELECT COUNT(*) FROM {tbl} WHERE workflow_id = ?", (_WORKFLOW_ID,))
            ).fetchone()
            counts.append(int(row[0]) if row else 0)
        cp = (await WorkflowRepository(db).get_checkpoints(_WORKFLOW_ID)).get("phase_5b_knowledge_graph")
    return counts[0], counts[1], counts[2], cp


@pytest.mark.asyncio
async def test_knowledge_graph_node_builds_persists_and_renders_end_to_end(tmp_path: Path) -> None:
    papers = [_paper(f"p{i}", f"Trial {i}") for i in range(1, 6)]
    records = [
        _record("p1", "adherence", "urban adults", "alpha protocol"),
        _record("p2", "adherence", "urban adults", "beta counseling"),
        _record("p3", "engagement", "rural elderly", "gamma portal"),
        _record("p4", "adherence", "urban adults", "delta check"),
        _record("p5", "adherence", "urban adults", "eps", StudyDesign.COHORT),
    ]
    chunks = [("c1", "p1", 0, "[1.0, 0.0]"), ("c2", "p2", 0, "[0.9, 0.1]"), ("c3", "p4", 0, "[1.0, 0.0]")]
    rc = _FakeRunContext()
    run_dir, db_path, state = await _setup_run(tmp_path, "run_e2e", papers, records, chunks=chunks, rc=rc)

    next_node = await KnowledgeGraphNode().run(GraphRunContext(state=state, deps=None))

    assert isinstance(next_node, PreWritingGateNode)
    expected_png = run_dir / "fig_evidence_network.png"
    assert state.artifacts["evidence_network"] == str(expected_png)
    assert expected_png.exists() and (run_dir / "fig_evidence_network.svg").exists()
    rels, comms, gaps, cp = await _db_counts(db_path)
    assert rels > 0 and comms > 0 and gaps > 0 and cp == "completed"
    assert rc.starts == [("phase_5b_knowledge_graph", "Building evidence knowledge graph (5 papers)...", 1)]
    assert rc.dones == [("phase_5b_knowledge_graph", {"graphs_built": 1})]


@pytest.mark.asyncio
async def test_knowledge_graph_node_is_idempotent_when_relationships_exist(tmp_path: Path) -> None:
    papers, records, rc = [_paper("p1"), _paper("p2")], [_record("p1"), _record("p2")], _FakeRunContext()
    _, db_path, state = await _setup_run(tmp_path, "run_idem", papers, records, rc=rc)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO paper_relationships (workflow_id, source_paper_id, target_paper_id, rel_type, weight) "
            "VALUES (?, 'p1', 'p2', 'shared_outcome', 1.0)",
            (_WORKFLOW_ID,),
        )
        await db.commit()

    with (
        patch("src.orchestration.knowledge_graph_node.build_paper_graph") as mock_build,
        patch("src.visualization.evidence_network.render_evidence_network", new_callable=AsyncMock) as mock_render,
    ):
        next_node = await KnowledgeGraphNode().run(GraphRunContext(state=state, deps=None))

    assert isinstance(next_node, PreWritingGateNode)
    mock_build.assert_not_called()
    mock_render.assert_not_awaited()
    assert "evidence_network" not in state.artifacts
    assert any("already built" in msg for msg in rc.statuses)
    assert rc.dones == [("phase_5b_knowledge_graph", {"graphs_built": 1})]
    rels, comms, _, cp = await _db_counts(db_path)
    assert rels == 1 and comms == 0 and cp == "completed"


@pytest.mark.asyncio
async def test_knowledge_graph_node_skips_figure_when_graph_has_no_edges(tmp_path: Path) -> None:
    _, db_path, state = await _setup_run(tmp_path, "run_no_edges", [_paper("p1")], [_record("p1")])

    with patch("src.visualization.evidence_network.render_evidence_network", new_callable=AsyncMock) as mock_render:
        next_node = await KnowledgeGraphNode().run(GraphRunContext(state=state, deps=None))

    assert isinstance(next_node, PreWritingGateNode)
    mock_render.assert_not_awaited()
    assert "evidence_network" not in state.artifacts
    _, comms, _, cp = await _db_counts(db_path)
    assert comms == 1 and cp == "completed"


@pytest.mark.asyncio
async def test_knowledge_graph_node_handles_figure_render_error_nonfatally(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    papers, records, rc = [_paper("p1"), _paper("p2")], [_record("p1"), _record("p2")], _FakeRunContext()
    _, db_path, state = await _setup_run(tmp_path, "run_render_fail", papers, records, rc=rc)

    with (
        caplog.at_level(logging.WARNING, logger="src.orchestration.knowledge_graph_node"),
        patch(
            "src.visualization.evidence_network.render_evidence_network",
            new_callable=AsyncMock,
            side_effect=RuntimeError("render crash"),
        ),
    ):
        next_node = await KnowledgeGraphNode().run(GraphRunContext(state=state, deps=None))

    assert isinstance(next_node, PreWritingGateNode)
    assert "evidence_network" not in state.artifacts
    assert "evidence network figure failed (non-fatal)" in caplog.text
    assert rc.dones == [("phase_5b_knowledge_graph", {"graphs_built": 1})]
    rels, _, _, cp = await _db_counts(db_path)
    assert rels == 1 and cp == "completed"


@pytest.mark.asyncio
async def test_knowledge_graph_node_averages_valid_embeddings_and_skips_mixed_dims(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    records = [
        _record("p1", outcome="o1", intervention="alpha unique"),
        _record("p2", outcome="o2", intervention="beta distinct"),
        _record("p3", outcome="o3", intervention="gamma separate"),
    ]
    chunks = [
        ("c1", "p1", 0, "[1.0, 3.0]"),
        ("c2", "p1", 1, "[3.0, 1.0]"),
        ("c3", "p2", 0, "{bad-json"),
        ("c4", "p2", 1, "[0.5, 0.5]"),
        ("c5", "p3", 0, "[1.0, 0.0]"),
        ("c6", "p3", 1, "[1.0, 0.0, 0.0]"),
    ]
    _, _, state = await _setup_run(tmp_path, "run_emb", papers, records, chunks=chunks)
    captured: dict[str, list[float]] = {}

    def _spy_build_paper_graph(records, papers, chunk_embeddings=None):
        if chunk_embeddings:
            captured.update(chunk_embeddings)
        return real_build_paper_graph(records=records, papers=papers, chunk_embeddings=chunk_embeddings)

    with (
        caplog.at_level(logging.WARNING, logger="src.orchestration.knowledge_graph_node"),
        patch("src.orchestration.knowledge_graph_node.build_paper_graph", side_effect=_spy_build_paper_graph),
        patch("src.visualization.evidence_network.render_evidence_network", new_callable=AsyncMock),
    ):
        next_node = await KnowledgeGraphNode().run(GraphRunContext(state=state, deps=None))

    assert isinstance(next_node, PreWritingGateNode)
    assert captured["p1"] == pytest.approx([2.0, 2.0])
    assert captured["p2"] == pytest.approx([0.5, 0.5])
    assert "p3" not in captured
    assert "Skipping paper p3: mixed embedding dimensions" in caplog.text
