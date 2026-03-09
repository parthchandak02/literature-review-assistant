"""Central workflow registry for resume discovery.

Maps (topic, config_hash) -> (workflow_id, db_path, status) so resume can find
which runtime.db to open without scanning the filesystem.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows_registry (
    workflow_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    db_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    heartbeat_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_registry_topic ON workflows_registry(topic);
CREATE INDEX IF NOT EXISTS idx_registry_topic_hash ON workflows_registry(topic, config_hash);

CREATE TABLE IF NOT EXISTS workflow_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_seq INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO workflow_counter (id, last_seq) VALUES (1, 0);
"""

_MIGRATION_ADD_HEARTBEAT = "ALTER TABLE workflows_registry ADD COLUMN heartbeat_at TEXT"
_MIGRATION_ADD_NOTES = "ALTER TABLE workflows_registry ADD COLUMN notes TEXT"


@asynccontextmanager
async def _open_registry(path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Open the registry DB with WAL mode and a 5 s busy-timeout.

    WAL allows concurrent readers alongside a single writer so note saves never
    block history reads.  busy_timeout lets writers queue instead of immediately
    returning SQLITE_BUSY when another write holds the lock.
    """
    async with aiosqlite.connect(path, timeout=5.0) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA busy_timeout = 5000")
        yield db


@dataclass
class RegistryEntry:
    """Entry in the workflow registry."""

    workflow_id: str
    topic: str
    config_hash: str
    db_path: str
    status: str
    created_at: str
    updated_at: str


def _registry_path(run_root: str) -> str:
    """Return absolute path to the registry db."""
    return str(Path(run_root).resolve() / "workflows_registry.db")


async def _ensure_registry(run_root: str) -> str:
    """Ensure registry db exists with schema, running migrations. Return absolute path."""
    path = _registry_path(run_root)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with _open_registry(path) as db:
        await db.executescript(REGISTRY_SCHEMA)
        # Migration: add heartbeat_at column for existing databases that pre-date the schema change.
        try:
            await db.execute(_MIGRATION_ADD_HEARTBEAT)
        except Exception:
            pass  # Column already exists -- sqlite raises OperationalError, ignore it.
        # Migration: add notes column for per-workflow user annotations.
        try:
            await db.execute(_MIGRATION_ADD_NOTES)
        except Exception:
            pass  # Column already exists -- sqlite raises OperationalError, ignore it.
        # Migration: create sequential counter table for wf-NNNN IDs (existing installs).
        try:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS workflow_counter "
                "(id INTEGER PRIMARY KEY CHECK (id = 1), last_seq INTEGER NOT NULL DEFAULT 0)"
            )
            await db.execute("INSERT OR IGNORE INTO workflow_counter (id, last_seq) VALUES (1, 0)")
        except Exception:
            pass
        await db.commit()
    return path


async def register(
    run_root: str,
    workflow_id: str,
    topic: str,
    config_hash: str,
    db_path: str,
    status: str = "running",
) -> None:
    """Register a workflow in the central registry."""
    path = await _ensure_registry(run_root)
    abs_db_path = str(Path(db_path).resolve())
    async with _open_registry(path) as db:
        await db.execute(
            """
            INSERT INTO workflows_registry
            (workflow_id, topic, config_hash, db_path, status, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(workflow_id) DO UPDATE SET
                topic = excluded.topic,
                config_hash = excluded.config_hash,
                db_path = excluded.db_path,
                status = excluded.status,
                updated_at = datetime('now')
            """,
            (workflow_id, topic, config_hash, abs_db_path, status),
        )
        await db.commit()


async def find_by_workflow_id(run_root: str, workflow_id: str) -> RegistryEntry | None:
    """Find a workflow by ID. Returns None if not found or db_path missing."""
    path = _registry_path(run_root)
    if not os.path.isfile(path):
        return None
    async with _open_registry(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT workflow_id, topic, config_hash, db_path, status, created_at, updated_at
            FROM workflows_registry
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    entry = RegistryEntry(
        workflow_id=str(row["workflow_id"]),
        topic=str(row["topic"]),
        config_hash=str(row["config_hash"]),
        db_path=str(row["db_path"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
    if not os.path.isfile(entry.db_path):
        return None
    return entry


async def find_by_workflow_id_fallback(run_root: str, workflow_id: str) -> RegistryEntry | None:
    """Fallback: scan run_summary.json files under run_root for workflow_id.
    Used when the central registry is missing (e.g. runs from before registry existed).
    """
    root = Path(run_root).resolve()
    if not root.is_dir():
        return None
    for run_summary_path in root.rglob("run_summary.json"):
        try:
            data = json.loads(run_summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("workflow_id") != workflow_id:
            continue
        db_path = str(run_summary_path.parent / "runtime.db")
        if not os.path.isfile(db_path):
            continue
        log_dir = data.get("log_dir") or ""
        topic_slug = log_dir.split("/")[-2] if "/" in log_dir else "unknown"
        return RegistryEntry(
            workflow_id=workflow_id,
            topic=topic_slug,
            config_hash="",
            db_path=str(Path(db_path).resolve()),
            status="completed" if data.get("included_papers") is not None else "running",
            created_at="",
            updated_at="",
        )
    return None


async def find_by_topic(
    run_root: str,
    topic: str,
    config_hash: str | None = None,
) -> list[RegistryEntry]:
    """Find workflows by topic (case-insensitive). Optionally filter by config_hash.
    Returns most recent first (by created_at desc). Excludes entries with missing db_path.
    """
    path = _registry_path(run_root)
    if not os.path.isfile(path):
        return []
    async with _open_registry(path) as db:
        db.row_factory = aiosqlite.Row
        if config_hash:
            cursor = await db.execute(
                """
                SELECT workflow_id, topic, config_hash, db_path, status, created_at, updated_at
                FROM workflows_registry
                WHERE LOWER(topic) = LOWER(?) AND config_hash = ?
                ORDER BY created_at DESC
                """,
                (topic, config_hash),
            )
        else:
            cursor = await db.execute(
                """
                SELECT workflow_id, topic, config_hash, db_path, status, created_at, updated_at
                FROM workflows_registry
                WHERE LOWER(topic) = LOWER(?)
                ORDER BY created_at DESC
                """,
                (topic,),
            )
        rows = await cursor.fetchall()
    entries: list[RegistryEntry] = []
    for row in rows:
        entry = RegistryEntry(
            workflow_id=str(row["workflow_id"]),
            topic=str(row["topic"]),
            config_hash=str(row["config_hash"]),
            db_path=str(row["db_path"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        if os.path.isfile(entry.db_path):
            entries.append(entry)
    return entries


async def update_status(run_root: str, workflow_id: str, status: str) -> None:
    """Update workflow status in registry."""
    path = _registry_path(run_root)
    if not os.path.isfile(path):
        return
    async with _open_registry(path) as db:
        await db.execute(
            """
            UPDATE workflows_registry SET status = ?, updated_at = datetime('now')
            WHERE workflow_id = ?
            """,
            (status, workflow_id),
        )
        await db.commit()


async def update_notes(run_root: str, workflow_id: str, notes: str) -> None:
    """Persist user-authored notes for a workflow.

    Notes are stored in the central registry so they survive across re-runs and
    are included in the /api/history response without opening per-run databases.
    """
    path = await _ensure_registry(run_root)
    async with _open_registry(path) as db:
        await db.execute(
            "UPDATE workflows_registry SET notes = ?, updated_at = datetime('now') WHERE workflow_id = ?",
            (notes, workflow_id),
        )
        await db.commit()


async def update_heartbeat(run_root: str, workflow_id: str) -> None:
    """Stamp heartbeat_at with the current UTC time for a running workflow.

    Called every 60 seconds by a background asyncio task so that the /api/history
    endpoint can detect workflows that are stuck as 'running' after a hard crash.
    """
    path = _registry_path(run_root)
    if not os.path.isfile(path):
        return
    async with _open_registry(path) as db:
        await db.execute(
            "UPDATE workflows_registry SET heartbeat_at = datetime('now') WHERE workflow_id = ?",
            (workflow_id,),
        )
        await db.commit()


async def allocate_workflow_id(run_root: str) -> str:
    """Atomically allocate the next sequential workflow ID (wf-0001, wf-0002, ...).

    Uses BEGIN EXCLUSIVE to make the read-increment-write a single atomic operation,
    preventing duplicate IDs even when two runs start concurrently under PM2.
    Counter is stored in the workflow_counter table in workflows_registry.db.
    """
    path = await _ensure_registry(run_root)
    async with _open_registry(path) as db:
        await db.execute("BEGIN EXCLUSIVE")
        cursor = await db.execute("SELECT last_seq FROM workflow_counter WHERE id = 1")
        row = await cursor.fetchone()
        next_seq = (row[0] if row else 0) + 1
        await db.execute("UPDATE workflow_counter SET last_seq = ? WHERE id = 1", (next_seq,))
        await db.commit()
    return f"wf-{next_seq:04d}"
