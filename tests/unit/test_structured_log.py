import asyncio
import json
from pathlib import Path

import pytest
import structlog

from src.utils.structured_log import (
    bind_run,
    configure_run_logging,
    drain_log_writer,
    load_events_from_jsonl,
    normalize_jsonl_event,
    shutdown_log_writer,
)


@pytest.fixture
async def structured_log_run(tmp_path: Path):
    """Configure per-run logging and tear down async writer state."""
    log_dir = str(tmp_path)
    configure_run_logging(log_dir)
    bind_run("wf-test", "run-test", log_dir)
    yield log_dir
    await shutdown_log_writer()
    import src.utils.structured_log as sl

    for fh in sl._file_handles.values():
        fh.close()
    sl._file_handles.clear()
    sl._structlog_configured = False
    structlog.reset_defaults()


@pytest.mark.asyncio
async def test_write_to_run_file_uses_async_queue(structured_log_run: str, tmp_path: Path) -> None:
    logger = structlog.get_logger()
    logger.info("queued_event", detail="async")
    await drain_log_writer()

    lines = (tmp_path / "app.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    if isinstance(entry, str):
        entry = json.loads(entry)
    assert entry["event"] == "queued_event"
    assert entry["detail"] == "async"
    assert entry["workflow_id"] == "wf-test"
    assert entry["run_id"] == "run-test"


def test_load_events_from_jsonl_supports_double_encoded_lines(tmp_path: Path) -> None:
    path = tmp_path / "app.jsonl"
    line = (
        '"{\\"phase\\": \\"phase_2_search\\", \\"action\\": \\"start\\", '
        '\\"description\\": \\"Running connectors...\\", \\"event\\": \\"phase\\", '
        '\\"timestamp\\": \\"2026-03-10T17:41:24.600698Z\\"}"'
    )
    path.write_text(line + "\n", encoding="utf-8")

    events = load_events_from_jsonl(str(path))
    assert len(events) == 1
    assert events[0]["type"] == "phase_start"
    assert events[0]["phase"] == "phase_2_search"


def test_normalize_jsonl_event_preserves_contract_fields() -> None:
    normalized = normalize_jsonl_event(
        {
            "event": "connector_result",
            "timestamp": "2026-03-10T17:41:24.600698Z",
            "connector": "pubmed",
            "status": "error",
            "error": "429",
            "reason_code": "connector_degraded",
            "reason_label": "Connector degraded; fallback path used",
            "action": "fallback",
            "entity_type": "connector",
            "entity_id": "pubmed",
        }
    )
    assert normalized is not None
    assert normalized["type"] == "connector_result"
    assert normalized["reason_code"] == "connector_degraded"
    assert normalized["reason_label"] == "Connector degraded; fallback path used"
    assert normalized["action"] == "fallback"
    assert normalized["entity_type"] == "connector"
    assert normalized["entity_id"] == "pubmed"


def test_normalize_jsonl_event_preserves_phase_contract_fields() -> None:
    normalized = normalize_jsonl_event(
        {
            "event": "phase",
            "timestamp": "2026-03-10T17:41:24.600698Z",
            "phase": "phase_3_screening",
            "action": "done",
            "summary": {"included": 7},
            "reason_code": "phase_summary",
            "reason_label": "Phase completed",
            "entity_type": "phase",
            "entity_id": "phase_3_screening",
        }
    )
    assert normalized is not None
    assert normalized["type"] == "phase_done"
    assert normalized["reason_code"] == "phase_summary"
    assert normalized["reason_label"] == "Phase completed"
    assert normalized["action"] == "done"
    assert normalized["entity_type"] == "phase"
    assert normalized["entity_id"] == "phase_3_screening"


@pytest.mark.asyncio
async def test_shutdown_log_writer_drains_pending_lines(structured_log_run: str, tmp_path: Path) -> None:
    logger = structlog.get_logger()
    for index in range(5):
        logger.info("shutdown_pressure", index=index)
    await shutdown_log_writer()

    lines = (tmp_path / "app.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    indices: set[int] = set()
    for line in lines:
        entry = json.loads(line)
        if isinstance(entry, str):
            entry = json.loads(entry)
        indices.add(int(entry["index"]))
    assert indices == {0, 1, 2, 3, 4}


@pytest.mark.asyncio
async def test_concurrent_log_writes_are_all_persisted(structured_log_run: str, tmp_path: Path) -> None:
    logger = structlog.get_logger()

    async def _emit(index: int) -> None:
        logger.info("concurrent_event", index=index)
        await asyncio.sleep(0)

    await asyncio.gather(*[_emit(i) for i in range(20)])
    await drain_log_writer()

    lines = (tmp_path / "app.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 20
