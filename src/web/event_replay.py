"""Replay run activity events with checkpoint-backed UI phase alignment."""

from __future__ import annotations

import datetime
from typing import Any

import aiosqlite

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.orchestration.phase_catalog import UI_TIMELINE_PHASE_ORDER
from src.web.event_store import EventStore

# Map UI phase -> checkpoint row name(s) in runtime.db.checkpoints.
UI_PHASE_CHECKPOINT_SOURCES: dict[str, tuple[str, ...]] = {
    "phase_2_search": ("phase_2_search",),
    "phase_3_screening": ("phase_3_screening",),
    "fulltext_pdf_retrieval": ("phase_3b_fulltext",),
    "phase_4_extraction_quality": ("phase_4_extraction_quality",),
    "phase_4b_embedding": ("phase_4b_embedding",),
    "phase_5_synthesis": ("phase_5_synthesis",),
    "phase_5b_knowledge_graph": ("phase_5b_knowledge_graph",),
    "phase_5c_pre_writing_gate": ("phase_5c_pre_writing_gate",),
    "phase_6_writing": ("phase_6_writing",),
    "phase_7_audit": ("phase_7_audit",),
    "finalize": ("finalize",),
}

_TERMINAL_EVENT_TYPES = frozenset({"done", "error", "cancelled"})


def _checkpoint_completed(checkpoints: dict[str, str], checkpoint_phase: str) -> bool:
    return checkpoints.get(checkpoint_phase) == "completed"


def ui_phase_completed(checkpoints: dict[str, str], ui_phase: str) -> bool:
    """Return True when any backing checkpoint for a UI phase is completed."""
    sources = UI_PHASE_CHECKPOINT_SOURCES.get(ui_phase, (ui_phase,))
    return any(_checkpoint_completed(checkpoints, source) for source in sources)


def _infer_synthetic_ts(events: list[dict[str, Any]], insert_index: int) -> str:
    if insert_index > 0:
        prev = events[insert_index - 1]
        if isinstance(prev, dict) and prev.get("ts"):
            return str(prev["ts"])
    return datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def enrich_events_with_checkpoints(
    events: list[dict[str, Any]],
    checkpoints: dict[str, str],
) -> list[dict[str, Any]]:
    """Insert synthetic phase_done markers for completed checkpoints missing from event_log."""
    if not checkpoints:
        return events

    phases_with_done = {
        str(event.get("phase"))
        for event in events
        if isinstance(event, dict) and event.get("type") == "phase_done" and event.get("phase")
    }

    insert_index = len(events)
    for index, event in enumerate(events):
        if isinstance(event, dict) and event.get("type") in _TERMINAL_EVENT_TYPES:
            insert_index = index
            break

    synthetic_ts = _infer_synthetic_ts(events, insert_index)
    synthetic_events: list[dict[str, Any]] = []
    for ui_phase in UI_TIMELINE_PHASE_ORDER:
        if ui_phase in phases_with_done:
            continue
        if not ui_phase_completed(checkpoints, ui_phase):
            continue
        synthetic_events.append(
            {
                "type": "phase_done",
                "phase": ui_phase,
                "summary": {},
                "total": None,
                "completed": None,
                "synthetic": True,
                "ts": synthetic_ts,
                "id": f"synthetic-{ui_phase}",
            }
        )

    if not synthetic_events:
        return events

    enriched = list(events)
    for event in reversed(synthetic_events):
        enriched.insert(insert_index, event)
    return enriched


async def resolve_workflow_id(db_path: str) -> str | None:
    try:
        async with aiosqlite.connect(db_path) as db:
            row = await (await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        return None
    return None


async def load_checkpoints(db_path: str, workflow_id: str) -> dict[str, str]:
    async with get_db(db_path) as db:
        return await WorkflowRepository(db).get_checkpoints(workflow_id)


async def load_replay_events(db_path: str, workflow_id: str | None = None) -> list[dict[str, Any]]:
    """Load persisted events and align UI timeline phases with checkpoint truth."""
    events = await EventStore().load(db_path)
    wf_id = workflow_id or await resolve_workflow_id(db_path)
    if not wf_id:
        return events
    try:
        checkpoints = await load_checkpoints(db_path, wf_id)
    except Exception:
        return events
    return enrich_events_with_checkpoints(events, checkpoints)
