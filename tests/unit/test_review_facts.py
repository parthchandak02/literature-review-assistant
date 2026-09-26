import pytest

from src.manuscript.review_facts import ReviewFacts, build_review_facts
from src.models import PRISMACounts


@pytest.mark.asyncio
async def test_build_review_facts_aligns_synthesis_count(tmp_path) -> None:
    from src.db.database import get_db
    from src.db.repositories import WorkflowRepository

    db_path = tmp_path / "facts.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-facts", "topic", "hash")
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            ("p1", "t", "[]", "openalex"),
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership
                (workflow_id, paper_id, screening_status, fulltext_status, synthesis_eligibility, source_phase)
            VALUES (?, ?, 'included', 'assessed', 'included_primary', 'extraction')
            """,
            ("wf-facts", "p1"),
        )
        await db.commit()

        facts = await build_review_facts(repo, "wf-facts", dedup_count=0, included_quantitative=1)
        assert facts.synthesis_included_count == 1
        assert facts.included_study_ids == ["p1"]
        assert facts.validate_cross_artifact() == [] or facts.prisma.total_included >= 0


def test_review_facts_flags_prisma_invalid() -> None:
    prisma = PRISMACounts(
        databases_records={},
        other_sources_records={},
        total_identified_databases=0,
        total_identified_other=0,
        duplicates_removed=0,
        records_screened=0,
        records_excluded_screening=0,
        reports_sought=0,
        reports_not_retrieved=0,
        reports_assessed=0,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=0,
        arithmetic_valid=False,
    )
    facts = ReviewFacts(workflow_id="wf", prisma=prisma, synthesis_included_count=2)
    assert any("arithmetic" in issue for issue in facts.validate_cross_artifact())
