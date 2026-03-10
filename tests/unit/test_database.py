from pathlib import Path

import aiosqlite
import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import ReviewerType, ScreeningDecision, ScreeningDecisionType


@pytest.mark.asyncio
async def test_database_migrations_create_tables(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    async with get_db(str(db_path)) as db:
        assert isinstance(db, aiosqlite.Connection)
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gate_results'")
        row = await cursor.fetchone()
        assert row is not None


@pytest.mark.asyncio
async def test_processed_paper_ids_query(tmp_path) -> None:
    db_path = tmp_path / "phase1_ids.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database)
            VALUES ('p1', 't', '["a"]', 'openalex')
            """
        )
        await db.commit()
        await repo.save_screening_decision(
            workflow_id="wf1",
            stage="title_abstract",
            decision=ScreeningDecision(
                paper_id="p1",
                decision=ScreeningDecisionType.INCLUDE,
                reviewer_type=ReviewerType.REVIEWER_A,
                confidence=0.91,
            ),
        )
        processed = await repo.get_processed_paper_ids("wf1", "title_abstract")
        assert processed == {"p1"}


@pytest.mark.asyncio
async def test_get_included_paper_ids_includes_uncertain(tmp_path) -> None:
    """get_included_paper_ids returns papers with include or uncertain at fulltext."""
    db_path = tmp_path / "included_ids.db"
    async with get_db(str(db_path)) as db:
        await db.executescript(Path("src/db/schema.sql").read_text())
        await db.commit()
        repo = WorkflowRepository(db)
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES ('p1', 't1', '[]', 'openalex'), ('p2', 't2', '[]', 'openalex')"
        )
        await db.commit()
        await repo.create_workflow("wf-inc", "topic", "hash")
        await repo.save_dual_screening_result("wf-inc", "p1", "fulltext", True, ScreeningDecisionType.INCLUDE, False)
        await repo.save_dual_screening_result("wf-inc", "p2", "fulltext", True, ScreeningDecisionType.UNCERTAIN, False)
        included = await repo.get_included_paper_ids("wf-inc")
        assert included == {"p1", "p2"}


@pytest.mark.asyncio
async def test_prisma_counts_assessed_falls_back_to_sought_minus_not_retrieved(tmp_path) -> None:
    """reports_assessed should not collapse to 0 when fulltext rows are sparse."""
    db_path = tmp_path / "prisma_counts.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow("wf-prisma", "topic", "hash")
        # papers table rows for FK integrity
        await db.executemany(
            "INSERT INTO papers (paper_id, title, authors, source_database) VALUES (?, ?, ?, ?)",
            [
                ("p1", "t1", "[]", "openalex"),
                ("p2", "t2", "[]", "openalex"),
                ("p3", "t3", "[]", "openalex"),
            ],
        )
        # title/abstract: all 3 included -> fulltext sought = 3
        await db.executemany(
            "INSERT INTO dual_screening_results (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("wf-prisma", "p1", "title_abstract", 1, "include", 0),
                ("wf-prisma", "p2", "title_abstract", 1, "include", 0),
                ("wf-prisma", "p3", "title_abstract", 1, "include", 0),
            ],
        )
        # fulltext-stage rows are absent/sparse, but one no_full_text exclusion exists.
        await db.execute(
            """
            INSERT INTO screening_decisions
                (workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("wf-prisma", "p1", "fulltext", "exclude", "no pdf", "no_full_text", "adjudicator", 0.9),
        )
        await db.commit()

        screened, excluded, sought, not_retrieved, assessed, reasons = await repo.get_prisma_screening_counts(
            "wf-prisma"
        )
        assert screened == 3
        assert excluded == 0
        assert sought == 3
        assert not_retrieved == 1
        assert assessed == 2
        assert reasons == {}
