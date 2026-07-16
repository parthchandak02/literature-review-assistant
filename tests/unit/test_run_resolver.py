"""Unit tests for unified run/workflow resolution and lifecycle reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import HTTPException

from src.db.workflow_registry import register
from src.web.lifecycle_reconciler import LifecycleReconciler
from src.web.run_resolver import RunResolver


@dataclass
class _StubRunRecord:
    workflow_id: str | None = None
    db_path: str | None = None
    done: bool = False
    task: Any = None


def _make_resolver(
    active_runs: dict[str, _StubRunRecord] | None = None,
    lifecycle_metrics: dict[str, int] | None = None,
) -> RunResolver:
    return RunResolver(
        active_runs=active_runs or {},
        lifecycle_reconciler=LifecycleReconciler(
            stale_threshold_seconds=120,
            stale_grace_seconds=120,
            bump_metric=lambda _name: None,
        ),
        lifecycle_metrics=lifecycle_metrics or {},
        anchor_file=__file__,
    )


@pytest.mark.asyncio
async def test_resolve_db_path_from_active_run() -> None:
    resolver = _make_resolver(
        {
            "abc12345": _StubRunRecord(db_path="/tmp/runtime.db"),
        }
    )
    assert await resolver.resolve_db_path("abc12345") == "/tmp/runtime.db"


@pytest.mark.asyncio
async def test_resolve_db_path_active_run_initializing_raises_503() -> None:
    resolver = _make_resolver({"abc12345": _StubRunRecord(db_path=None)})
    with pytest.raises(HTTPException) as exc:
        await resolver.resolve_db_path("abc12345")
    assert exc.value.status_code == 503
    assert exc.value.headers == {"Retry-After": "2"}


@pytest.mark.asyncio
async def test_resolve_db_path_non_workflow_identifier_raises_404() -> None:
    resolver = _make_resolver()
    with pytest.raises(HTTPException) as exc:
        await resolver.resolve_db_path("not-a-workflow")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Run not found"


@pytest.mark.asyncio
async def test_resolve_db_path_from_registry(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-registry",
        topic="Registry lookup",
        config_hash="hash",
        db_path=str(db_path),
    )
    resolver = _make_resolver()
    assert await resolver.resolve_db_path("wf-registry", run_root) == str(db_path)


@pytest.mark.asyncio
async def test_resolve_db_path_missing_workflow_raises_404(tmp_path) -> None:
    resolver = _make_resolver()
    with pytest.raises(HTTPException) as exc:
        await resolver.resolve_db_path("wf-missing", str(tmp_path))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_registry_db_path_returns_none_for_non_workflow_id() -> None:
    resolver = _make_resolver()
    assert await resolver.resolve_registry_db_path("run-id") is None


@pytest.mark.asyncio
async def test_resolve_registry_db_path_returns_none_when_missing(tmp_path) -> None:
    resolver = _make_resolver()
    assert await resolver.resolve_registry_db_path("wf-missing", str(tmp_path)) is None


@pytest.mark.asyncio
async def test_live_run_id_for_workflow_returns_active_run() -> None:
    resolver = _make_resolver(
        {
            "run-a": _StubRunRecord(workflow_id="wf-live", done=False, task=None),
            "run-b": _StubRunRecord(workflow_id="wf-live", done=True, task=None),
        }
    )
    assert resolver.live_run_id_for_workflow("wf-live") == "run-a"


@pytest.mark.asyncio
async def test_reconcile_effective_status_loads_registry_row(tmp_path) -> None:
    run_root = str(tmp_path)
    db_path = tmp_path / "run" / "runtime.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("")
    await register(
        run_root=run_root,
        workflow_id="wf-reconcile",
        topic="Reconcile",
        config_hash="hash",
        db_path=str(db_path),
        status="completed",
    )
    resolver = _make_resolver()
    status, diag = await resolver.reconcile_effective_status("wf-reconcile", run_root)
    assert status == "completed"
    assert diag["registry_status"] == "completed"


@pytest.mark.asyncio
async def test_reconcile_effective_status_missing_workflow_raises_404(tmp_path) -> None:
    resolver = _make_resolver()
    with pytest.raises(HTTPException) as exc:
        await resolver.reconcile_effective_status("wf-missing", str(tmp_path))
    assert exc.value.status_code == 404
