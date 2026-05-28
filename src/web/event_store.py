"""Persist and replay run activity events."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import uuid
from typing import Any, Protocol

import aiosqlite

from src.db.database import open_runtime_db

_logger = logging.getLogger(__name__)

DURABLE_EVENT_TYPES = frozenset(
    {
        "phase_start",
        "phase_done",
        "done",
        "error",
        "cancelled",
        "workflow_id_ready",
        "db_ready",
    }
)


class EventRecord(Protocol):
    event_log: list[dict[str, Any]]
    _flush_index: int
    _flush_lock: asyncio.Lock
    _event_cond: asyncio.Condition
    db_path: str | None
    workflow_id: str | None


class EventStore:
    """Canonical ReviewEvent persistence to SQLite event_log."""

    async def persist(self, db_path: str, workflow_id: str, events: list[dict[str, Any]]) -> None:
        if not events or not workflow_id:
            return
        try:
            async with open_runtime_db(db_path) as db:
                await db.executemany(
                    "INSERT INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
                    [
                        (
                            workflow_id,
                            e.get("type", "unknown"),
                            json.dumps(e, default=str),
                            str(e.get("ts", "")),
                        )
                        for e in events
                    ],
                )
                await db.commit()
        except Exception as exc:
            _logger.warning(
                "Failed to persist event_log for workflow=%s db=%s: %s",
                workflow_id,
                db_path,
                exc,
            )

    async def load(self, db_path: str) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT id, payload, ts FROM event_log ORDER BY id ASC") as cur:
                    rows = await cur.fetchall()
            events: list[dict[str, Any]] = []
            for row in rows:
                event = json.loads(row["payload"])
                if not event.get("id"):
                    event["id"] = f"db-{row['id']}"
                if not event.get("ts"):
                    event["ts"] = str(row["ts"] or "")
                events.append(event)
            return events
        except Exception:
            return []

    async def notify(self, record: EventRecord) -> None:
        async with record._event_cond:
            record._event_cond.notify_all()

    async def flush_pending(self, record: EventRecord) -> None:
        if not (record.db_path and record.workflow_id):
            return
        async with record._flush_lock:
            new = record.event_log[record._flush_index :]
            if not new:
                return
            await self.persist(record.db_path, record.workflow_id, new)
            record._flush_index += len(new)

    def append(self, record: EventRecord, event: dict[str, Any]) -> None:
        if not event.get("id"):
            event["id"] = f"evt-{uuid.uuid4().hex}"
        if not event.get("ts"):
            event["ts"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        event_type = str(event.get("type") or "")
        event["durability"] = "durable" if event_type in DURABLE_EVENT_TYPES else "eventual"
        record.event_log.append(event)
        try:
            asyncio.create_task(self.notify(record))
        except Exception:
            pass
        if event_type in DURABLE_EVENT_TYPES:
            try:
                asyncio.create_task(self.flush_pending(record))
            except Exception:
                pass
