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
