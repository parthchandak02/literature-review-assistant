"""Durability guarantees for EventStore flush/persist behavior."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest

from src.db.database import get_db
from src.web.event_store import DURABLE_EVENT_TYPES, EventStore


@dataclass
class _StubRecord:
    event_log: list[dict] = field(default_factory=list)
    _flush_index: int = 0
    _flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _event_cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    db_path: str | None = None
    workflow_id: str | None = None


async def _init_runtime_db(db_path: Path, workflow_id: str) -> None:
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "durability-test", "hash", "running"),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_persist_raises_on_db_failure(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    await _init_runtime_db(db_path, "wf-persist-fail")

    with patch("src.web.event_store.open_runtime_db", side_effect=RuntimeError("db locked")):
        with pytest.raises(RuntimeError, match="db locked"):
            await store.persist(str(db_path), "wf-persist-fail", [{"type": "phase_start", "ts": "t0"}])


@pytest.mark.asyncio
async def test_flush_index_not_advanced_when_persist_fails(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-flush-fail"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    record.event_log.append({"type": "phase_start", "phase": "phase_1", "ts": "t0"})

    with patch("src.web.event_store.open_runtime_db", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError, match="write failed"):
            await store.flush_pending(record)

    assert record._flush_index == 0

    await store.flush_pending(record)
    assert record._flush_index == 1

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM event_log WHERE workflow_id=?", (workflow_id,))).fetchone()
    assert row is not None
    assert int(row[0]) == 1


@pytest.mark.asyncio
async def test_append_schedules_tracked_flush_task(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-tracked-flush"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    store.append(record, {"type": "phase_start", "phase": "phase_1"})

    await store.await_pending_flushes(record, timeout=5.0)
    assert record._flush_index == 1

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (
            await db.execute(
                "SELECT event_type, payload FROM event_log WHERE workflow_id=?",
                (workflow_id,),
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "phase_start"
    payload = json.loads(row[1])
    assert payload["phase"] == "phase_1"


@pytest.mark.asyncio
async def test_failed_flush_retries_on_next_flush(tmp_path: Path) -> None:
    store = EventStore()
    db_path = tmp_path / "runtime.db"
    workflow_id = "wf-retry"
    await _init_runtime_db(db_path, workflow_id)

    record = _StubRecord(db_path=str(db_path), workflow_id=workflow_id)
    record.event_log.extend(
        [
            {"type": "phase_start", "phase": "phase_1", "ts": "t0"},
            {"type": "phase_done", "phase": "phase_1", "ts": "t1"},
        ]
    )

    call_count = 0
    real_open = store.persist

    async def flaky_persist(db_path_arg: str, workflow_id_arg: str, events: list[dict]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient failure")
        await real_open(db_path_arg, workflow_id_arg, events)

    with patch.object(store, "persist", side_effect=flaky_persist):
        with pytest.raises(RuntimeError, match="transient failure"):
            await store.flush_pending(record)
        assert record._flush_index == 0

        await store.flush_pending(record)
        assert record._flush_index == 2

    async with aiosqlite.connect(str(db_path)) as db:
        row = await (await db.execute("SELECT COUNT(*) FROM event_log WHERE workflow_id=?", (workflow_id,))).fetchone()
    assert row is not None
    assert int(row[0]) == 2


def test_durable_event_types_include_terminal_markers() -> None:
    assert {"done", "error", "cancelled", "phase_start", "phase_done"}.issubset(DURABLE_EVENT_TYPES)
