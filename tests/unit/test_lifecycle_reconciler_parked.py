"""Lifecycle reconciler tests for parked PROSPERO/review runs."""

from __future__ import annotations

import json

import pytest

from src.web.lifecycle_reconciler import LifecycleReconciler, _terminal_status_from_done_payload


def test_done_payload_parked_prospero_not_completed() -> None:
    payload = json.dumps(
        {
            "type": "done",
            "outputs": {
                "status": "awaiting_prospero",
                "workflow_id": "wf-0108",
                "db_path": "/tmp/runtime.db",
            },
        }
    )
    assert _terminal_status_from_done_payload(payload) == "awaiting_prospero"


def test_done_payload_without_parked_status_returns_none() -> None:
    payload = json.dumps({"type": "done", "outputs": {"status": "done", "workflow_id": "wf-1"}})
    assert _terminal_status_from_done_payload(payload) is None


@pytest.mark.asyncio
async def test_collect_terminal_evidence_respects_parked_done_event(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    async with __import__("aiosqlite").connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE event_log (
                id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT
            )
            """
        )
        await db.execute(
            "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
            (
                "done",
                json.dumps(
                    {
                        "type": "done",
                        "outputs": {"status": "awaiting_prospero", "workflow_id": "wf-0108"},
                    }
                ),
            ),
        )
        await db.commit()

    reconciler = LifecycleReconciler(
        stale_threshold_seconds=120,
        stale_grace_seconds=120,
        bump_metric=lambda _name: None,
    )
    evidence = await reconciler.collect_terminal_evidence(str(db_path))
    assert evidence["terminal_status"] == "awaiting_prospero"
    assert evidence["source"] == "event_log_parked"
