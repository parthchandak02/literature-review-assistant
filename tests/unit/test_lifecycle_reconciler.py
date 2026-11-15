"""Unit tests for lifecycle reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

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


@pytest.mark.asyncio
async def test_collect_terminal_evidence_skips_aiosqlite_when_db_missing(tmp_path: Path) -> None:
    reconciler = LifecycleReconciler(
        stale_threshold_seconds=120,
        stale_grace_seconds=120,
        bump_metric=lambda _name: None,
    )
    missing_db = tmp_path / "missing_dir" / "runtime.db"

    with patch("src.web.lifecycle_reconciler.aiosqlite.connect") as mock_connect:
        evidence = await reconciler.collect_terminal_evidence(str(missing_db))

    mock_connect.assert_not_called()
    assert evidence["terminal_status"] is None
    assert not missing_db.exists()

    summary_dir = tmp_path / "summary_only"
    summary_dir.mkdir()
    (summary_dir / "run_summary.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    summary_db = summary_dir / "runtime.db"

    with patch("src.web.lifecycle_reconciler.aiosqlite.connect") as mock_connect:
        summary_evidence = await reconciler.collect_terminal_evidence(str(summary_db))

    mock_connect.assert_not_called()
    assert summary_evidence["terminal_status"] == "completed"
    assert summary_evidence["source"] == "run_summary"
    assert not summary_db.exists()
