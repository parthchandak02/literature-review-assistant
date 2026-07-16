"""Run lifecycle coordinator for active-run resolution and registry-backed claims.

Phase 2.1 centralizes in-memory ``_active_runs`` access, registry-backed path
resolution, and atomic resume claims so routers do not duplicate parent-path hacks.
"""

from __future__ import annotations

import datetime
import json as _json
import logging
import pathlib
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiosqlite
from fastapi import HTTPException

from src.db.workflow_registry import (
    _open_registry as _open_registry_db,
)
from src.db.workflow_registry import (
    candidate_run_roots,
    find_by_workflow_id,
    resolve_workflow_db_path,
    run_root_from_db_path,
    try_claim_for_resume,
)
from src.web.shared import (
    AttachRequest,
    ResumeRequest,
    _ensure_runtime_db_migrated,
    _normalize_status,
    _validate_db_path,
)

if TYPE_CHECKING:
    from src.web.lifecycle_reconciler import LifecycleReconciler
    from src.web.run_resolver import RunResolver

_logger = logging.getLogger(__name__)

_RESUMABLE_ATTACH_OVERRIDE_STATUSES = frozenset({"running", "stale", "awaiting_review"})


@dataclass(frozen=True)
class ResolvedWorkflow:
    """Registry-backed workflow identity for API routing."""

    workflow_id: str
    db_path: str
    run_root: str
    topic: str | None = None
    run_id: str | None = None
    registry_status: str | None = None


