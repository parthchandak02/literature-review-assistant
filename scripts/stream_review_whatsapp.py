#!/usr/bin/env python3
"""Stream literature-review progress to WhatsApp via the Hermes Baileys bridge.

One sticky message per pipeline phase (edit in place). New message on phase change.
Requires --chat-id from the WhatsApp group where the review was started.

Usage:
  python scripts/stream_review_whatsapp.py \\
    --workflow-id wf-0105 --chat-id '120363...@g.us' --interval 45

Hermes should embed the chat id when launching detached tmux (shell environment does not propagate).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def _resolve_repo_root() -> Path:
    root = os.getenv("LITREVIEW_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _resolve_repo_root()
sys.path.insert(0, str(REPO_ROOT))

_HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
if _HERMES_SCRIPTS.is_dir():
    sys.path.insert(0, str(_HERMES_SCRIPTS))

from whatsapp_stream import WhatsAppStream, resolve_chat_id  # noqa: E402

from scripts.watch_review import (  # noqa: E402
    Snapshot,
    _load_state,
    _save_state,
    _snapshot,
)
from src.utils.structured_log import load_events_from_jsonl  # noqa: E402

_TERMINAL_STATUSES = frozenset(
    {"completed", "complete", "done", "failed", "cancelled", "canceled", "error"}
)
_PHASE_EDIT_MAX_AGE_S = 14 * 60  # refresh bubble before WhatsApp 15m edit window


@dataclass
class StreamState:
    chat_id: str
    phase: str | None
    message_id: str | None
    message_sent_at: float
    last_body: str
    cursor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "phase": self.phase,
            "message_id": self.message_id,
            "message_sent_at": self.message_sent_at,
            "last_body": self.last_body,
            "cursor": self.cursor,
            "updated_at": int(time.time()),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, chat_id: str) -> StreamState:
        return cls(
            chat_id=str(data.get("chat_id") or chat_id),
            phase=data.get("phase"),
            message_id=data.get("message_id"),
            message_sent_at=float(data.get("message_sent_at") or 0.0),
            last_body=str(data.get("last_body") or ""),
            cursor=str(data.get("cursor") or ""),
        )


def _stream_state_path(workflow_id: str) -> Path:
    return Path("~/.hermes/watcher-state").expanduser() / f"lit-review-wa-{workflow_id}.json"


def _load_stream_state(path: Path, chat_id: str) -> StreamState | None:
    raw = _load_state(path)
    if not raw:
        return None
    return StreamState.from_dict(raw, chat_id=chat_id)


def _save_stream_state(path: Path, state: StreamState) -> None:
    _save_state(path, state.to_dict())


def _screening_stats(db_path: str) -> dict[str, int] | None:
    """Title/abstract dual-review counts when tables exist."""
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "dual_screening_results" not in tables:
            conn.close()
            return None
        total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        screened = conn.execute(
            "SELECT COUNT(*) FROM dual_screening_results WHERE stage='title_abstract'"
        ).fetchone()[0]
        included = conn.execute(
            "SELECT COUNT(*) FROM dual_screening_results "
            "WHERE stage='title_abstract' AND final_decision='include'"
        ).fetchone()[0]
        excluded = conn.execute(
            "SELECT COUNT(*) FROM dual_screening_results "
            "WHERE stage='title_abstract' AND final_decision='exclude'"
        ).fetchone()[0]
        conn.close()
        remaining = max(0, int(total) - int(screened))
        return {
            "total": int(total),
            "screened": int(screened),
            "included": int(included),
            "excluded": int(excluded),
            "remaining": remaining,
        }
    except sqlite3.Error:
        return None


def _format_phase_label(phase: str | None) -> str:
    if not phase:
        return "Starting"
    return phase.replace("_", " ").replace("phase ", "Phase ").title()


def _build_body(snapshot: Snapshot, stats: dict[str, int] | None) -> str:
    lines = [
        f"*Lit review* `{snapshot.workflow_id}`",
        f"> status: `{snapshot.registry_status}`",
    ]
    phase_label = _format_phase_label(snapshot.phase)
    lines.append(f"*{_escape_phase(phase_label)}*")
    if stats and snapshot.phase and "screen" in snapshot.phase.lower():
        lines.append(
            f"Screening: `{stats['screened']}`/`{stats['total']}` "
            f"· included `{stats['included']}` · excluded `{stats['excluded']}` "
            f"· left `{stats['remaining']}`"
        )
    elif snapshot.included_papers is not None:
        lines.append(f"Included papers: `{snapshot.included_papers}`")
    if snapshot.phase_ts:
        lines.append(f"_updated {snapshot.phase_ts}_")
    return "\n".join(lines)


def _escape_phase(label: str) -> str:
    return label.replace("*", "")


def _has_terminal_event(db_path: str) -> bool:
    app_log = Path(db_path).parent / "app.jsonl"
    if not app_log.is_file():
        return False
    try:
        events = load_events_from_jsonl(str(app_log))
    except OSError:
        return False
    for event in reversed(events[-50:]):
        if str(event.get("type") or "") in {"done", "error", "cancelled"}:
            return True
    return False


def _find_submission_zip(db_path: str) -> Path | None:
    run_dir = Path(db_path).parent
    submission = run_dir / "submission"
    if not submission.is_dir():
        return None
    zips = sorted(submission.glob("submission_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


async def _run_export(workflow_id: str) -> Path | None:
    proc = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "python",
        "-m",
        "src.main",
        "export",
        "--workflow-id",
        workflow_id,
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0:
        return None
    snapshot = await _snapshot(workflow_id, "runs")
    return _find_submission_zip(snapshot.db_path)


def _should_new_bubble(state: StreamState, snapshot: Snapshot) -> bool:
    if state.phase != snapshot.phase:
        return True
    if state.message_sent_at and (time.time() - state.message_sent_at) > _PHASE_EDIT_MAX_AGE_S:
        return True
    return state.message_id is None


async def _push_update(
    chat: WhatsAppStream,
    state: StreamState,
    snapshot: Snapshot,
    *,
    force_send: bool = False,
) -> StreamState:
    stats = _screening_stats(snapshot.db_path)
    body = _build_body(snapshot, stats)
    if body == state.last_body and not force_send:
        return state

    new_bubble = _should_new_bubble(state, snapshot)
    if new_bubble:
        mid = chat.send(body)
        return StreamState(
            chat_id=state.chat_id,
            phase=snapshot.phase,
            message_id=mid,
            message_sent_at=time.time(),
            last_body=body,
            cursor=snapshot.cursor,
        )

    chat.edit(body)
    return StreamState(
        chat_id=state.chat_id,
        phase=snapshot.phase,
        message_id=state.message_id,
        message_sent_at=state.message_sent_at,
        last_body=body,
        cursor=snapshot.cursor,
    )


async def _run_loop(args: argparse.Namespace) -> int:
    state_path = _stream_state_path(args.workflow_id)
    prior = _load_stream_state(state_path, args.chat_id)
    workflow_state = prior.to_dict() if prior else {}
    chat_id = resolve_chat_id(cli_chat_id=args.chat_id, workflow_state=workflow_state)

    chat = WhatsAppStream(chat_id)
    state = prior or StreamState(
        chat_id=chat_id,
        phase=None,
        message_id=None,
        message_sent_at=0.0,
        last_body="",
        cursor="",
    )
    if state.chat_id != chat_id:
        state = StreamState(
            chat_id=chat_id,
            phase=None,
            message_id=None,
            message_sent_at=0.0,
            last_body="",
            cursor="",
        )

    try:
        while True:
            snapshot = await _snapshot(args.workflow_id, args.run_root)
            state = await _push_update(chat, state, snapshot)
            _save_stream_state(state_path, state)

            status = (snapshot.registry_status or "").lower()
            if status in _TERMINAL_STATUSES or _has_terminal_event(snapshot.db_path):
                break

            await asyncio.sleep(args.interval)

        snapshot = await _snapshot(args.workflow_id, args.run_root)
        zip_path = _find_submission_zip(snapshot.db_path)
        if zip_path is None and args.export_on_complete:
            zip_path = await _run_export(args.workflow_id)

        final_text = (
            f"*Lit review complete* `{args.workflow_id}`\n"
            f"> status: `{snapshot.registry_status}`"
        )
        if snapshot.included_papers is not None:
            final_text += f"\nIncluded: `{snapshot.included_papers}`"
        chat.send(final_text)
        if zip_path and zip_path.is_file():
            chat.send_media(zip_path, caption=f"Submission package · {args.workflow_id}")
    finally:
        chat.close()

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stream lit-review progress to WhatsApp.")
    parser.add_argument("--workflow-id", required=True, help="Workflow id (e.g. wf-0105).")
    parser.add_argument(
        "--chat-id",
        required=True,
        help="WhatsApp JID for the group/DM where the review was started (@g.us or @lid).",
    )
    parser.add_argument("--run-root", default="runs", help="Runs root for registry lookup.")
    parser.add_argument("--interval", type=float, default=45.0, help="Poll interval seconds.")
    parser.add_argument(
        "--export-on-complete",
        action="store_true",
        help="Run src.main export if submission zip missing when workflow finishes.",
    )
    return parser


async def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return await _run_loop(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
