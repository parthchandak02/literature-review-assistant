"""Structured logging for machine-parseable audit trail.

Per-run isolation: each run writes to its own {log_dir}/app.jsonl.
The global structlog processors are configured once; per-run routing
is handled by reading the current run's log_dir from structlog contextvars
and writing the JSON line to the matching open file handle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

import structlog
from structlog.processors import JSONRenderer
from structlog.typing import EventDict, Processor

# Maps log_dir (absolute path string) -> open file handle for that run's app.jsonl.
_file_handles: dict[str, TextIO] = {}

# True once the global structlog processor chain has been configured (one-time).
_structlog_configured = False


def _write_to_run_file(
    logger: Any,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """structlog processor: write JSON line to the current run's app.jsonl.

    Reads log_dir from contextvars (bound by bind_run).  If no log_dir is
    bound (e.g. during startup before any run starts) the write is silently
    skipped so the global structlog chain continues normally.
    """
    ctx = structlog.contextvars.get_contextvars()
    log_dir = ctx.get("log_dir")
    if log_dir and log_dir in _file_handles:
        fh = _file_handles[log_dir]
        try:
            line = json.dumps(event_dict) + "\n"
            fh.write(line)
            fh.flush()
        except Exception:
            pass
    return event_dict


def configure_run_logging(log_dir: str) -> None:
    """Open a per-run app.jsonl for this log_dir and ensure structlog is configured.

    Safe to call multiple times with the same log_dir (idempotent).
    Each distinct log_dir gets its own file handle so multiple sequential
    runs in a long-lived API process each write to the correct file.
    """
    global _structlog_configured

    if log_dir not in _file_handles:
        app_log_path = Path(log_dir) / "app.jsonl"
        app_log_path.parent.mkdir(parents=True, exist_ok=True)
        _file_handles[log_dir] = open(app_log_path, "a", encoding="utf-8")  # noqa: SIM115

    if not _structlog_configured:
        processors: list[Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            JSONRenderer(),
            _write_to_run_file,
        ]
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=False,
        )
        _structlog_configured = True


def bind_run(workflow_id: str, run_id: str, log_dir: str = "") -> None:
    """Bind run context so every log line includes workflow_id, run_id, and log_dir."""
    structlog.contextvars.bind_contextvars(
        workflow_id=workflow_id,
        run_id=run_id,
        log_dir=log_dir,
    )


def log_api_call(
    source: str,
    status: str,
    phase: str,
    *,
    paper_id: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    records: int | None = None,
    error: str | None = None,
    raw_response: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    call_type: str | None = None,
) -> None:
    """Log an API call event."""
    payload: dict[str, Any] = {"source": source, "status": status, "phase": phase}
    if call_type is not None:
        payload["call_type"] = call_type
    if paper_id is not None:
        payload["paper_id"] = paper_id
    if model is not None:
        payload["model"] = model
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    if records is not None:
        payload["records"] = records
    if error is not None:
        payload["error"] = error
    if raw_response is not None and len(raw_response) < 500:
        payload["raw_response"] = raw_response
    elif raw_response is not None:
        payload["raw_response_preview"] = raw_response[:200] + "..."
    if tokens_in is not None:
        payload["tokens_in"] = tokens_in
    if tokens_out is not None:
        payload["tokens_out"] = tokens_out
    if cost_usd is not None:
        payload["cost_usd"] = cost_usd
    logger = structlog.get_logger()
    logger.info("api_call", **payload)


def log_rate_limit_wait(tier: str, slots_used: int, limit: int) -> None:
    """Log rate limit wait event."""
    logger = structlog.get_logger()
    logger.info("rate_limit_wait", tier=tier, slots_used=slots_used, limit=limit)


def log_screening_decision(
    paper_id: str,
    stage: str,
    decision: str,
    rationale: str | None = None,
) -> None:
    """Log a screening decision event."""
    payload: dict[str, Any] = {"paper_id": paper_id, "stage": stage, "decision": decision}
    if rationale is not None:
        payload["rationale"] = rationale
    logger = structlog.get_logger()
    logger.info("screening_decision", **payload)


def log_phase(phase: str, action: str, **summary: Any) -> None:
    """Log phase transition (action: start|done)."""
    logger = structlog.get_logger()
    logger.info("phase", phase=phase, action=action, **summary)


def log_connector_result(
    connector: str,
    status: str,
    records: int | None = None,
    error: str | None = None,
) -> None:
    """Log connector search result."""
    payload: dict[str, Any] = {"connector": connector, "status": status}
    if records is not None:
        payload["records"] = records
    if error is not None:
        payload["error"] = error
    logger = structlog.get_logger()
    logger.info("connector_result", **payload)


# ---------------------------------------------------------------------------
# JSONL replay helpers
# ---------------------------------------------------------------------------

_PASSTHROUGH_EVENTS = frozenset({"api_call", "screening_decision", "rate_limit_wait"})


def normalize_jsonl_event(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one app.jsonl line to the ReviewEvent format consumed by the frontend.

    structlog writes the event name into the "event" key and adds "timestamp",
    "level", "workflow_id", and "run_id". We remap to the frontend's "type" + "ts"
    convention and drop internal fields.
    """
    ev = entry.get("event")
    ts = entry.get("timestamp", "")

    if ev == "phase":
        action = entry.get("action")
        if action == "start":
            return {
                "type": "phase_start",
                "phase": entry.get("phase"),
                "description": entry.get("description", ""),
                "total": entry.get("total"),
                "ts": ts,
            }
        if action == "done":
            return {
                "type": "phase_done",
                "phase": entry.get("phase"),
                "summary": entry.get("summary", {}),
                "total": entry.get("total"),
                "completed": entry.get("completed"),
                "ts": ts,
            }
        return None  # "start" workflow marker -- skip

    if ev == "connector_result":
        return {
            "type": "connector_result",
            "name": entry.get("connector"),
            "status": entry.get("status"),
            "records": entry.get("records"),
            "error": entry.get("error"),
            "ts": ts,
        }

    if ev in _PASSTHROUGH_EVENTS:
        out = {k: v for k, v in entry.items() if k not in ("event", "level", "timestamp", "workflow_id", "run_id", "log_dir")}
        out["type"] = ev
        out["ts"] = ts
        return out

    return None


def load_events_from_jsonl(path: str) -> list[dict[str, Any]]:
    """Read an app.jsonl file and return normalized ReviewEvent dicts.

    Skips lines that fail to parse or map to no known event type.
    """
    result: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                normalized = normalize_jsonl_event(entry)
                if normalized is not None:
                    result.append(normalized)
    except OSError:
        pass
    return result
