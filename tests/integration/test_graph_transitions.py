"""Graph transition matrix: node routing with real SQLite and mocked LLM/search."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_graph import End, GraphRunContext

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import (
    CandidatePaper,
    CohortMembershipRecord,
    ExtractionRecord,
    SourceCategory,
    StudyDesign,
)
from src.orchestration.nodes.extraction_quality import ExtractionQualityNode
from src.orchestration.nodes.pre_writing_gate import PreWritingGateNode
from src.orchestration.nodes.resume_start import ResumeStartNode
from src.orchestration.nodes.screening import ScreeningNode
from src.orchestration.nodes.search import SearchNode
from src.orchestration.nodes.start import StartNode
from src.orchestration.nodes.writing import WritingNode
from src.orchestration.state import ReviewState
from src.orchestration.workflow import RUN_GRAPH
from src.quality.casp import CaspAssessor
from tests.integration.conftest import WorkflowDbFixture, init_runtime_workflow_db


def _graph_ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


@pytest.mark.asyncio
async def test_start_node_routes_to_search_node(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    review_path, settings_path = minimal_config_paths
    run_root = tmp_path / "runs"
    state = ReviewState(
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(run_root),
    )

    next_node = await StartNode().run(_graph_ctx(state))

    assert isinstance(next_node, SearchNode)
    assert state.workflow_id
    assert state.db_path
    assert state.review is not None
    assert state.settings is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("next_phase", "expected_type"),
    [
        ("phase_3_screening", ScreeningNode),
        ("phase_4_extraction_quality", ExtractionQualityNode),
    ],
)
async def test_resume_start_node_routes_by_phase(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
    next_phase: str,
    expected_type: type,
) -> None:
    review_path, settings_path = minimal_config_paths
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    state = ReviewState(
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(tmp_path / "runs"),
        workflow_id="wf-resume-route",
        next_phase=next_phase,
        log_dir=str(log_dir),
        run_id="resume-route-run",
    )

    next_node = await ResumeStartNode().run(_graph_ctx(state))

    assert isinstance(next_node, expected_type)


async def _seed_pre_writing_blocked_state(
    fixture: WorkflowDbFixture,
    *,
    rewinds_exhausted: bool,
) -> ReviewState:
    paper = CandidatePaper(
        paper_id="p-gate-1",
        title="Graph gate paper",
        authors=["Author"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    record = ExtractionRecord(
        paper_id="p-gate-1",
        study_design=StudyDesign.QUALITATIVE,
        intervention_description="Intervention",
        outcomes=[],
        results_summary={"summary": "Reported outcomes."},
    )

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        await repo.bulk_upsert_cohort_memberships(
            [
                CohortMembershipRecord(
                    workflow_id=fixture.workflow_id,
                    paper_id="p-gate-1",
                    screening_status="included",
                    fulltext_status="assessed",
                    synthesis_eligibility="included_primary",
                    exclusion_reason_code=None,
                    source_phase="phase_4_extraction_quality",
                )
            ]
        )
        await db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query, records_retrieved, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("openalex", "database", "2026-07-16", "graph gate", 1, fixture.workflow_id),
        )
        await repo.save_extraction_record(fixture.workflow_id, record)
        assessment = await CaspAssessor().assess(record)
        await repo.save_casp_assessment(fixture.workflow_id, "p-gate-1", assessment)
        if rewinds_exhausted:
            await repo.get_or_create_recovery_policy(
                fixture.workflow_id,
                "phase_5c_pre_writing_gate",
                "pre_writing_validation",
                max_retries=0,
                max_rewinds=1,
            )
            await repo.increment_rewind_count(
                fixture.workflow_id,
                "phase_5c_pre_writing_gate",
                "pre_writing_validation",
            )
        await db.commit()

    review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    run_dir = fixture.run_root / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(fixture.run_root),
        workflow_id=fixture.workflow_id,
        db_path=str(fixture.db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        review=review,
        settings=settings,
        included_papers=[paper],
        extraction_records=[record],
        dedup_count=0,
        artifacts={"run_summary": str(run_dir / "run_summary.json")},
    )


@pytest.mark.asyncio
async def test_pre_writing_gate_ready_routes_to_writing_node(
    tmp_workflow_db: WorkflowDbFixture,
) -> None:
    paper = CandidatePaper(
        paper_id="p-ready-1",
        title="Ready paper",
        authors=["Author"],
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )
    record = ExtractionRecord(
        paper_id="p-ready-1",
        study_design=StudyDesign.QUALITATIVE,
        intervention_description="Intervention",
        outcomes=[],
        results_summary={"summary": "Positive outcomes."},
    )

    async with get_db(str(tmp_workflow_db.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        await repo.bulk_upsert_cohort_memberships(
            [
                CohortMembershipRecord(
                    workflow_id=tmp_workflow_db.workflow_id,
                    paper_id="p-ready-1",
                    screening_status="included",
                    fulltext_status="assessed",
                    synthesis_eligibility="included_primary",
                    exclusion_reason_code=None,
                    source_phase="phase_4_extraction_quality",
                )
            ]
        )
        await db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query, records_retrieved, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("openalex", "database", "2026-07-16", "ready gate", 1, tmp_workflow_db.workflow_id),
        )
        await repo.save_extraction_record(tmp_workflow_db.workflow_id, record)
        assessment = await CaspAssessor().assess(record)
        await repo.save_casp_assessment(tmp_workflow_db.workflow_id, "p-ready-1", assessment)
        await db.execute(
            """
            INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("chunk-ready-1", tmp_workflow_db.workflow_id, "p-ready-1", 0, "Chunk text", "[0.1, 0.2]"),
        )
        await db.commit()

    review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    run_dir = tmp_workflow_db.run_root / "ready-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_workflow_db.run_root),
        workflow_id=tmp_workflow_db.workflow_id,
        db_path=str(tmp_workflow_db.db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        review=review,
        settings=settings,
        included_papers=[paper],
        extraction_records=[record],
        dedup_count=0,
        artifacts={"run_summary": str(run_dir / "run_summary.json")},
    )

    next_node = await PreWritingGateNode().run(_graph_ctx(state))

    assert isinstance(next_node, WritingNode)


