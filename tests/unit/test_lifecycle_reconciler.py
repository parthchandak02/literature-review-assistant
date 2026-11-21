"""Unit tests for lifecycle reconciliation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from src.web.lifecycle_reconciler import LifecycleReconciler, _terminal_status_from_done_payload


def _make_reconciler() -> LifecycleReconciler:
    return LifecycleReconciler(
        stale_threshold_seconds=120,
        stale_grace_seconds=120,
        bump_metric=lambda _name: None,
    )


async def _write_done_event_db(db_path: Path, payload: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE event_log (id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, payload TEXT)")
        await db.execute("INSERT INTO event_log (event_type, payload) VALUES ('done', ?)", (payload,))
        await db.commit()


def _row(workflow_id: str, status: str, db_path: Path) -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "status": status,
        "db_path": str(db_path),
        "heartbeat_at": None,
        "updated_at": None,
        "created_at": None,
    }


def test_running_heartbeat_stale_when_no_timestamps() -> None:
    class Row:
        def __getitem__(self, key: str) -> None:
            return None

    assert _make_reconciler().running_heartbeat_stale(Row()) is True


def test_terminal_status_from_done_payload_logs_warning_on_malformed_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="src.web.lifecycle_reconciler"):
        assert _terminal_status_from_done_payload("{not valid json") is None
    assert any("Malformed done event payload" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_collect_terminal_evidence_skips_aiosqlite_when_db_missing(tmp_path: Path) -> None:
    reconciler = _make_reconciler()
    missing_db = tmp_path / "missing_dir" / "runtime.db"

    with patch("src.web.lifecycle_reconciler.aiosqlite.connect") as mock_connect:
        evidence = await reconciler.collect_terminal_evidence(str(missing_db))

    mock_connect.assert_not_called()
    assert evidence["terminal_status"] is None
    assert not missing_db.exists()

    summary_dir = tmp_path / "summary_only"
    summary_dir.mkdir()
    (summary_dir / "run_summary.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    summary_db = summary_dir / "runtime.db"

    with patch("src.web.lifecycle_reconciler.aiosqlite.connect") as mock_connect:
        summary_evidence = await reconciler.collect_terminal_evidence(str(summary_db))

    mock_connect.assert_not_called()
    assert summary_evidence["terminal_status"] == "completed"
    assert summary_evidence["source"] == "run_summary"
    assert not summary_db.exists()


@pytest.mark.asyncio
async def test_collect_terminal_evidence_logs_open_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    corrupt_db = tmp_path / "runtime.db"
    corrupt_db.write_bytes(b"not a sqlite file")

    with caplog.at_level(logging.WARNING, logger="src.web.lifecycle_reconciler"):
        evidence = await _make_reconciler().collect_terminal_evidence(str(corrupt_db))

    assert evidence["terminal_status"] is None
    assert any(str(corrupt_db) in rec.message and "DatabaseError" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_collect_terminal_evidence_logs_query_and_summary_failures(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "runtime.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        await db.commit()
    summary_path = tmp_path / "run_summary.json"
    summary_path.write_text("{corrupt json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="src.web.lifecycle_reconciler"):
        evidence = await _make_reconciler().collect_terminal_evidence(str(db_path))

    assert evidence["terminal_status"] is None
    joined = "\n".join(rec.message for rec in caplog.records)
    assert f"event_log for terminal evidence in {db_path}" in joined
    assert f"workflows table for terminal evidence in {db_path}" in joined
    assert f"checkpoints table for terminal evidence in {db_path}" in joined
    assert f"Failed to read terminal status from {summary_path}" in joined
    assert "JSONDecodeError" in joined


@pytest.mark.asyncio
async def test_collect_terminal_evidence_falls_back_when_event_log_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "runtime.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE workflows (status TEXT, updated_at TEXT)")
        await db.execute("INSERT INTO workflows (status, updated_at) VALUES ('completed', '2026-01-01T00:00:00Z')")
        await db.commit()

    with caplog.at_level(logging.WARNING, logger="src.web.lifecycle_reconciler"):
        evidence = await _make_reconciler().collect_terminal_evidence(str(db_path))

    assert evidence["terminal_status"] == "completed"
    assert evidence["source"] == "workflows_table"
    assert any("event_log" in rec.message and str(db_path) in rec.message for rec in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wf_id", "prior_status", "payload", "expected_status", "expected_source"),
    [
        (
            "wf-parked",
            "running",
            json.dumps({"outputs": {"status": "awaiting_prospero"}}),
            "awaiting_prospero",
            "event_log_parked",
        ),
        ("wf-stale", "stale", "{}", "completed", "event_log"),
    ],
)
async def test_resolve_effective_status_logs_registry_repair_failures(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    wf_id: str,
    prior_status: str,
    payload: str,
    expected_status: str,
    expected_source: str,
) -> None:
    db_path = tmp_path / wf_id / "runtime.db"
    await _write_done_event_db(db_path, payload)
    with (
        patch(
            "src.web.lifecycle_reconciler.update_registry_status",
            new=AsyncMock(side_effect=RuntimeError("registry locked")),
        ),
        caplog.at_level(logging.WARNING, logger="src.web.lifecycle_reconciler"),
    ):
        status, diag = await _make_reconciler().resolve_effective_status(
            _row(wf_id, prior_status, db_path),  # type: ignore[arg-type]
            None,
            str(tmp_path),
            lifecycle_metrics={},
        )
    assert status == expected_status
    assert diag["source"] == expected_source
    assert diag["override"] == f"{prior_status}->{expected_status}"
    assert any(
        wf_id in r.message and f"{prior_status} -> {expected_status}" in r.message and "registry locked" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_resolve_effective_status_logs_actual_prior_status_on_repair(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _write_done_event_db(db_path, "{}")
    with (
        patch("src.web.lifecycle_reconciler.update_registry_status", new=AsyncMock(return_value=None)),
        caplog.at_level(logging.INFO, logger="src.web.lifecycle_reconciler"),
    ):
        status, _ = await _make_reconciler().resolve_effective_status(
            _row("wf-repaired", "stale", db_path),  # type: ignore[arg-type]
            None,
            str(tmp_path),
            lifecycle_metrics={},
        )

    assert status == "completed"
    assert any("workflow wf-repaired status stale -> completed (event_log)" in r.message for r in caplog.records)
