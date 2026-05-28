"""Unit tests for lifecycle reconciliation."""

from __future__ import annotations

from src.web.lifecycle_reconciler import LifecycleReconciler


def test_running_heartbeat_stale_when_no_timestamps() -> None:
    reconciler = LifecycleReconciler(
        stale_threshold_seconds=120,
        stale_grace_seconds=120,
        bump_metric=lambda _name: None,
    )

    class Row:
        def __getitem__(self, key: str) -> None:
            return None

    assert reconciler.running_heartbeat_stale(Row()) is True
