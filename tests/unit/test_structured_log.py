from pathlib import Path

from src.utils.structured_log import load_events_from_jsonl


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

