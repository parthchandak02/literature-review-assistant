"""Persist and replay run activity events."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import uuid
from typing import Any, Protocol

import aiosqlite

from src.db.database import connect_sqlite, open_runtime_db

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

    def __init__(self) -> None:
        self._flush_tasks: dict[int, set[asyncio.Task[None]]] = {}

    async def persist(self, db_path: str, workflow_id: str, events: list[dict[str, Any]]) -> None:
        if not events or not workflow_id:
            return
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

    def _register_flush_task(
        self,
        record: EventRecord,
        task: asyncio.Task[None],
        *,
        task_name: str = "background",
    ) -> None:
        key = id(record)
        tasks = self._flush_tasks.setdefault(key, set())
        tasks.add(task)

        def _on_done(done_task: asyncio.Task[None]) -> None:
            bucket = self._flush_tasks.get(key)
            if bucket is not None:
                bucket.discard(done_task)
                if not bucket:
                    self._flush_tasks.pop(key, None)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                _logger.warning(
                    "EventStore %s task failed (workflow_id=%s, db_path=%s): %s",
                    task_name,
                    record.workflow_id,
                    record.db_path,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

        task.add_done_callback(_on_done)

    async def await_pending_flushes(
        self,
        record: EventRecord,
        *,
        timeout: float | None = None,
    ) -> None:
        """Wait for in-flight durable-event flush tasks for ``record``."""
        key = id(record)
        pending = set(self._flush_tasks.get(key, set()))
        if not pending:
            return
        coro = asyncio.gather(*pending, return_exceptions=True)
        if timeout is None:
            await coro
        else:
            await asyncio.wait_for(coro, timeout=timeout)

    async def drain_all_flushes(
        self,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        timeout: float = 2.0,
    ) -> None:
        """Await all pending flush tasks on the specified event loop."""
        target_loop = loop or asyncio.get_running_loop()
        pending = [
            task
            for bucket in list(self._flush_tasks.values())
            for task in list(bucket)
            if not task.done() and task.get_loop() is target_loop
        ]
        if not pending:
            return
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
        except TimeoutError:
            _logger.warning(
                "EventStore drain_all_flushes timed out after %.2fs waiting for %d task(s); cancelling remaining",
                timeout,
                len(pending),
            )
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def load(self, db_path: str) -> list[dict[str, Any]]:
        try:
            async with connect_sqlite(db_path) as db:
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
        except Exception as exc:
            _logger.warning(
                "EventStore failed to load event_log from db_path=%s: %s",
                db_path,
                exc,
                exc_info=True,
            )
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

    def _log_schedule_failure(
        self,
        task_name: str,
        record: EventRecord,
        event_type: str,
        exc: Exception,
    ) -> None:
        if isinstance(exc, RuntimeError) and "no running event loop" in str(exc).lower():
            _logger.debug(
                "EventStore skipped %s scheduling (no running event loop; workflow_id=%s, event_type=%s)",
                task_name,
                record.workflow_id,
                event_type,
            )
            return
        _logger.warning(
            "EventStore failed to schedule %s task (workflow_id=%s, db_path=%s, event_type=%s): %s",
            task_name,
            record.workflow_id,
            record.db_path,
            event_type,
            exc,
            exc_info=True,
        )

    def append(self, record: EventRecord, event: dict[str, Any]) -> None:
        if not event.get("id"):
            event["id"] = f"evt-{uuid.uuid4().hex}"
        if not event.get("ts"):
            event["ts"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        event_type = str(event.get("type") or "")
        event["durability"] = "durable" if event_type in DURABLE_EVENT_TYPES else "eventual"
        record.event_log.append(event)
        notify_coro = self.notify(record)
        try:
            # Keep a strong ref so the waiter wake-up is not GC'd mid-flight (RUF006).
            notify_task = asyncio.create_task(notify_coro)
            self._register_flush_task(record, notify_task, task_name="notify")
        except Exception as exc:
            if hasattr(notify_coro, "close"):
                notify_coro.close()
            self._log_schedule_failure("notify", record, event_type, exc)
        if event_type in DURABLE_EVENT_TYPES:
            flush_coro = self.flush_pending(record)
            try:
                task = asyncio.create_task(flush_coro)
                self._register_flush_task(record, task, task_name="flush_pending")
            except Exception as exc:
                if hasattr(flush_coro, "close"):
                    flush_coro.close()
                self._log_schedule_failure("flush_pending", record, event_type, exc)
