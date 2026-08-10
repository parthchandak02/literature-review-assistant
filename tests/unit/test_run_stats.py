"""Unit tests for RunStatsResolver."""

from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.stats import RunStatsResolver


@pytest.mark.asyncio
async def test_papers_included_prefers_cohort_membership(tmp_path) -> None:
    db_path = tmp_path / "stats.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES ('wf1', 't', 'h', 'running')"
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database)
            VALUES ('p1', 'Paper', '["A"]', 'openalex')
            """
        )
        await db.execute(
            """
            INSERT INTO study_cohort_membership (
                workflow_id, paper_id, screening_status, fulltext_status,
                synthesis_eligibility, source_phase
            ) VALUES ('wf1', 'p1', 'included', 'retrieved', 'included_primary', 'phase_3_screening')
            """
        )
        await db.commit()

        resolver = RunStatsResolver()
        included = await resolver.papers_included(db, workflow_id="wf1")
        assert included.count == 1
        assert included.source_key == "study_cohort_membership_synthesis_included_primary"


@pytest.mark.asyncio
async def test_papers_included_prefers_primary_extraction_over_dual_when_cohort_missing(tmp_path) -> None:
    db_path = tmp_path / "stats_extraction_primary.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES ('wf1', 't', 'h', 'completed')"
        )
        for idx, status in enumerate(["primary", "primary", "secondary_review"], start=1):
            paper_id = f"p{idx}"
            await db.execute(
                "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
                (paper_id, f"Paper {idx}", '["A"]', "openalex"),
            )
            await db.execute(
                """
                INSERT INTO dual_screening_results (
                    workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
                ) VALUES ('wf1', ?, 'fulltext', 1, 'include', 0)
                """,
                (paper_id,),
            )
            await db.execute(
                """
                INSERT INTO extraction_records (workflow_id, paper_id, study_design, primary_study_status, data)
                VALUES ('wf1', ?, 'rct', ?, ?)
                """,
                (paper_id, status, f'{{"primary_study_status": "{status}"}}'),
            )
        await db.commit()

        resolver = RunStatsResolver()
        included = await resolver.papers_included(db, workflow_id="wf1")
        assert included.count == 2
        assert included.source_key == "extraction_records_primary"


@pytest.mark.asyncio
async def test_papers_included_counts_unknown_primary_study_status_as_primary(tmp_path) -> None:
    """Column default 'unknown' is not a non-primary exclusion status."""
    db_path = tmp_path / "stats_unknown.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES ('wf1', 't', 'h', 'completed')"
        )
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES ('p1', 'Paper', ?, 'openalex')",
            ('["A"]',),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed
            ) VALUES ('wf1', 'p1', 'fulltext', 1, 'include', 0)
            """
        )
        await db.execute(
            """
            INSERT INTO extraction_records (workflow_id, paper_id, study_design, primary_study_status, data)
            VALUES ('wf1', 'p1', 'rct', 'unknown', '{}')
            """
        )
        await db.commit()

        resolver = RunStatsResolver()
        included = await resolver.papers_included(db, workflow_id="wf1")
        assert included.count == 1
        assert included.source_key == "extraction_records_primary"


@pytest.mark.asyncio
async def test_total_cost_sums_cost_records(tmp_path) -> None:
    db_path = tmp_path / "costs.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO cost_records (
                workflow_id, model, phase, tokens_in, tokens_out, cost_usd, latency_ms
            ) VALUES ('wf1', 'google:gemini-2.5-flash', 'phase_2_search', 10, 5, 0.25, 100)
            """
        )
        await db.commit()
        resolver = RunStatsResolver()
        assert await resolver.total_cost(db) == pytest.approx(0.25)