class RunLifecycleCoordinator:
    """Coordinates in-memory active runs with registry-backed workflow resolution."""

    def __init__(
        self,
        active_runs: dict[str, Any] | None = None,
        *,
        run_resolver: RunResolver | None = None,
        lifecycle_reconciler: LifecycleReconciler | None = None,
    ) -> None:
        self._active_runs: dict[str, Any] = active_runs if active_runs is not None else {}
        self._run_resolver = run_resolver
        self._lifecycle_reconciler = lifecycle_reconciler

    @property
    def active_runs(self) -> dict[str, Any]:
        return self._active_runs

    def get(self, run_id: str) -> Any | None:
        return self._active_runs.get(run_id)

    def set(self, run_id: str, record: Any) -> None:
        self._active_runs[run_id] = record

    def pop(self, run_id: str, default: Any = None) -> Any:
        return self._active_runs.pop(run_id, default)

    def values(self) -> Any:
        return self._active_runs.values()

    def items(self) -> Any:
        return self._active_runs.items()

    def find_active_by_workflow(self, workflow_id: str) -> Any | None:
        for record in self._active_runs.values():
            if record.workflow_id == workflow_id and not record.done:
                return record
        return None

    def active_run_id_by_workflow(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for record in self._active_runs.values():
            if record.workflow_id and not record.done and (record.task is None or not record.task.done()):
                mapping[record.workflow_id] = record.run_id
        return mapping

    def ensure_not_running(self, workflow_id: str, *, detail: str | None = None) -> None:
        record = self.find_active_by_workflow(workflow_id)
        if record is not None:
            raise HTTPException(
                status_code=409,
                detail=detail or "Workflow is already running. Stop the active run before resuming.",
            )

    @staticmethod
    def infer_run_root(db_path: str) -> str:
        return run_root_from_db_path(db_path)

    async def resolve_db_path(self, identifier: str, run_root: str = "runs") -> str:
        """Resolve runtime.db path from an active run_id or workflow_id."""
        if self._run_resolver is not None:
            return await self._run_resolver.resolve_db_path(identifier, run_root)

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

        roots = candidate_run_roots(run_root, anchor_file=__file__)
        db_path = await resolve_workflow_db_path(identifier, roots)
        if not db_path:
            raise HTTPException(status_code=404, detail="Run not found")
        return db_path

    async def resolve_workflow(
        self,
        workflow_id: str,
        *,
        run_root: str = "runs",
        db_path_hint: str | None = None,
    ) -> ResolvedWorkflow:
        """Resolve workflow identity from registry, with optional db_path hint."""
        roots = candidate_run_roots(run_root, anchor_file=__file__)
        if db_path_hint:
            hint_root = run_root_from_db_path(db_path_hint)
            if hint_root not in roots:
                roots = [hint_root, *roots]

        db_path: str | None = None
        topic: str | None = None
        registry_status: str | None = None
        for root in roots:
            entry = await find_by_workflow_id(root, workflow_id)
            if entry is None:
                continue
            db_path = entry.db_path
            topic = entry.topic
            registry_status = entry.status
            run_root = root
            break

        if db_path is None and db_path_hint:
            _validate_db_path(db_path_hint)
            db_path = str(pathlib.Path(db_path_hint).resolve())
            run_root = run_root_from_db_path(db_path)
        elif db_path is None:
            db_path = await resolve_workflow_db_path(workflow_id, roots)
            if db_path is None:
                raise HTTPException(status_code=404, detail="Workflow not found")
            run_root = run_root_from_db_path(db_path)

        active = self.find_active_by_workflow(workflow_id)
        return ResolvedWorkflow(
            workflow_id=workflow_id,
            db_path=db_path,
            run_root=run_root,
            topic=topic,
            run_id=active.run_id if active is not None else None,
            registry_status=registry_status,
        )

    async def claim_for_resume(self, workflow_id: str, db_path: str) -> ResolvedWorkflow:
        """Ensure workflow is not in-memory active and atomically claim registry row."""
        self.ensure_not_running(workflow_id)
        resolved = await self.resolve_workflow(workflow_id, db_path_hint=db_path)
        reclaim_stale_running = False
        registry = pathlib.Path(resolved.run_root) / "workflows_registry.db"
        if registry.exists():
            try:
                async with _open_registry_db(str(registry)) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        """
                        SELECT status, heartbeat_at, updated_at, created_at
                        FROM workflows_registry
                        WHERE workflow_id = ?
                        """,
                        (workflow_id,),
                    ) as cur:
                        row = await cur.fetchone()
                if row is not None:
                    registry_status = _normalize_status(str(row["status"]))
                    if registry_status == "awaiting_review":
                        raise HTTPException(
                            status_code=409,
                            detail="Workflow is already running. Stop the active run before resuming.",
                        )
                    if registry_status == "running":
                        heartbeat_stale = (
                            self._lifecycle_reconciler.running_heartbeat_stale(row)
                            if self._lifecycle_reconciler is not None
                            else False
                        )
                        if not heartbeat_stale:
                            raise HTTPException(
                                status_code=409,
                                detail="Workflow is already running. Stop the active run before resuming.",
                            )
                        reclaim_stale_running = True
                        _logger.info(
                            "Resume allowed for stale running registry claim: workflow=%s",
                            workflow_id,
                        )
            except HTTPException:
                raise
            except Exception:
                pass

        claimed, blocking_status = await try_claim_for_resume(
            resolved.run_root,
            workflow_id,
            reclaim_stale_running=reclaim_stale_running,
        )
        if not claimed and blocking_status in {"running", "awaiting_review"}:
            raise HTTPException(
                status_code=409,
                detail="Workflow is already running. Stop the active run before resuming.",
            )
        return resolved

    async def start_resume(
        self,
        req: ResumeRequest,
        *,
        resume_wrapper: Any,
    ) -> tuple[str, Any]:
        """Claim workflow and register an in-memory resume task."""
        from src.web.state import _RunRecord

        resolved = await self.claim_for_resume(req.workflow_id, req.db_path)
        run_id = str(uuid.uuid4())[:8]
        record = _RunRecord(run_id=run_id, topic=req.topic)
        record.db_path = resolved.db_path
        record.workflow_id = req.workflow_id
        record.run_root = resolved.run_root
        self.set(run_id, record)
        import asyncio

        from src.web.run_concurrency import acquire_run_slot_or_raise

        await acquire_run_slot_or_raise()
        task = asyncio.create_task(
            resume_wrapper(record, req.workflow_id, resolved.db_path, req.from_phase, req.verbose, req.debug)
        )
        record.task = task
        return run_id, record

    async def attach_history(self, req: AttachRequest) -> tuple[str, Any]:
        """Create a read-only completed run record from a historical workflow."""
        from src.web.state import (
            _collect_terminal_evidence,
            _load_event_log_from_db,
            _RunRecord,
        )

        _validate_db_path(req.db_path)
        resolved = await self.resolve_workflow(req.workflow_id, db_path_hint=req.db_path)

        if pathlib.Path(resolved.db_path).resolve() != pathlib.Path(req.db_path).resolve():
            _logger.info(
                "Attach db_path hint differs from registry for %s; using registry path %s",
                req.workflow_id,
                resolved.db_path,
            )

        run_id = str(uuid.uuid4())[:8]
        topic = req.topic or resolved.topic or "Untitled review"
        record = _RunRecord(run_id=run_id, topic=topic)
        record.done = True
        record.db_path = resolved.db_path
        record.workflow_id = req.workflow_id
        record.run_root = resolved.run_root

        await _ensure_runtime_db_migrated(resolved.db_path)
        summary_path = pathlib.Path(resolved.db_path).parent / "run_summary.json"
        if summary_path.exists():
            try:
                record.outputs = _json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        record.event_log = await _load_event_log_from_db(resolved.db_path, req.workflow_id)
        try:
            evidence = await _collect_terminal_evidence(resolved.db_path)
        except Exception:
            evidence = {"terminal_status": None, "source": None}

        normalized_req_status = _normalize_status(req.status)
        effective_attach_status = normalized_req_status
        evidence_terminal = evidence.get("terminal_status")
        if (
            evidence_terminal in {"completed", "failed", "interrupted"}
            and normalized_req_status in _RESUMABLE_ATTACH_OVERRIDE_STATUSES
        ):
            effective_attach_status = str(evidence_terminal)
            _logger.info(
                "Attach status override for %s: %s -> %s (source=%s)",
                req.workflow_id,
                normalized_req_status,
                evidence_terminal,
                evidence.get("source"),
            )

        if effective_attach_status not in ("completed", "done"):
            record.error = f"Workflow {effective_attach_status}"
        if effective_attach_status not in ("completed", "done"):
            has_terminal = any(
                isinstance(e, dict) and e.get("type") in ("done", "error", "cancelled") for e in record.event_log
            )
            if not has_terminal:
                record.event_log.append(
                    {
                        "type": "error",
                        "msg": (
                            "Workflow appears orphaned (no terminal event persisted)"
                            if effective_attach_status == "stale"
                            else f"Run ended with status: {effective_attach_status}"
                        ),
                        "ts": datetime.datetime.now(tz=datetime.UTC).isoformat(),
                    }
                )
        self.set(run_id, record)
        return run_id, record


_default_coordinator: RunLifecycleCoordinator | None = None


def bind_active_runs(
    active_runs: dict[str, Any],
    *,
    run_resolver: RunResolver | None = None,
    lifecycle_reconciler: LifecycleReconciler | None = None,
) -> RunLifecycleCoordinator:
    """Bind the module-level coordinator to the process active-run map."""
    global _default_coordinator
    _default_coordinator = RunLifecycleCoordinator(
        active_runs,
        run_resolver=run_resolver,
        lifecycle_reconciler=lifecycle_reconciler,
    )
    return _default_coordinator


def get_coordinator() -> RunLifecycleCoordinator:
    if _default_coordinator is None:
        return RunLifecycleCoordinator()
    return _default_coordinator
