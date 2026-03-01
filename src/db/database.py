"""SQLite connection and migration helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


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
