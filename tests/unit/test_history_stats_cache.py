"""Unit tests for registry-backed history stats caching helpers."""

from __future__ import annotations

from src.web.routers.history import (
    should_use_registry_stats,
    stats_payload_from_registry_row,
)


def test_should_use_registry_stats_when_terminal_and_timestamp_present() -> None:
    assert (
        should_use_registry_stats(
            reg_status="completed",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id=None,
        )
        is True
    )
    assert (
        should_use_registry_stats(
            reg_status="failed",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id=None,
        )
        is True
    )
    assert (
        should_use_registry_stats(
            reg_status="interrupted",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id=None,
        )
        is True
    )


def test_should_use_registry_stats_rejects_missing_timestamp() -> None:
    assert (
        should_use_registry_stats(
            reg_status="completed",
            stats_updated_at=None,
            live_run_id=None,
        )
        is False
    )
    assert (
        should_use_registry_stats(
            reg_status="completed",
            stats_updated_at="",
            live_run_id=None,
        )
        is False
    )


def test_should_use_registry_stats_rejects_live_or_non_terminal() -> None:
    assert (
        should_use_registry_stats(
            reg_status="completed",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id="run-live",
        )
        is False
    )
    assert (
        should_use_registry_stats(
            reg_status="running",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id=None,
        )
        is False
    )
    assert (
        should_use_registry_stats(
            reg_status="awaiting_review",
            stats_updated_at="2026-03-10T12:00:00",
            live_run_id=None,
        )
        is False
    )


def test_stats_payload_from_registry_row_maps_columns() -> None:
    row = {
        "papers_found": 42,
        "papers_included": 7,
        "total_cost": 3.5,
    }
    payload = stats_payload_from_registry_row(row)  # type: ignore[arg-type]
    assert payload == {
        "ok": True,
        "papers_found": 42,
        "papers_included": 7,
        "total_cost": 3.5,
        "artifacts_count": None,
    }
