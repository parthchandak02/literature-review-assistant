"""Unit tests for human-in-the-loop screening checkpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.models.config import ReviewConfig
from src.orchestration.runners.hitl_runner import run_human_review_checkpoint
from src.orchestration.state import ReviewState

_MINIMAL_REVIEW: dict[str, object] = {
    "research_question": "What is the effect of intervention X?",
    "review_type": "systematic",
    "domain": "Health",
    "scope": "Clinical settings",
    "keywords": ["intervention", "health"],
    "date_range_start": 2015,
    "date_range_end": 2026,
    "pico": {
        "population": "Adults",
        "intervention": "Intervention X",
        "comparison": "Usual care",
        "outcome": "Quality of life",
    },
    "inclusion_criteria": ["Adult participants"],
    "exclusion_criteria": ["Animal studies"],
    "target_databases": ["pubmed"],
}


@pytest.mark.asyncio
async def test_human_review_checkpoint_parks_in_web_mode(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-hitl-web" / "run_20260103"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(_MINIMAL_REVIEW)
    settings = MagicMock()
    settings.human_in_the_loop.enabled = True
    rc = MagicMock()
    rc.web_mode = True

    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-hitl-web",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        run_context=rc,
    )

    with (
        patch("src.orchestration.runners.hitl_runner.update_status", new_callable=AsyncMock) as mock_update,
    ):
        paused = await run_human_review_checkpoint(state)

    assert paused is True
    update_calls = [call.args for call in mock_update.await_args_list]
    assert any(call[2] == "awaiting_review" for call in update_calls)
    assert not any(call[2] == "running" for call in update_calls)


@pytest.mark.asyncio
async def test_human_review_checkpoint_cli_timeout_stays_parked(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-hitl-timeout" / "run_20260103"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(_MINIMAL_REVIEW)
    snapshot_path = run_dir / "config_snapshot.yaml"
    snapshot_path.write_text(yaml.safe_dump(review.model_dump(mode="json")), encoding="utf-8")

    settings = MagicMock()
    settings.human_in_the_loop.enabled = True
    settings.human_in_the_loop.poll_interval_seconds = 0
    settings.human_in_the_loop.max_wait_seconds = 1

    state = ReviewState(
        review_path=str(snapshot_path),
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-hitl-timeout",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
    )

    with (
        patch("src.orchestration.runners.hitl_runner.update_status", new_callable=AsyncMock) as mock_update,
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(
            "src.orchestration.runners.hitl_runner.find_by_workflow_id",
            new_callable=AsyncMock,
            return_value=MagicMock(status="awaiting_review"),
        ),
    ):
        paused = await run_human_review_checkpoint(state)

    assert paused is True
    update_calls = [call.args for call in mock_update.await_args_list]
    assert any(call[2] == "awaiting_review" for call in update_calls)
    assert not any(call[2] == "running" for call in update_calls)


@pytest.mark.asyncio
async def test_human_review_checkpoint_cli_polls_until_running(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-hitl-ok" / "run_20260103"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(_MINIMAL_REVIEW)
    settings = MagicMock()
    settings.human_in_the_loop.enabled = True
    settings.human_in_the_loop.poll_interval_seconds = 0
    settings.human_in_the_loop.max_wait_seconds = 5

    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-hitl-ok",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
    )

    statuses = iter(["awaiting_review", "running"])

    async def _fake_find(_run_root: str, _workflow_id: str):
        status = next(statuses, "running")
        return MagicMock(status=status)

    with (
        patch("src.orchestration.runners.hitl_runner.get_db") as mock_get_db,
        patch("src.orchestration.runners.hitl_runner.WorkflowRepository") as mock_repo_cls,
        patch("src.orchestration.runners.hitl_runner.update_status", new_callable=AsyncMock) as mock_update,
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch("src.orchestration.runners.hitl_runner.find_by_workflow_id", side_effect=_fake_find),
    ):
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        mock_repo_cls.return_value = AsyncMock()

        paused = await run_human_review_checkpoint(state)

    assert paused is False
    update_calls = [call.args for call in mock_update.await_args_list]
    assert any(call[2] == "awaiting_review" for call in update_calls)
    assert any(call[2] == "running" for call in update_calls)
