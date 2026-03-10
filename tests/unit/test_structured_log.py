from pathlib import Path

from src.utils.structured_log import load_events_from_jsonl, normalize_jsonl_event


def test_load_events_from_jsonl_supports_double_encoded_lines(tmp_path: Path) -> None:
    path = tmp_path / "app.jsonl"
    line = (
        "\"{\\\"phase\\\": \\\"phase_2_search\\\", \\\"action\\\": \\\"start\\\", "
        "\\\"description\\\": \\\"Running connectors...\\\", \\\"event\\\": \\\"phase\\\", "
        "\\\"timestamp\\\": \\\"2026-03-10T17:41:24.600698Z\\\"}\""
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