@pytest.mark.asyncio
async def test_pre_writing_gate_terminal_failure_aborts_graph(
    tmp_workflow_db: WorkflowDbFixture,
) -> None:
    """Missing RAG chunks with exhausted rewinds stops the graph before writing."""
    state = await _seed_pre_writing_blocked_state(tmp_workflow_db, rewinds_exhausted=True)

    with pytest.raises(RuntimeError, match="pre-writing gate blocked"):
        await RUN_GRAPH.run(PreWritingGateNode(), state=state)


@pytest.mark.asyncio
async def test_pre_writing_gate_rewindable_failure_routes_to_embedding_node(
    tmp_workflow_db: WorkflowDbFixture,
) -> None:
    """First blocking failure with rewind budget routes back to embedding."""
    state = await _seed_pre_writing_blocked_state(tmp_workflow_db, rewinds_exhausted=False)

    next_node = await PreWritingGateNode().run(_graph_ctx(state))

    from src.orchestration.embedding_node import EmbeddingNode

    assert isinstance(next_node, EmbeddingNode)
    assert not isinstance(next_node, End)


@pytest.mark.asyncio
async def test_search_node_csv_strict_gate_failure_returns_end(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
    mock_search_connectors: None,
) -> None:
    """Strict search-volume gate failure terminates RUN_GRAPH with End output."""
    review_path, settings_path = minimal_config_paths
    strict_settings = settings_path.read_text(encoding="utf-8").replace(
        "profile: warning",
        "profile: strict",
    )
    settings_path.write_text(strict_settings, encoding="utf-8")

    workflow_id = "wf-search-end"
    run_dir = tmp_path / "runs" / "2026-07-16" / workflow_id / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    await init_runtime_workflow_db(db_path, workflow_id)

    review, settings = load_configs(str(review_path), str(settings_path))
    masterlist = run_dir / "masterlist.csv"
    masterlist.write_text("Title,Authors,Year,DOI,Abstract\n", encoding="utf-8")
    review.masterlist_csv_path = str(masterlist)

    state = ReviewState(
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(tmp_path / "runs"),
        workflow_id=workflow_id,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        review=review,
        settings=settings,
        artifacts={
            "run_summary": str(run_dir / "run_summary.json"),
            "protocol": str(run_dir / "doc_protocol.md"),
            "search_appendix": str(run_dir / "search_appendix.md"),
            "masterlist_csv": str(masterlist),
        },
    )

    next_node = await SearchNode().run(_graph_ctx(state))

    assert isinstance(next_node, End)
    assert next_node.data["status"] == "failed"
    assert next_node.data["gate"] == "search_volume"
