"""Attach must not render gate statuses (config_ready, awaiting_*) as errors."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from src.db.database import get_db
from src.web.app import _active_runs, app
from src.web.lifecycle_coordinator import attach_status_event

_TS = "2026-09-28T00:00:00+00:00"


@pytest.mark.parametrize(
    "status",
    ["config_ready", "config_generating", "awaiting_prospero", "awaiting_review"],
)
def test_gate_statuses_emit_status_event(status: str) -> None:
    event = attach_status_event(status, _TS)
    assert event["type"] == "status"
    assert event["message"]
    assert "ended" not in event["message"].lower()


def test_needs_revision_emits_warn_event_with_message() -> None:
    event = attach_status_event("needs_revision", _TS)
    assert event["type"] == "warn"
    assert "audit failed" in event["message"]


@pytest.mark.parametrize("status", ["failed", "interrupted", "gate_blocked"])
def test_failure_statuses_still_emit_error(status: str) -> None:
    event = attach_status_event(status, _TS)
    assert event == {"type": "error", "msg": f"Run ended with status: {status}", "ts": _TS}


def test_stale_status_reports_orphan_error() -> None:
    event = attach_status_event("stale", _TS)
    assert event["type"] == "error"
    assert "orphaned" in event["msg"]


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_attach_config_ready_has_no_error_event(client: httpx.AsyncClient, tmp_path: Path) -> None:
    workflow_id = "wf-attach-config-ready"
    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "config_ready"),
        )
        await db.commit()

    payload = {"workflow_id": workflow_id, "topic": "Topic", "db_path": str(db_path), "status": "config_ready"}
    try:
        resp = await client.post("/api/history/attach", json=payload)
        assert resp.status_code == 200
        record = _active_runs[resp.json()["run_id"]]
        assert record.error is None
        assert [e["type"] for e in record.event_log] == ["status"]
    finally:
        for run_id in list(_active_runs):
            if _active_runs[run_id].workflow_id == workflow_id:
                _active_runs.pop(run_id, None)
