"""Unit tests for resume state loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper
from src.models.enums import ScreeningDecisionType, SourceCategory
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState


@pytest.mark.asyncio
async def test_load_resume_state_phase3(tmp_path) -> None:
    run_dir = tmp_path / "2026-02-16" / "how-do-ai-tutors-impact-learning" / "run_01-00-00PM"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.save_paper(
            CandidatePaper(
                paper_id="p1",
                title="Paper 1",
                authors=["A"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await repo.save_paper(
            CandidatePaper(
                paper_id="p2",
                title="Paper 2",
                authors=["B"],
                source_database="openalex",
                source_category=SourceCategory.DATABASE,
            )
        )
        await repo.create_workflow("wf-resume", "How do AI tutors impact learning?", "abc123")
        await repo.save_checkpoint("wf-resume", "phase_2_search", papers_processed=2)
        await repo.save_dual_screening_result(
            "wf-resume", "p1", "title_abstract", True, ScreeningDecisionType.INCLUDE, False
        )
        await repo.save_dual_screening_result(
            "wf-resume", "p1", "fulltext", True, ScreeningDecisionType.INCLUDE, False
        )

    state, next_phase = await load_resume_state(
        db_path=str(db_path),
        workflow_id="wf-resume",
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        log_root=str(tmp_path),
        output_root=str(tmp_path / "outputs"),
    )
    assert isinstance(state, ReviewState)
    assert state.workflow_id == "wf-resume"
    assert next_phase == "phase_3_screening"
    assert len(state.deduped_papers) >= 1
    assert len(state.included_papers) == 1
    assert state.included_papers[0].paper_id == "p1"
