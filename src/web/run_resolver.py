"""Unified run/workflow DB path resolution and lifecycle status reconciliation."""

from __future__ import annotations

import pathlib
from typing import Any

import aiosqlite
from fastapi import HTTPException

from src.db.workflow_registry import _open_registry as _open_registry_db
from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path
from src.web.lifecycle_reconciler import LifecycleReconciler

_REGISTRY_ROW_COLUMNS = """
    workflow_id, topic, status, db_path,
    COALESCE(created_at, '') AS created_at,
    updated_at,
    heartbeat_at
"""


class RunResolver:
    """Resolve runtime.db paths and reconcile registry lifecycle status."""

    def __init__(
        self,
        *,
        active_runs: dict[str, Any],
        lifecycle_reconciler: LifecycleReconciler,
        lifecycle_metrics: dict[str, int],
        anchor_file: str | None = None,
    ) -> None:
        self._active_runs = active_runs
        self._lifecycle_reconciler = lifecycle_reconciler
        self._lifecycle_metrics = lifecycle_metrics
        self._anchor_file = anchor_file

    def live_run_id_for_workflow(self, workflow_id: str) -> str | None:
        """Return the active run_id for a workflow that is currently executing."""
        for run_id, record in self._active_runs.items():
            if (
                record.workflow_id == workflow_id
                and not record.done
                and (record.task is None or not record.task.done())
            ):
                return run_id
        return None

    async def resolve_db_path(self, identifier: str, run_root: str = "runs") -> str:
        """Resolve db_path from an active run_id or a wf-* workflow_id."""
        record = self._active_runs.get(identifier)
        if record is not None:
            if not record.db_path:
                raise HTTPException(
                    status_code=503,
                    detail="Database initializing -- retry in a moment",
                    headers={"Retry-After": "2"},
                )
            return record.db_path

        if not identifier.startswith("wf-"):
            raise HTTPException(status_code=404, detail="Run not found")

        db_path = await self.resolve_registry_db_path(identifier, run_root)
        if not db_path:
            raise HTTPException(status_code=404, detail="Run not found")
        return db_path

    async def resolve_registry_db_path(self, workflow_id: str, run_root: str = "runs") -> str | None:
        """Look up db_path for a workflow_id via registry and filesystem fallback roots."""
        if not workflow_id.startswith("wf-"):
            return None
        roots = candidate_run_roots(run_root, anchor_file=self._anchor_file)
        return await resolve_workflow_db_path(workflow_id, roots)

    async def reconcile_effective_status(
        self,
        workflow_id: str,
        run_root: str = "runs",
        *,
        row: aiosqlite.Row | None = None,
        live_run_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Reconcile registry status against durable runtime terminal evidence."""
        resolved_row = row
        if resolved_row is None:
            resolved_row = await self._load_registry_row(workflow_id, run_root)
            if resolved_row is None:
                raise HTTPException(status_code=404, detail="Workflow not found")

        if live_run_id is None:
            live_run_id = self.live_run_id_for_workflow(workflow_id)

        return await self._lifecycle_reconciler.resolve_effective_status(
            resolved_row,
            live_run_id,
            run_root,
            lifecycle_metrics=self._lifecycle_metrics,
        )

    async def _load_registry_row(self, workflow_id: str, run_root: str) -> aiosqlite.Row | None:
        registry = pathlib.Path(run_root) / "workflows_registry.db"
        if not registry.exists():
            return None
        try:
            async with _open_registry_db(str(registry)) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    f"SELECT {_REGISTRY_ROW_COLUMNS} FROM workflows_registry WHERE workflow_id = ?",
                    (workflow_id,),
                ) as cur:
                    return await cur.fetchone()
        except Exception:
            return None
