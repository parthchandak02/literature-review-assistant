"""Resume integrity repair for orphaned paper and workflow references.

`load_resume_state` calls `repair_foreign_key_integrity` before it rebuilds the
paper cohort. Old runtime databases can hold screening, extraction, and
checkpoint rows whose parents were never inserted. These tests lock the stub
rows that repair inserts so later foreign-key writes can succeed.
"""

from __future__ import annotations

import aiosqlite
import pytest

from src.db.database import get_db, repair_foreign_key_integrity


async def _set_foreign_keys(db: aiosqlite.Connection, enabled: bool) -> None:
    await db.commit()
    await db.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")


async def _paper_row(db: aiosqlite.Connection, paper_id: str) -> aiosqlite.Row | None:
    cursor = await db.execute(
        """
        SELECT title, authors, source_database, source_category
        FROM papers
        WHERE paper_id = ?
        """,
        (paper_id,),
    )
    return await cursor.fetchone()


async def _workflow_row(db: aiosqlite.Connection, workflow_id: str) -> aiosqlite.Row | None:
    cursor = await db.execute(
        """
        SELECT topic, config_hash, status
        FROM workflows
        WHERE workflow_id = ?
        """,
        (workflow_id,),
    )
    return await cursor.fetchone()


@pytest.mark.asyncio
async def test_repair_returns_zero_when_references_are_intact(tmp_path) -> None:
    db_path = tmp_path / "intact.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO workflows (workflow_id, topic, config_hash, status)
            VALUES ('wf-real', 'Real topic', 'hash', 'completed')
            """
        )
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database)
            VALUES ('p-real', 'Real title', '["Ada"]', 'openalex')
            """
        )
        await db.execute(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES ('wf-real', 'p-real', 'title_abstract', 'include', 'reviewer_a', 0.9)
            """
        )
        await db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status)
            VALUES ('wf-real', 'phase_2_search', 'completed')
            """
        )
        await db.commit()

        inserted = await repair_foreign_key_integrity(db)

        assert inserted == 0
        paper = await _paper_row(db, "p-real")
        assert paper is not None
        assert paper["title"] == "Real title"
        workflow = await _workflow_row(db, "wf-real")
        assert workflow is not None
        assert workflow["status"] == "completed"


