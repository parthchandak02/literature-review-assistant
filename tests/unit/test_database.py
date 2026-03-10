from pathlib import Path

import aiosqlite
import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import (
    DecisionLogEntry,
    ManuscriptAssembly,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SectionDraft,
)


@pytest.mark.asyncio
async def test_database_migrations_create_tables(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    async with get_db(str(db_path)) as db:
        assert isinstance(db, aiosqlite.Connection)
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gate_results'")
        row = await cursor.fetchone()
        assert row is not None
        schema_version_row = await (await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")).fetchone()
        assert schema_version_row is not None
        assert int(schema_version_row[0]) >= 8

        cols = await (await db.execute("PRAGMA table_info(cost_records)")).fetchall()
        col_names = {str(r[1]) for r in cols}
        assert "workflow_id" in col_names

        cols2 = await (await db.execute("PRAGMA table_info(extraction_records)")).fetchall()
        col_names2 = {str(r[1]) for r in cols2}
        assert "extraction_source" in col_names2

        cols3 = await (await db.execute("PRAGMA table_info(decision_log)")).fetchall()
        col_names3 = {str(r[1]) for r in cols3}
        assert "workflow_id" in col_names3

        cols4 = await (await db.execute("PRAGMA table_info(manuscript_sections)")).fetchall()
        assert "section_key" in {str(r[1]) for r in cols4}


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


@pytest.mark.asyncio
async def test_failed_search_connectors_filters_by_workflow(tmp_path) -> None:
    db_path = tmp_path / "connector_failures.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.append_decision_log(
            DecisionLogEntry(
                workflow_id="wf-target",
                decision_type="search_connector_error",
                decision="error",
                rationale="OpenAlex: RuntimeError: quota exceeded",
                actor="search",
                phase="phase_2_search",
            )
        )
        await repo.append_decision_log(
            DecisionLogEntry(
                workflow_id="wf-other",
                decision_type="search_connector_error",
                decision="error",
                rationale="Scopus: RuntimeError: bad key",
                actor="search",
                phase="phase_2_search",
            )
        )
        out = await repo.get_failed_search_connectors("wf-target")
        assert out == ["OpenAlex"]


@pytest.mark.asyncio
async def test_save_section_draft_dual_writes_manuscript_tables(tmp_path) -> None:
    db_path = tmp_path / "manuscript_tables.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-manu",
            section="methods",
            version=1,
            content="<!-- SECTION_BLOCK:information_sources -->\n### Information Sources\n\nText body.",
            claims_used=[],
            citations_used=[],
            word_count=6,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=2)
        sections = await repo.load_latest_manuscript_sections("wf-manu")
        assert len(sections) == 1
        assert sections[0].section_key == "methods"
        cur = await db.execute(
            "SELECT COUNT(*) FROM manuscript_blocks WHERE workflow_id=? AND section_key=?",
            ("wf-manu", "methods"),
        )
        row = await cur.fetchone()
        assert row is not None
        assert int(row[0]) >= 2


@pytest.mark.asyncio
async def test_save_manuscript_assembly_validates_manifest_refs(tmp_path) -> None:
    db_path = tmp_path / "assembly_manifest.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-asm",
            section="results",
            version=1,
            content="### Study Selection\n\nBody text.",
            claims_used=[],
            citations_used=[],
            word_count=4,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)
        await repo.save_manuscript_assembly(
            ManuscriptAssembly(
                workflow_id="wf-asm",
                assembly_id="latest",
                target_format="md",
                content="content",
                manifest_json='{"sections":[{"section_key":"results","version":1,"order":0}]}',
            )
        )
        got = await repo.load_latest_manuscript_assembly("wf-asm", "md")
        assert got is not None
        assert got.assembly_id == "latest"


@pytest.mark.asyncio
async def test_validate_manuscript_md_parity(tmp_path) -> None:
    db_path = tmp_path / "parity.db"
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        draft = SectionDraft(
            workflow_id="wf-parity",
            section="discussion",
            version=1,
            content="## Discussion\n\nText [1].",
            claims_used=[],
            citations_used=[],
            word_count=4,
        )
        await repo.save_section_draft(draft)
        await repo.save_manuscript_section_from_draft(draft, section_order=0)
        md = "## Discussion\n\nText [1]."
        await repo.save_manuscript_assembly(
            ManuscriptAssembly(
                workflow_id="wf-parity",
                assembly_id="latest",
                target_format="md",
                content=md,
                manifest_json='{"sections":[{"section_key":"discussion","version":1,"order":0}]}',
            )
        )
        parity = await repo.validate_manuscript_md_parity("wf-parity", md)
        assert parity["has_assembly"] is True
        assert parity["citation_set_match"] is True
