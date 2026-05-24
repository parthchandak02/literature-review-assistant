#!/usr/bin/env python3
"""Low-noise workflow monitor for cron and terminal use.

One-shot mode prints only when major state changes since the last check.
Follow mode streams high-level events from app.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite


def _resolve_repo_root() -> Path:
    if os.environ.get("LITREVIEW_ROOT"):
        return Path(os.environ["LITREVIEW_ROOT"]).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _resolve_repo_root()
sys.path.insert(0, str(REPO_ROOT))

from src.db.workflow_registry import (  # noqa: E402
    candidate_run_roots,
    find_by_workflow_id,
    find_by_workflow_id_fallback,
    resolve_workflow_db_path,
)
from src.utils.structured_log import load_events_from_jsonl  # noqa: E402

FOLLOW_EVENT_TYPES = {"phase_start", "phase_done", "error", "done", "cancelled"}


@dataclass
class Snapshot:
    workflow_id: str
    db_path: str
    registry_status: str
    phase: str | None
    phase_ts: str | None
    included_papers: int | None

    @property
    def cursor(self) -> str:
        payload = {
            "registry_status": self.registry_status,
            "phase": self.phase,
            "phase_ts": self.phase_ts,
            "included_papers": self.included_papers,
        }
        return json.dumps(payload, sort_keys=True)


def _default_state_file(workflow_id: str) -> Path:
    return Path("~/.hermes/watcher-state").expanduser() / f"lit-review-{workflow_id}.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, sort_keys=True), encoding="utf-8")


async def _resolve_entry(workflow_id: str, run_root: str) -> tuple[str, str]:
    roots = candidate_run_roots(run_root, anchor_file=__file__)
    db_path = await resolve_workflow_db_path(workflow_id, roots)
    if not db_path:
        raise FileNotFoundError(f"Workflow {workflow_id} not found under run roots: {roots}")

    status = "unknown"
    for root in roots:
        entry = await find_by_workflow_id(root, workflow_id)
        if entry is None:
            entry = await find_by_workflow_id_fallback(root, workflow_id)
        if entry is not None:
            status = entry.status
            break
    return db_path, status


async def _read_latest_phase_done(db_path: str, workflow_id: str) -> tuple[str | None, str | None]:
    query = """
        SELECT payload, ts
        FROM event_log
        WHERE workflow_id = ? AND event_type = 'phase_done'
        ORDER BY ts DESC, id DESC
        LIMIT 1
    """
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(query, (workflow_id,))
        row = await cur.fetchone()
    if not row:
        return None, None
    payload_raw, ts = row
    try:
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    except json.JSONDecodeError:
        payload = {}
    phase = payload.get("phase") if isinstance(payload, dict) else None
    return (str(phase) if phase else None), (str(ts) if ts else None)


def _read_included_papers(db_path: str) -> int | None:
    run_summary_path = Path(db_path).parent / "run_summary.json"
    if not run_summary_path.exists():
        return None
    try:
        data = json.loads(run_summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = data.get("included_papers")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def _snapshot(workflow_id: str, run_root: str) -> Snapshot:
    db_path, status = await _resolve_entry(workflow_id, run_root)
    phase, phase_ts = await _read_latest_phase_done(db_path, workflow_id)
    included_papers = _read_included_papers(db_path)
    return Snapshot(
        workflow_id=workflow_id,
        db_path=db_path,
        registry_status=status,
        phase=phase,
        phase_ts=phase_ts,
        included_papers=included_papers,
    )


def _format_message(snapshot: Snapshot) -> str:
    bits = [f"workflow={snapshot.workflow_id}", f"status={snapshot.registry_status}"]
    if snapshot.phase:
        bits.append(f"phase={snapshot.phase}")
    if snapshot.phase_ts:
        bits.append(f"ts={snapshot.phase_ts}")
    if snapshot.included_papers is not None:
        bits.append(f"included_papers={snapshot.included_papers}")
    return " | ".join(bits)


async def _run_once(args: argparse.Namespace) -> int:
    state_file = Path(args.state_file).expanduser() if args.state_file else _default_state_file(args.workflow_id)
    if args.reset_state and state_file.exists():
        state_file.unlink()

    snapshot = await _snapshot(args.workflow_id, args.run_root)
    previous = _load_state(state_file)

    previous_cursor = str(previous.get("cursor") or "")
    changed = snapshot.cursor != previous_cursor

    if not changed:
        return 0

    state = {"cursor": snapshot.cursor, "updated_at": int(time.time())}
    _save_state(state_file, state)

    if args.json:
        print(
            json.dumps(
                {
                    "workflow_id": snapshot.workflow_id,
                    "status": snapshot.registry_status,
                    "phase": snapshot.phase,
                    "phase_ts": snapshot.phase_ts,
                    "included_papers": snapshot.included_papers,
                },
                ensure_ascii=True,
            )
        )
    else:
        print(_format_message(snapshot))
    return 0


def _format_follow_event(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "")
    if event_type not in FOLLOW_EVENT_TYPES:
        return None
    ts = str(event.get("ts") or "")
    if event_type in {"phase_start", "phase_done"}:
        phase = str(event.get("phase") or "")
        return f"{ts} {event_type} {phase}".strip()
    return f"{ts} {event_type}".strip()


async def _run_follow(args: argparse.Namespace) -> int:
    snapshot = await _snapshot(args.workflow_id, args.run_root)
    app_log = Path(snapshot.db_path).parent / "app.jsonl"
    if not app_log.exists():
        raise FileNotFoundError(f"app.jsonl not found for workflow {args.workflow_id}: {app_log}")

    print(f"following workflow={args.workflow_id} log={app_log}")
    seen = 0
    while True:
        events = load_events_from_jsonl(str(app_log))
        if len(events) > seen:
            for event in events[seen:]:
                line = _format_follow_event(event)
                if line:
                    print(line)
            seen = len(events)
        await asyncio.sleep(args.interval)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor major workflow stage changes with low-noise output.")
    parser.add_argument("--workflow-id", required=True, help="Workflow identifier (e.g. wf-0096).")
    parser.add_argument("--run-root", default="runs", help="Runs root used to resolve workflows_registry.db.")
    parser.add_argument("--state-file", help="Optional state file path for one-shot dedup output.")
    parser.add_argument("--json", action="store_true", help="Emit JSON in one-shot mode.")
    parser.add_argument("--reset-state", action="store_true", help="Reset dedup state before one-shot check.")
    parser.add_argument("--follow", action="store_true", help="Follow app.jsonl and stream major events.")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval in follow mode.")
    return parser


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.follow:
        return await _run_follow(args)
    return await _run_once(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
