"""Tests for contextual warning logs on error paths in RunLifecycleCoordinator.attach_history."""

from __future__ import annotations

import logging
import pathlib

import pytest
from fastapi import HTTPException

from src.db.database import get_db
from src.web import lifecycle_coordinator as coordinator_mod
from src.web.lifecycle_coordinator import RunLifecycleCoordinator
from src.web.path_guard import RUNS_ROOTS_ENV
from src.web.shared import AttachRequest


async def _seed_runtime_db(db_path: pathlib.Path, workflow_id: str, status: str = "completed") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", status),
        )
        await db.commit()


@pytest.fixture
def isolated_runs_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(RUNS_ROOTS_ENV, raising=False)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    monkeypatch.setattr("src.web.state._allowed_roots", set())
    monkeypatch.setattr(coordinator_mod, "schedule_runtime_db_manuscript_backfill", lambda _p: None)
    return runs_dir.resolve()


@pytest.mark.asyncio
async def test_attach_history_logs_warning_on_corrupt_run_summary(
    isolated_runs_root: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_id = "wf-corrupt-summary"
    db_path = isolated_runs_root / workflow_id / "runtime.db"
    await _seed_runtime_db(db_path, workflow_id, status="completed")
    summary_path = db_path.parent / "run_summary.json"
    summary_path.write_text("{not valid json", encoding="utf-8")

    coordinator = RunLifecycleCoordinator()
    caplog.set_level(logging.WARNING, logger=coordinator_mod.__name__)

    run_id, record = await coordinator.attach_history(
        AttachRequest(workflow_id=workflow_id, topic="Topic", db_path=str(db_path), status="completed")
    )

    assert run_id
    assert record.done is True
    assert record.outputs == {}
    assert any(
        rec.levelno == logging.WARNING
        and workflow_id in rec.message
        and "run_summary.json" in rec.message
        and "JSONDecodeError" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_attach_history_logs_warning_on_terminal_evidence_failure(
    isolated_runs_root: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_id = "wf-evidence-fail"
    db_path = isolated_runs_root / workflow_id / "runtime.db"
    await _seed_runtime_db(db_path, workflow_id, status="running")

    async def _boom(_db_path: str) -> dict[str, object]:
        raise RuntimeError("sqlite busy during probe")

    monkeypatch.setattr("src.web.state._collect_terminal_evidence", _boom)

    coordinator = RunLifecycleCoordinator()
    caplog.set_level(logging.WARNING, logger=coordinator_mod.__name__)

    _, record = await coordinator.attach_history(
        AttachRequest(workflow_id=workflow_id, topic="Topic", db_path=str(db_path), status="stale")
    )

    assert record.done is True
    assert record.error == "Workflow stale"
    assert any(
        rec.levelno == logging.WARNING
        and workflow_id in rec.message
        and str(db_path) in rec.message
        and "RuntimeError" in rec.message
        and "sqlite busy during probe" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_attach_history_logs_warning_when_db_outside_attachable_roots(
    isolated_runs_root: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    outside = isolated_runs_root.parent / "outside" / "runtime.db"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("", encoding="utf-8")

    coordinator = RunLifecycleCoordinator()
    caplog.set_level(logging.WARNING, logger=coordinator_mod.__name__)

    with pytest.raises(HTTPException) as exc:
        await coordinator.attach_history(
            AttachRequest(workflow_id="wf-outside", topic="Topic", db_path=str(outside), status="completed")
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid database path"
    assert any(
        rec.levelno == logging.WARNING
        and "wf-outside" in rec.message
        and str(outside) in rec.message
        and "outside attachable roots" in rec.message
        for rec in caplog.records
    )
