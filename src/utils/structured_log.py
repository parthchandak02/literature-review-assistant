"""Structured logging for machine-parseable audit trail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from structlog.processors import JSONRenderer
from structlog.typing import Processor

_configured = False
_logger: structlog.BoundLogger | None = None


def configure_run_logging(log_dir: str) -> None:
    """One-time setup at workflow start. Writes JSON lines to {log_dir}/app.jsonl."""
    global _configured, _logger
    if _configured:
        return
    app_log_path = Path(log_dir) / "app.jsonl"
    app_log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handle = open(app_log_path, "a", encoding="utf-8")

    def _file_logger_factory(*args: Any, **kwargs: Any) -> structlog.PrintLogger:
        return structlog.PrintLogger(file_handle)

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        JSONRenderer(),
    ]
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=_file_logger_factory,
        cache_logger_on_first_use=True,
    )
    _configured = True
    _logger = structlog.get_logger()


def bind_run(workflow_id: str, run_id: str) -> None:
    """Bind workflow context so every log includes workflow_id and run_id."""
    structlog.contextvars.bind_contextvars(workflow_id=workflow_id, run_id=run_id)


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
) -> None:
    """Log an API call event."""
    payload: dict[str, Any] = {"source": source, "status": status, "phase": phase}
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
    if _logger is not None:
        _logger.info("api_call", **payload)


def log_rate_limit_wait(tier: str, slots_used: int, limit: int) -> None:
    """Log rate limit wait event."""
    if _logger is not None:
        _logger.info("rate_limit_wait", tier=tier, slots_used=slots_used, limit=limit)


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
    if _logger is not None:
        _logger.info("screening_decision", **payload)


def log_phase(phase: str, action: str, **summary: Any) -> None:
    """Log phase transition (action: start|done)."""
    if _logger is not None:
        _logger.info("phase", phase=phase, action=action, **summary)


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
    if _logger is not None:
        _logger.info("connector_result", **payload)
