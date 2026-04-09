from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, CohortMembershipRecord, ExtractionRecord, SourceCategory, StudyDesign
from src.orchestration.state import ReviewState
from src.orchestration.workflow import _compute_pre_writing_gate_report
from src.quality.casp import CaspAssessor


def _paper() -> CandidatePaper:
    return CandidatePaper(
        paper_id="p1",
        title="AI tutor outcomes in higher education",
        authors=["Smith"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )


def _record() -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.QUALITATIVE,
        intervention_description="AI tutoring support",
        outcomes=[],
        results_summary={"summary": "Positive learning outcomes were reported."},
    )


async def _seed_gate_ready_db(tmp_path: Path) -> tuple[str, ReviewState]:
    run_dir = tmp_path / "2026-04-08" / "topic" / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    paper = _paper()
    record = _record()

    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prewrite", "Test topic", "abc123")
        await repo.save_paper(paper)
        await repo.bulk_upsert_cohort_memberships(
            [
                CohortMembershipRecord(
                    workflow_id="wf-prewrite",
                    paper_id="p1",
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
            ("openalex", "database", "2026-04-08", "ai tutor", 1, "wf-prewrite"),
        )
        await db.commit()
        await repo.save_extraction_record("wf-prewrite", record)
        assessment = await CaspAssessor().assess(record)
        await repo.save_casp_assessment("wf-prewrite", "p1", assessment)
        await db.execute(
            """
            INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("chunk-1", "wf-prewrite", "p1", 0, "Chunk text", "[0.1, 0.2]"),
        )
        await db.commit()

    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-prewrite",
        db_path=str(db_path),
        included_papers=[paper],
        extraction_records=[record],
        dedup_count=0,
    )
    return str(db_path), state


@pytest.mark.asyncio
async def test_pre_writing_gate_report_passes_when_prerequisites_exist(tmp_path: Path) -> None:
    db_path, state = await _seed_gate_ready_db(tmp_path)
    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        report = await _compute_pre_writing_gate_report(
            state=state,
            repository=repo,
            db=db,
            attempt_number=1,
        )
    assert report.ready is True
    assert report.rewind_phase is None
    assert all(check.ok for check in report.checks)


@pytest.mark.asyncio
async def test_pre_writing_gate_report_requests_embedding_rewind_when_chunks_missing(tmp_path: Path) -> None:
    db_path, state = await _seed_gate_ready_db(tmp_path)
    async with get_db(db_path) as db:
        await db.execute("DELETE FROM paper_chunks_meta WHERE workflow_id = ?", ("wf-prewrite",))
        await db.commit()
        repo = WorkflowRepository(db)
        report = await _compute_pre_writing_gate_report(
            state=state,
            repository=repo,
            db=db,
            attempt_number=1,
        )
    assert report.ready is False
    assert report.rewind_phase == "phase_4b_embedding"
    assert any(check.name == "rag_chunk_coverage" and not check.ok for check in report.checks)
