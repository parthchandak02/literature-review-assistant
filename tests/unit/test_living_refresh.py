"""Unit tests for living review delta pipeline DB merge (Enhancement #6)."""
from __future__ import annotations

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository, merge_papers_from_parent


async def _setup_parent_db(db_path: str, paper_ids: list) -> None:
    """Populate a parent DB with papers and dual_screening_results decisions."""
    async with get_db(db_path) as db:
        await WorkflowRepository(db).create_workflow("wf-parent", "Parent topic", "hash-parent")
        for pid in paper_ids:
            await db.execute(
                """INSERT INTO papers
                   (paper_id, title, abstract, authors, year, doi, url, source_database,
                    display_label, openalex_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, f"Title {pid}", "Abstract.", '["Author A"]',
                 2023, f"10.1234/{pid}", None, "openalex",
                 f"Label {pid}", None),
            )
        await db.commit()
        for pid in paper_ids:
            await db.execute(
                """INSERT INTO dual_screening_results
                   (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
                   VALUES ('wf-parent', ?, 'stage1', 1, 'include', 0)""",
                (pid,),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_merge_copies_papers_and_decisions(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2", "p3"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 3
        cur = await dst_db.execute("SELECT COUNT(*) FROM dual_screening_results")
        assert (await cur.fetchone())[0] == 3


@pytest.mark.asyncio
async def test_merge_is_idempotent(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 2


@pytest.mark.asyncio
async def test_merge_marks_source_as_merged_from_parent(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT source_database FROM papers WHERE paper_id='p1'")
        row = await cur.fetchone()
        assert row is not None and row[0] == "merged_from_parent"


@pytest.mark.asyncio
async def test_merge_skips_papers_already_in_dst(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        await dst_db.execute(
            "INSERT INTO papers (paper_id, title, authors, source_database, year) "
            "VALUES ('p1', 'Pre-existing', '[\"A\"]', 'openalex', 2020)"
        )
        await dst_db.commit()
        await merge_papers_from_parent(parent_db, dst_db)
        cur = await dst_db.execute("SELECT COUNT(*) FROM papers")
        assert (await cur.fetchone())[0] == 2
        cur = await dst_db.execute("SELECT source_database FROM papers WHERE paper_id='p1'")
        row = await cur.fetchone()
        assert row[0] == "openalex"


@pytest.mark.asyncio
async def test_merge_returns_count(tmp_path) -> None:
    parent_db = str(tmp_path / "parent.db")
    dst_path = str(tmp_path / "dst.db")
    await _setup_parent_db(parent_db, ["p1", "p2", "p3"])
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        n = await merge_papers_from_parent(parent_db, dst_db)
        assert n == 3


@pytest.mark.asyncio
async def test_merge_graceful_on_bad_parent_path(tmp_path) -> None:
    dst_path = str(tmp_path / "dst.db")
    async with get_db(dst_path) as dst_db:
        await WorkflowRepository(dst_db).create_workflow("wf-dst", "topic", "hash")
        n = await merge_papers_from_parent("/nonexistent/path/parent.db", dst_db)
        assert n == 0
