from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import (
    CandidatePaper,
    ExtractionRecord,
    OutlineNode,
    PrimaryStudyStatus,
    SectionOutline,
    SourceCategory,
    StudyDesign,
)
from src.models.enums import ScreeningDecisionType


@pytest.mark.asyncio
async def test_rollback_from_writing_clears_section_outlines(tmp_path) -> None:
    async with get_db(str(tmp_path / "rollback_writing.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outline", "topic", "hash")
        await repo.save_section_outline(
            "wf-outline",
            SectionOutline(
                section_key="results",
                nodes=[
                    OutlineNode(
                        node_id="study_selection",
                        heading="Study Selection",
                        intent="Cover PRISMA flow.",
                        required_citekeys=[],
                        evidence_chunk_ids=[],
                    )
                ],
                grounding_hash="abc123",
            ),
        )

        assert set((await repo.load_section_outlines("wf-outline")).keys()) == {"results"}
        await repo.rollback_phase_data("wf-outline", "phase_6_writing")
        assert await repo.load_section_outlines("wf-outline") == {}


@pytest.mark.asyncio
async def test_rollback_from_finalize_keeps_section_outlines(tmp_path) -> None:
    async with get_db(str(tmp_path / "rollback_finalize.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-outline-finalize", "topic", "hash")
        await repo.save_section_outline(
            "wf-outline-finalize",
            SectionOutline(
                section_key="discussion",
                nodes=[
                    OutlineNode(
                        node_id="principal_findings",
                        heading="Principal Findings",
                        intent="Interpret the main evidence pattern.",
                        required_citekeys=[],
                        evidence_chunk_ids=[],
                    )
                ],
                grounding_hash="def456",
            ),
        )

        await repo.rollback_phase_data("wf-outline-finalize", "finalize")
        assert set((await repo.load_section_outlines("wf-outline-finalize")).keys()) == {"discussion"}


async def _seed_rollback_contract_rows(repo: WorkflowRepository, db, workflow_id: str) -> None:
    """Seed papers plus downstream screening, extraction, and cohort rows."""
    await repo.create_workflow(workflow_id, "rollback contract topic", "hash")
    await repo.save_paper(
        CandidatePaper(
            paper_id="p-rb-1",
            title="Rollback contract paper",
            authors=["Author"],
            source_database="openalex",
            source_category=SourceCategory.DATABASE,
        )
    )
    await db.execute(
        """
        INSERT INTO search_results
        (database_name, source_category, search_date, search_query, records_retrieved, workflow_id)
        VALUES ('openalex', 'database', '2026-08-10', 'rollback', 1, ?)
        """,
        (workflow_id,),
    )
    await db.execute(
        """
        INSERT INTO screening_decisions
        (workflow_id, paper_id, stage, decision, reviewer_type, confidence)
        VALUES (?, 'p-rb-1', 'title_abstract', 'include', 'reviewer_a', 0.9)
        """,
        (workflow_id,),
    )
    await repo.save_dual_screening_result(
        workflow_id,
        "p-rb-1",
        "title_abstract",
        True,
        ScreeningDecisionType.INCLUDE,
        False,
    )
    await db.execute(
        """
        INSERT INTO study_cohort_membership
        (workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase)
        VALUES (?, 'p-rb-1', 'included_title_abstract', 'pending', 'pending', 'phase_3_screening')
        """,
        (workflow_id,),
    )
    await repo.save_extraction_record(
        workflow_id,
        ExtractionRecord(
            paper_id="p-rb-1",
            study_design=StudyDesign.MIXED_METHODS,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
            participant_count=42,
            intervention_description="Intervention",
            results_summary={"summary": "Improved coverage."},
            extraction_source="openalex_content",
        ),
    )
    await db.execute(
        """
        UPDATE study_cohort_membership
        SET synthesis_eligibility = 'included_primary',
            source_phase = 'phase_4_extraction_quality'
        WHERE workflow_id = ? AND paper_id = 'p-rb-1'
        """,
        (workflow_id,),
    )
    await db.commit()


async def _count_for_workflow(db, table: str, workflow_id: str) -> int:
    row = await (
        await db.execute(f"SELECT COUNT(*) FROM {table} WHERE workflow_id = ?", (workflow_id,))
    ).fetchone()
    return int(row[0])


async def _count_papers(db) -> int:
    row = await (await db.execute("SELECT COUNT(*) FROM papers")).fetchone()
    return int(row[0])


async def _count_cohort_for_source_phase(db, workflow_id: str, source_phase: str) -> int:
    row = await (
        await db.execute(
            """
            SELECT COUNT(*) FROM study_cohort_membership
            WHERE workflow_id = ? AND source_phase = ?
            """,
            (workflow_id, source_phase),
        )
    ).fetchone()
    return int(row[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("from_phase", "expected"),
    [
        (
            "phase_2_search",
            {
                "papers": 0,
                "search_results": 0,
                "screening_decisions": 0,
                "dual_screening_results": 0,
                "extraction_records": 0,
                "cohort_phase_3": 0,
                "cohort_phase_4": 0,
            },
        ),
        (
            "phase_4_extraction_quality",
            {
                "papers": 1,
                "search_results": 1,
                "screening_decisions": 1,
                "dual_screening_results": 1,
                "extraction_records": 0,
                "cohort_phase_3": 0,
                "cohort_phase_4": 0,
            },
        ),
    ],
)
async def test_rollback_phase_data_contract_matrix(
    tmp_path,
    from_phase: str,
    expected: dict[str, int],
) -> None:
    workflow_id = f"wf-rb-{from_phase}"
    async with get_db(str(tmp_path / f"rollback_{from_phase}.db")) as db:
        repo = WorkflowRepository(db)
        await _seed_rollback_contract_rows(repo, db, workflow_id)

        await repo.rollback_phase_data(workflow_id, from_phase)

        assert await _count_papers(db) == expected["papers"]
        assert await _count_for_workflow(db, "search_results", workflow_id) == expected["search_results"]
        assert await _count_for_workflow(db, "screening_decisions", workflow_id) == expected["screening_decisions"]
        assert await _count_for_workflow(db, "dual_screening_results", workflow_id) == expected["dual_screening_results"]
        assert await _count_for_workflow(db, "extraction_records", workflow_id) == expected["extraction_records"]
        assert (
            await _count_cohort_for_source_phase(db, workflow_id, "phase_3_screening")
            == expected["cohort_phase_3"]
        )
        assert (
            await _count_cohort_for_source_phase(db, workflow_id, "phase_4_extraction_quality")
            == expected["cohort_phase_4"]
        )


@pytest.mark.asyncio
async def test_rollback_from_screening_clears_cohort_but_keeps_papers(tmp_path) -> None:
    workflow_id = "wf-rb-phase3"
    async with get_db(str(tmp_path / "rollback_phase3.db")) as db:
        repo = WorkflowRepository(db)
        await _seed_rollback_contract_rows(repo, db, workflow_id)

        await repo.rollback_phase_data(workflow_id, "phase_3_screening")

        assert await _count_papers(db) == 1
        assert await _count_for_workflow(db, "search_results", workflow_id) == 1
        assert await _count_for_workflow(db, "screening_decisions", workflow_id) == 0
        assert await _count_for_workflow(db, "dual_screening_results", workflow_id) == 0
        assert await _count_for_workflow(db, "extraction_records", workflow_id) == 0
        assert await _count_for_workflow(db, "study_cohort_membership", workflow_id) == 0