@pytest.mark.asyncio
async def test_repair_stubs_each_orphaned_paper_id_once(tmp_path) -> None:
    db_path = tmp_path / "orphan_papers.db"
    async with get_db(str(db_path)) as db:
        await _set_foreign_keys(db, False)
        await db.execute(
            """
            INSERT INTO papers (paper_id, title, authors, source_database)
            VALUES ('p-known', 'Known title', '["Ada"]', 'openalex')
            """
        )
        await db.executemany(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES (?, ?, 'title_abstract', 'include', 'reviewer_a', 0.8)
            """,
            [("wf", "p-screen"), ("wf", "p-shared")],
        )
        await db.execute(
            """
            INSERT INTO extraction_records (workflow_id, paper_id, study_design, data)
            VALUES ('wf', 'p-shared', 'rct', '{}')
            """
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results (
                workflow_id, paper_id, stage, agreement, final_decision
            ) VALUES ('wf', 'p-dual', 'title_abstract', 1, 'include')
            """
        )
        await db.execute(
            """
            INSERT INTO rob_assessments (
                workflow_id, paper_id, tool_used, assessment_data, overall_judgment
            ) VALUES ('wf', 'p-rob', 'rob2', '{}', 'low')
            """
        )
        await db.execute(
            """
            INSERT INTO paper_chunks_meta (chunk_id, workflow_id, paper_id, chunk_index, content)
            VALUES ('chunk-1', 'wf', 'p-chunk', 0, 'excerpt')
            """
        )
        await db.execute(
            """
            INSERT INTO screening_corrections (workflow_id, paper_id, ai_decision, human_decision)
            VALUES ('wf', 'p-correct', 'exclude', 'include')
            """
        )
        await db.execute(
            """
            INSERT INTO paper_relationships (
                workflow_id, source_paper_id, target_paper_id, rel_type
            ) VALUES ('wf', 'p-known', 'p-cited', 'cites')
            """
        )
        await db.commit()
        await _set_foreign_keys(db, True)

        inserted = await repair_foreign_key_integrity(db)

        expected_ids = {
            "p-screen",
            "p-shared",
            "p-dual",
            "p-rob",
            "p-chunk",
            "p-correct",
            "p-cited",
        }
        assert inserted == len(expected_ids)
        known = await _paper_row(db, "p-known")
        assert known is not None
        assert known["title"] == "Known title"
        assert known["source_database"] == "openalex"
        for paper_id in expected_ids:
            stub = await _paper_row(db, paper_id)
            assert stub is not None
            assert stub["title"] == "[Recovered]"
            assert stub["authors"] == "[]"
            assert stub["source_database"] == "integrity_repair"
            assert stub["source_category"] == "database"

        await db.execute(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES ('wf', 'p-screen', 'fulltext', 'exclude', 'reviewer_b', 0.7)
            """
        )
        await db.commit()


@pytest.mark.asyncio
async def test_repair_stubs_orphaned_checkpoint_workflows(tmp_path) -> None:
    db_path = tmp_path / "orphan_workflows.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO workflows (workflow_id, topic, config_hash, status)
            VALUES ('wf-real', 'Kept topic', 'hash', 'completed')
            """
        )
        await db.commit()
        await _set_foreign_keys(db, False)
        await db.executemany(
            """
            INSERT INTO checkpoints (workflow_id, phase, status)
            VALUES (?, 'phase_3_screening', 'completed')
            """,
            [("wf-real",), ("wf-missing",)],
        )
        await db.commit()
        await _set_foreign_keys(db, True)

        inserted = await repair_foreign_key_integrity(db)

        assert inserted == 1
        kept = await _workflow_row(db, "wf-real")
        assert kept is not None
        assert kept["topic"] == "Kept topic"
        assert kept["status"] == "completed"
        stub = await _workflow_row(db, "wf-missing")
        assert stub is not None
        assert stub["topic"] == "[Recovered]"
        assert stub["config_hash"] == ""
        assert stub["status"] == "running"

        await db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status)
            VALUES ('wf-missing', 'phase_4_extraction_quality', 'completed')
            """
        )
        await db.commit()


@pytest.mark.asyncio
async def test_repair_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "idempotent.db"
    async with get_db(str(db_path)) as db:
        await _set_foreign_keys(db, False)
        await db.execute(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES ('wf', 'p-once', 'title_abstract', 'include', 'reviewer_a', 0.5)
            """
        )
        await db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status)
            VALUES ('wf-once', 'phase_2_search', 'completed')
            """
        )
        await db.commit()
        await _set_foreign_keys(db, True)

        first = await repair_foreign_key_integrity(db)
        second = await repair_foreign_key_integrity(db)

        assert first == 2
        assert second == 0
        paper_count = await (await db.execute("SELECT COUNT(*) FROM papers WHERE paper_id = 'p-once'")).fetchone()
        workflow_count = await (
            await db.execute("SELECT COUNT(*) FROM workflows WHERE workflow_id = 'wf-once'")
        ).fetchone()
        assert int(paper_count[0]) == 1
        assert int(workflow_count[0]) == 1


@pytest.mark.asyncio
async def test_repair_skips_blank_ids_and_missing_tables(tmp_path) -> None:
    db_path = tmp_path / "partial_schema.db"
    async with get_db(str(db_path)) as db:
        await _set_foreign_keys(db, False)
        await db.execute(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES ('wf', '', 'title_abstract', 'include', 'reviewer_a', 0.4)
            """
        )
        await db.execute(
            """
            INSERT INTO screening_decisions (
                workflow_id, paper_id, stage, decision, reviewer_type, confidence
            ) VALUES ('wf', 'p-kept', 'title_abstract', 'exclude', 'reviewer_a', 0.4)
            """
        )
        await db.execute(
            """
            INSERT INTO checkpoints (workflow_id, phase, status)
            VALUES ('', 'phase_2_search', 'completed')
            """
        )
        await db.execute("DROP TABLE dual_screening_results")
        await db.commit()
        await _set_foreign_keys(db, True)

        inserted = await repair_foreign_key_integrity(db)

        assert inserted == 1
        assert await _paper_row(db, "") is None
        assert await _paper_row(db, "p-kept") is not None
        assert await _workflow_row(db, "") is None
