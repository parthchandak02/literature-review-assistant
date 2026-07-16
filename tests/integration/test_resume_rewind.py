"""Integration: resume from_phase clears sub-phase checkpoints and rollback data."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import (
    CandidatePaper,
    ExtractionRecord,
    PrimaryStudyStatus,
    ScreeningDecisionType,
    SearchResult,
    SourceCategory,
    StudyDesign,
)
from src.models.writing import SectionDraft
from src.orchestration.resume import load_resume_state
from tests.integration.conftest import WorkflowDbFixture, init_runtime_workflow_db


async def _seed_resume_run(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
    *,
    workflow_id: str = "wf-resume-rewind",
) -> tuple[WorkflowDbFixture, Path, Path]:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-07-16" / "rewind-topic" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    review_path, settings_path = minimal_config_paths
    (run_dir / "config_snapshot.yaml").write_text(review_path.read_text(encoding="utf-8"), encoding="utf-8")
    await init_runtime_workflow_db(
        db_path,
        workflow_id,
        topic="Resume rewind integration topic",
        config_hash="resume-rewind-hash",
        status="interrupted",
    )
    fixture = WorkflowDbFixture(
        workflow_id=workflow_id,
        db_path=db_path,
        run_root=run_root,
        topic="Resume rewind integration topic",
        config_hash="resume-rewind-hash",
    )
    return fixture, review_path, settings_path


@pytest.mark.asyncio
async def test_from_phase_clears_phase_3b_fulltext_subphase_checkpoint(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    fixture, review_path, settings_path = await _seed_resume_run(tmp_path, minimal_config_paths)

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_checkpoint(fixture.workflow_id, "phase_2_search", papers_processed=1)
        await repo.save_checkpoint(fixture.workflow_id, "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint(fixture.workflow_id, "phase_3b_fulltext", papers_processed=1)
        await db.commit()

    _, next_phase = await load_resume_state(
        db_path=str(fixture.db_path),
        workflow_id=fixture.workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(fixture.run_root),
        from_phase="phase_3_screening",
    )
    assert next_phase == "phase_3_screening"

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(fixture.workflow_id)

    assert "phase_2_search" in checkpoints
    assert "phase_3_screening" not in checkpoints
    assert "phase_3b_fulltext" not in checkpoints


@pytest.mark.asyncio
async def test_from_phase_writing_clears_writing_subphase_checkpoints(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    fixture, review_path, settings_path = await _seed_resume_run(
        tmp_path,
        minimal_config_paths,
        workflow_id="wf-resume-writing-subphases",
    )

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        for phase in (
            "phase_2_search",
            "phase_3_screening",
            "phase_4_extraction_quality",
            "phase_4b_embedding",
            "phase_5_synthesis",
            "phase_5b_knowledge_graph",
            "phase_5c_pre_writing_gate",
            "phase_6_writing",
            "phase_6a_hyde",
            "phase_6a2_outline",
            "phase_6b_phase_a",
            "phase_6e_concepts",
            "phase_6f_custom_diagrams",
        ):
            await repo.save_checkpoint(fixture.workflow_id, phase, papers_processed=1)
        await db.commit()

    _, next_phase = await load_resume_state(
        db_path=str(fixture.db_path),
        workflow_id=fixture.workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(fixture.run_root),
        from_phase="phase_6_writing",
    )
    assert next_phase == "phase_6_writing"

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(fixture.workflow_id)

    assert "phase_6_writing" not in checkpoints
    for sub_phase in (
        "phase_6a_hyde",
        "phase_6a2_outline",
        "phase_6b_phase_a",
        "phase_6e_concepts",
        "phase_6f_custom_diagrams",
    ):
        assert sub_phase not in checkpoints


@pytest.mark.asyncio
async def test_from_phase_search_rollback_phase_data_clears_downstream_rows(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    fixture, review_path, settings_path = await _seed_resume_run(
        tmp_path,
        minimal_config_paths,
        workflow_id="wf-resume-rollback",
    )
    paper = CandidatePaper(
        paper_id="p-rewind-1",
        title="Rewind paper",
        authors=["Author"],
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_checkpoint(fixture.workflow_id, "phase_2_search", papers_processed=1)
        await repo.save_checkpoint(fixture.workflow_id, "phase_3_screening", papers_processed=1)
        await repo.save_checkpoint(fixture.workflow_id, "phase_4_extraction_quality", papers_processed=1)
        await repo.save_paper(paper)
        await repo.save_search_result(
            SearchResult(
                workflow_id=fixture.workflow_id,
                database_name="openalex",
                source_category=SourceCategory.DATABASE,
                search_date="2026-07-16",
                search_query="rewind",
                records_retrieved=1,
                papers=[paper],
            )
        )
        await repo.save_dual_screening_result(
            fixture.workflow_id,
            "p-rewind-1",
            "title_abstract",
            True,
            ScreeningDecisionType.INCLUDE,
            False,
        )
        await repo.save_extraction_record(
            fixture.workflow_id,
            ExtractionRecord(
                paper_id="p-rewind-1",
                study_design=StudyDesign.MIXED_METHODS,
                primary_study_status=PrimaryStudyStatus.PRIMARY,
                participant_count=20,
                intervention_description="Intervention",
                results_summary={"summary": "Improved coverage."},
                extraction_source="openalex_content",
            ),
        )
        await db.commit()

    _, next_phase = await load_resume_state(
        db_path=str(fixture.db_path),
        workflow_id=fixture.workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(fixture.run_root),
        from_phase="phase_2_search",
    )
    assert next_phase == "phase_2_search"

    async with get_db(str(fixture.db_path)) as db:
        search_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM search_results WHERE workflow_id = ?",
                (fixture.workflow_id,),
            )
        ).fetchone()
        screening_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = ?",
                (fixture.workflow_id,),
            )
        ).fetchone()
        extraction_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM extraction_records WHERE workflow_id = ?",
                (fixture.workflow_id,),
            )
        ).fetchone()
        paper_count = await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone()

    assert int(search_count[0]) == 0
    assert int(screening_count[0]) == 0
    assert int(extraction_count[0]) == 0
    assert int(paper_count[0]) == 0


@pytest.mark.asyncio
async def test_from_phase_writing_clears_section_drafts_via_repository(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    fixture, review_path, settings_path = await _seed_resume_run(
        tmp_path,
        minimal_config_paths,
        workflow_id="wf-resume-section-drafts",
    )

    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        for phase in (
            "phase_2_search",
            "phase_3_screening",
            "phase_4_extraction_quality",
            "phase_4b_embedding",
            "phase_5_synthesis",
            "phase_5b_knowledge_graph",
            "phase_5c_pre_writing_gate",
            "phase_6_writing",
        ):
            await repo.save_checkpoint(fixture.workflow_id, phase, papers_processed=1)
        await repo.save_section_draft(
            SectionDraft(
                workflow_id=fixture.workflow_id,
                section="results",
                version=1,
                content="stale draft",
                claims_used=[],
                citations_used=[],
                word_count=2,
            )
        )
        await db.commit()

    await load_resume_state(
        db_path=str(fixture.db_path),
        workflow_id=fixture.workflow_id,
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_root=str(fixture.run_root),
        from_phase="phase_6_writing",
    )

    async with get_db(str(fixture.db_path)) as db:
        draft_count = await (
            await db.execute(
                "SELECT COUNT(*) FROM section_drafts WHERE workflow_id = ?",
                (fixture.workflow_id,),
            )
        ).fetchone()
    assert int(draft_count[0]) == 0
