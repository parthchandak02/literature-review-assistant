"""Tests for checkpoint-backed UI event replay alignment."""

from __future__ import annotations

from src.web.event_replay import enrich_events_with_checkpoints, ui_phase_completed


def test_ui_phase_completed_maps_fulltext_checkpoint() -> None:
    checkpoints = {
        "phase_2_search": "completed",
        "phase_3_screening": "completed",
        "phase_3b_fulltext": "completed",
    }
    assert ui_phase_completed(checkpoints, "fulltext_pdf_retrieval") is True
    assert ui_phase_completed(checkpoints, "phase_4_extraction_quality") is False


def test_enrich_events_injects_fulltext_from_phase_3b_checkpoint() -> None:
    events = [
        {"type": "phase_done", "phase": "phase_2_search", "ts": "2026-05-28T00:00:00Z"},
        {"type": "phase_done", "phase": "phase_3_screening", "ts": "2026-05-28T00:00:01Z"},
    ]
    checkpoints = {
        "phase_2_search": "completed",
        "phase_3_screening": "completed",
        "phase_3b_fulltext": "completed",
        "phase_4_extraction_quality": "completed",
    }

    enriched = enrich_events_with_checkpoints(events, checkpoints)
    done_phases = {event["phase"] for event in enriched if event.get("type") == "phase_done"}

    assert "fulltext_pdf_retrieval" in done_phases
    assert "phase_4_extraction_quality" in done_phases
    synthetic = [event for event in enriched if event.get("synthetic")]
    assert any(event["phase"] == "fulltext_pdf_retrieval" for event in synthetic)


def test_enrich_events_inserts_before_terminal_marker() -> None:
    events = [
        {"type": "phase_done", "phase": "phase_2_search", "ts": "2026-05-28T00:00:00Z"},
        {"type": "done", "outputs": {}, "ts": "2026-05-28T00:00:02Z"},
    ]
    checkpoints = {"phase_2_search": "completed", "phase_3_screening": "completed"}

    enriched = enrich_events_with_checkpoints(events, checkpoints)
    assert enriched[1]["phase"] == "phase_3_screening"
    assert enriched[1]["synthetic"] is True
    assert enriched[2]["type"] == "done"


def test_enrich_events_skips_existing_phase_done() -> None:
    events = [
        {"type": "phase_done", "phase": "fulltext_pdf_retrieval", "ts": "2026-05-28T00:00:00Z"},
    ]
    checkpoints = {"phase_3b_fulltext": "completed"}

    enriched = enrich_events_with_checkpoints(events, checkpoints)
    assert len(enriched) == 1
