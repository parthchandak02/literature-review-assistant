"""Unit tests for IncludedSetResolver: canonical cohort membership transitions."""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.manuscript.cohort import IncludedSetResolver
from src.models import CandidatePaper, SourceCategory

WF = "wf-cohort"


def _paper(paper_id: str = "p1") -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Smith"],
        year=2024,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
    )


@pytest.fixture
async def cohort_repo(tmp_path):
    async with get_db(str(tmp_path / "cohort.db")) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(WF, "topic", "hash")
        yield repo


async def _ensure_papers(repo: WorkflowRepository, *paper_ids: str) -> IncludedSetResolver:
    for paper_id in paper_ids:
        await repo.save_paper(_paper(paper_id))
    return IncludedSetResolver(repo, WF)


async def _row(repo: WorkflowRepository, paper_id: str) -> tuple[str, str, str, str | None]:
    cursor = await repo.db.execute(
        """
        SELECT screening_status, fulltext_status, synthesis_eligibility, exclusion_reason_code
        FROM study_cohort_membership
        WHERE workflow_id = ? AND paper_id = ?
        """,
        (WF, paper_id),
    )
    row = await cursor.fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), str(row[2]), row[3]


@pytest.mark.asyncio
async def test_screening_include_marks_pending_synthesis(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome("p1", fulltext_decision="include")
    screening, fulltext, eligibility, reason = await _row(cohort_repo, "p1")
    assert (screening, fulltext, eligibility, reason) == ("included", "assessed", "pending", None)


@pytest.mark.asyncio
async def test_screening_uncertain_treated_as_included_pending(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome("p1", fulltext_decision="uncertain")
    screening, fulltext, eligibility, reason = await _row(cohort_repo, "p1")
    assert (screening, fulltext, eligibility, reason) == ("included", "assessed", "pending", None)


@pytest.mark.asyncio
async def test_screening_exclude_records_reason_and_status(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome(
        "p1",
        fulltext_decision="exclude",
        exclusion_reason_code="wrong_population",
    )
    screening, fulltext, eligibility, reason = await _row(cohort_repo, "p1")
    assert (screening, fulltext, eligibility, reason) == (
        "excluded",
        "assessed",
        "excluded_screening",
        "wrong_population",
    )


@pytest.mark.asyncio
async def test_screening_exclude_defaults_reason_when_omitted(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome("p1", fulltext_decision="exclude")
    _, _, eligibility, reason = await _row(cohort_repo, "p1")
    assert eligibility == "excluded_screening"
    assert reason == "screening_excluded"


@pytest.mark.asyncio
async def test_screening_no_full_text_sets_not_retrieved(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome(
        "p1",
        fulltext_decision="exclude",
        exclusion_reason_code="no_full_text",
    )
    screening, fulltext, eligibility, reason = await _row(cohort_repo, "p1")
    assert (screening, fulltext, eligibility, reason) == (
        "excluded",
        "not_retrieved",
        "excluded_screening",
        "no_full_text",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary_study_status", "expected_eligibility"),
    [
        ("secondary_review", "excluded_non_primary"),
        ("protocol_only", "excluded_non_primary"),
        ("non_empirical", "excluded_non_primary"),
    ],
)
async def test_extraction_excludes_non_primary_designs(
    cohort_repo, primary_study_status: str, expected_eligibility: str
) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_extraction_outcome(
        "p1",
        primary_study_status=primary_study_status,
        extraction_failed=False,
        scope_mismatch=True,
        low_quality=True,
    )
    screening, fulltext, eligibility, reason = await _row(cohort_repo, "p1")
    assert screening == "included"
    assert fulltext == "assessed"
    assert eligibility == expected_eligibility
    assert reason == primary_study_status


@pytest.mark.asyncio
async def test_extraction_failed_marks_excluded_failed_extraction(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_extraction_outcome(
        "p1",
        primary_study_status="primary",
        extraction_failed=True,
    )
    _, _, eligibility, reason = await _row(cohort_repo, "p1")
    assert eligibility == "excluded_failed_extraction"
    assert reason == "failed_extraction"


@pytest.mark.asyncio
async def test_extraction_success_marks_included_primary(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_extraction_outcome(
        "p1",
        primary_study_status="primary",
        extraction_failed=False,
    )
    _, _, eligibility, reason = await _row(cohort_repo, "p1")
    assert eligibility == "included_primary"
    assert reason is None


@pytest.mark.asyncio
async def test_get_synthesis_included_ids_only_primary(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1", "p2", "p3")
    await resolver.persist_extraction_outcome("p1", primary_study_status="primary", extraction_failed=False)
    await resolver.persist_extraction_outcome("p2", primary_study_status="secondary_review", extraction_failed=False)
    await resolver.persist_extraction_outcome(
        "p3",
        primary_study_status="primary",
        extraction_failed=False,
        low_quality=True,
        exclusion_reason_code="low_quality_mmat",
    )
    included = await resolver.get_synthesis_included_ids()
    assert included == {"p1"}


@pytest.mark.asyncio
async def test_screening_then_extraction_updates_same_membership_row(cohort_repo) -> None:
    resolver = await _ensure_papers(cohort_repo, "p1")
    await resolver.persist_screening_outcome("p1", fulltext_decision="include")
    await resolver.persist_extraction_outcome(
        "p1",
        primary_study_status="primary",
        extraction_failed=False,
    )
    cursor = await cohort_repo.db.execute(
        "SELECT COUNT(*) FROM study_cohort_membership WHERE workflow_id = ?",
        (WF,),
    )
    count = (await cursor.fetchone())[0]
    _, _, eligibility, reason = await _row(cohort_repo, "p1")
    included = await resolver.get_synthesis_included_ids()
    assert count == 1
    assert eligibility == "included_primary"
    assert reason is None
    assert included == {"p1"}
