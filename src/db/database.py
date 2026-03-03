"""SQLite connection and migration helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_logger = logging.getLogger(__name__)


async def _init_connection(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA cache_size = 10000")
    await db.execute("PRAGMA temp_store = MEMORY")


async def run_migrations(db: aiosqlite.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    await db.executescript(schema_sql)
    await db.commit()
    # Migration: add country column to papers if missing (existing databases)
    try:
        await db.execute("ALTER TABLE papers ADD COLUMN country TEXT")
        await db.commit()
    except Exception:
        pass
    # Migration: add display_label column to papers (canonical human-readable label)
    try:
        await db.execute("ALTER TABLE papers ADD COLUMN display_label TEXT")
        await db.commit()
    except Exception:
        pass
    # Migration: add dedup_count column to workflows
    try:
        await db.execute("ALTER TABLE workflows ADD COLUMN dedup_count INTEGER")
        await db.commit()
    except Exception:
        pass
    # Migration: add event_log table for SSE event replay on existing databases
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                ts TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_log_workflow ON event_log(workflow_id)"
        )
        await db.commit()
    except Exception:
        pass
    # Migration: add extraction_source column to extraction_records (Idea 2)
    try:
        await db.execute(
            "ALTER TABLE extraction_records ADD COLUMN extraction_source TEXT DEFAULT 'text'"
        )
        await db.commit()
    except Exception:
        pass
    # Migration: add paper_chunks_meta table (Idea 1 - RAG)
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paper_chunks_meta (
                chunk_id    TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                paper_id    TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content     TEXT NOT NULL,
                embedding   TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_workflow ON paper_chunks_meta(workflow_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_paper ON paper_chunks_meta(paper_id)"
        )
        await db.commit()
    except Exception:
        pass
    # Migration: add screening_corrections and learned_criteria (Idea 4 - Active Learning)
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS screening_corrections (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id     TEXT NOT NULL,
                paper_id        TEXT NOT NULL,
                ai_decision     TEXT NOT NULL,
                human_decision  TEXT NOT NULL,
                human_reason    TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS learned_criteria (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id     TEXT NOT NULL,
                criterion_type  TEXT NOT NULL,
                criterion_text  TEXT NOT NULL,
                source_paper_ids TEXT,
                version         INTEGER DEFAULT 1,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_corrections_workflow ON screening_corrections(workflow_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_criteria_workflow ON learned_criteria(workflow_id)"
        )
        await db.commit()
    except Exception:
        pass
    # Migration: add knowledge graph tables (Idea 5)
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paper_relationships (
                workflow_id     TEXT NOT NULL,
                source_paper_id TEXT NOT NULL,
                target_paper_id TEXT NOT NULL,
                rel_type        TEXT NOT NULL,
                weight          REAL,
                PRIMARY KEY (workflow_id, source_paper_id, target_paper_id, rel_type),
                FOREIGN KEY (source_paper_id) REFERENCES papers(paper_id),
                FOREIGN KEY (target_paper_id) REFERENCES papers(paper_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS graph_communities (
                workflow_id     TEXT NOT NULL,
                community_id    INTEGER NOT NULL,
                paper_ids       TEXT NOT NULL,
                label           TEXT,
                PRIMARY KEY (workflow_id, community_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS research_gaps (
                gap_id          TEXT PRIMARY KEY,
                workflow_id     TEXT NOT NULL,
                description     TEXT NOT NULL,
                related_paper_ids TEXT,
                gap_type        TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_gaps_workflow ON research_gaps(workflow_id)"
        )
        await db.commit()
    except Exception:
        pass


async def repair_foreign_key_integrity(db: aiosqlite.Connection) -> int:
    """Insert stub papers for orphaned paper_id references and stub workflows for
    orphaned workflow_id references. Returns count of stubs inserted.

    Old DBs may have screening_decisions, extraction_records, checkpoints, etc.
    referencing paper_ids or workflow_ids not in papers/workflows (e.g. from
    migration or corruption). This causes FOREIGN KEY constraint failed on INSERT.
    We insert minimal stub rows.
    """
    cursor = await db.execute("SELECT paper_id FROM papers")
    existing_papers = {str(row[0]) for row in await cursor.fetchall()}
    missing_papers: set[str] = set()

    async def collect_paper_ids(query: str, col_idx: int = 0) -> None:
        try:
            cur = await db.execute(query)
            for row in await cur.fetchall():
                pid = str(row[col_idx]) if row else None
                if pid and pid not in existing_papers:
                    missing_papers.add(pid)
        except Exception as e:
            _logger.debug("repair_foreign_key_integrity: skip query %s: %s", query[:50], e)

    await collect_paper_ids("SELECT DISTINCT paper_id FROM screening_decisions")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM dual_screening_results")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM extraction_records")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM paper_chunks_meta")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM screening_corrections")
    await collect_paper_ids("SELECT DISTINCT paper_id FROM rob_assessments")
    await collect_paper_ids("SELECT DISTINCT source_paper_id FROM paper_relationships", 0)
    await collect_paper_ids("SELECT DISTINCT target_paper_id FROM paper_relationships", 0)

    inserted = 0
    for pid in missing_papers:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO papers
                (paper_id, title, authors, source_database, source_category)
                VALUES (?, '[Recovered]', '[]', 'integrity_repair', 'database')
                """,
                (pid,),
            )
            inserted += 1
        except Exception as e:
            _logger.warning("repair_foreign_key_integrity: could not insert stub paper %s: %s", pid, e)

    # Stub workflows for orphaned workflow_id refs (e.g. checkpoints referencing
    # workflows that were never created or were deleted).
    try:
        cur = await db.execute("SELECT workflow_id FROM workflows")
        existing_workflows = {str(row[0]) for row in await cur.fetchall()}
        missing_workflows: set[str] = set()
        for (table, col) in [("checkpoints", "workflow_id")]:
            try:
                cur = await db.execute(f"SELECT DISTINCT {col} FROM {table}")
                for row in await cur.fetchall():
                    wid = str(row[0]) if row else None
                    if wid and wid not in existing_workflows:
                        missing_workflows.add(wid)
            except Exception as e:
                _logger.debug("repair_foreign_key_integrity: skip %s.%s: %s", table, col, e)
        for wid in missing_workflows:
            try:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO workflows (workflow_id, topic, config_hash, status)
                    VALUES (?, '[Recovered]', '', 'running')
                    """,
                    (wid,),
                )
                inserted += 1
            except Exception as e:
                _logger.warning("repair_foreign_key_integrity: could not insert stub workflow %s: %s", wid, e)
    except Exception as e:
        _logger.debug("repair_foreign_key_integrity: workflow stub phase skipped: %s", e)

    if inserted:
        await db.commit()
        _logger.info("repair_foreign_key_integrity: inserted %d stub rows for orphaned refs", inserted)
    return inserted


@asynccontextmanager
async def get_db(db_path: str = "data/checkpoints/review_state.db") -> AsyncIterator[aiosqlite.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(path))
    try:
        db.row_factory = aiosqlite.Row
        await _init_connection(db)
        await run_migrations(db)
        yield db
    finally:
        await db.close()
