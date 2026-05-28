"""Terminal status reconciliation for registry and history surfaces."""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable
from typing import Any

import aiosqlite

from src.db.workflow_registry import update_status as update_registry_status
from src.web.shared import _normalize_status

_logger = logging.getLogger(__name__)

TERMINAL_EVENT_TO_STATUS = {
    "done": "completed",
    "error": "failed",
    "cancelled": "interrupted",
}


class LifecycleReconciler:
    def __init__(
        self,
        *,
        stale_threshold_seconds: int,
        stale_grace_seconds: int,
        bump_metric: Callable[[str], None],
    ) -> None:
        self.stale_threshold_seconds = stale_threshold_seconds
        self.stale_grace_seconds = stale_grace_seconds
        self._bump_metric = bump_metric

    def running_heartbeat_stale(self, row: aiosqlite.Row) -> bool:
        from src.web.shared import _age_seconds as age_fn

        heartbeat_age = age_fn(row["heartbeat_at"])
        updated_age = age_fn(row["updated_at"])
        created_age = age_fn(row["created_at"])
        fresh = (
            min(x for x in (heartbeat_age, updated_age, created_age) if x is not None)
            if any(x is not None for x in (heartbeat_age, updated_age, created_age))
            else None
        )
        if fresh is not None and fresh <= self.stale_grace_seconds:
            return False
        if heartbeat_age is not None:
            return heartbeat_age > self.stale_threshold_seconds
        if updated_age is not None:
            return updated_age > self.stale_threshold_seconds
        if created_age is not None:
            return created_age > self.stale_threshold_seconds
        return True

    async def collect_terminal_evidence(self, db_path: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "terminal_status": None,
            "source": None,
            "event_type": None,
            "workflow_status": None,
            "summary_status": None,
            "finalize_checkpoint_status": None,
        }
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                try:
                    async with db.execute(
                        "SELECT event_type FROM event_log WHERE event_type IN ('done','error','cancelled') ORDER BY id DESC LIMIT 1"
                    ) as cur:
                        ev_row = await cur.fetchone()
                    if ev_row and ev_row["event_type"]:
                        ev_type = str(ev_row["event_type"])
                        out["event_type"] = ev_type
                        ev_status = TERMINAL_EVENT_TO_STATUS.get(ev_type)
                        if ev_status:
                            out["terminal_status"] = ev_status
                            out["source"] = "event_log"
                except Exception:
                    pass
                if out["terminal_status"] is None:
                    try:
                        async with db.execute(
                            "SELECT status FROM workflows ORDER BY updated_at DESC, rowid DESC LIMIT 1"
                        ) as cur:
                            wf_row = await cur.fetchone()
                        wf_status = _normalize_status(str(wf_row["status"])) if wf_row and wf_row["status"] else ""
                        out["workflow_status"] = wf_status
                        if wf_status in {"completed", "failed", "interrupted"}:
                            out["terminal_status"] = wf_status
                            out["source"] = "workflows_table"
                    except Exception:
                        pass
                if out["terminal_status"] is None:
                    try:
                        async with db.execute(
                            "SELECT status FROM checkpoints WHERE phase='finalize' ORDER BY rowid DESC LIMIT 1"
                        ) as cur:
                            cp_row = await cur.fetchone()
                        cp_status = _normalize_status(str(cp_row["status"])) if cp_row and cp_row["status"] else ""
                        out["finalize_checkpoint_status"] = cp_status
                        if cp_status == "completed":
                            out["terminal_status"] = "completed"
                            out["source"] = "finalize_checkpoint"
                    except Exception:
                        pass
        except Exception:
            return out
        summary_path = pathlib.Path(db_path).parent / "run_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                summary_status = _normalize_status(str(summary.get("status", "")))
                out["summary_status"] = summary_status
                if out["terminal_status"] is None and summary_status in {"completed", "failed", "interrupted"}:
                    out["terminal_status"] = summary_status
                    out["source"] = "run_summary"
            except Exception:
                pass
        return out

    async def resolve_effective_status(
        self,
        row: aiosqlite.Row,
        live_run_id: str | None,
        run_root: str,
        *,
        lifecycle_metrics: dict[str, int],
    ) -> tuple[str, dict[str, Any]]:
        from src.web.shared import _age_seconds as age_fn

        registry_status = _normalize_status(str(row["status"]))
        diagnostics: dict[str, Any] = {
            "registry_status": registry_status,
            "live_run_id": live_run_id,
            "source": "registry",
        }
        live_run_active = bool(live_run_id and registry_status in {"running", "awaiting_review"})
        if live_run_active and not self.running_heartbeat_stale(row):
            diagnostics["source"] = "active_run"
            return registry_status, diagnostics
        if live_run_active:
            diagnostics["live_run_stale"] = True
        evidence = await self.collect_terminal_evidence(str(row["db_path"]))
        diagnostics["evidence"] = evidence
        terminal = evidence.get("terminal_status")
        if terminal in {"completed", "failed", "interrupted"} and registry_status in {
            "running",
            "stale",
            "awaiting_review",
        }:
            diagnostics["source"] = str(evidence.get("source") or "runtime")
            diagnostics["override"] = f"{registry_status}->{terminal}"
            if registry_status == "stale":
                self._bump_metric("stale_reversals")
            heartbeat_age = age_fn(row["heartbeat_at"])
            updated_age = age_fn(row["updated_at"])
            if heartbeat_age is None or heartbeat_age > self.stale_threshold_seconds:
                if updated_age is None or updated_age > self.stale_threshold_seconds:
                    self._bump_metric("missing_heartbeat_with_terminal_evidence")
            if registry_status != terminal:
                try:
                    await update_registry_status(run_root, str(row["workflow_id"]), terminal)
                except Exception:
                    pass
                else:
                    _logger.info(
                        "Lifecycle repair: workflow %s status running -> %s (%s)",
                        row["workflow_id"],
                        terminal,
                        evidence.get("source"),
                    )
            return terminal, diagnostics
        if registry_status == "running" and not live_run_id:
            if self.running_heartbeat_stale(row):
                self._bump_metric("stale_detections")
                diagnostics["source"] = "heartbeat_timeout"
                _logger.info(
                    "Lifecycle stale classification: workflow=%s heartbeat_at=%s updated_at=%s metrics=%s",
                    row["workflow_id"],
                    row["heartbeat_at"],
                    row["updated_at"],
                    lifecycle_metrics,
                )
                return "stale", diagnostics
        return registry_status, diagnostics
