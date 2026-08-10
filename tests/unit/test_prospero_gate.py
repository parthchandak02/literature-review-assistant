"""Unit tests for PROSPERO registration gate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.models.config import ProtocolRegistration, ReviewConfig
from src.orchestration.helpers.prospero_validation import validate_prospero_id
from src.orchestration.runners.prospero_gate_runner import run_prospero_gate
from src.orchestration.state import ReviewState
from src.protocol.generator import ProtocolGenerator

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


def test_validate_prospero_id_accepts_valid_crd() -> None:
    assert validate_prospero_id("crd42025678901") == "CRD42025678901"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "CRD123",
        "CRD42025",
        "OSF123456",
        "CRD42025678901X",
    ],
)
def test_validate_prospero_id_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        validate_prospero_id(value)


def test_generate_pre_registration_artifacts_writes_expected_files(tmp_path: Path) -> None:
    config = ReviewConfig.model_validate(
        {
            **_MINIMAL_REVIEW,
            "protocol": ProtocolRegistration().model_dump(),
        }
    )
    generator = ProtocolGenerator(output_dir=str(tmp_path))
    paths = generator.generate_pre_registration_artifacts("wf-test", config, None)

    assert paths["protocol"].exists()
    assert paths["prospero_markdown"].exists()
    assert paths["prospero_docx"].exists()

    prospero_text = paths["prospero_markdown"].read_text(encoding="utf-8")
    assert "[PENDING - submit to PROSPERO]" in prospero_text
    assert "[TO BE COMPLETED]" in prospero_text
    assert "Records retrieved per database" not in prospero_text
    assert "POST-RUN SEARCH COUNTS" not in prospero_text


@pytest.mark.asyncio
async def test_run_prospero_gate_parks_in_web_mode(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-0003" / "run_20260103"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(
        {
            **_MINIMAL_REVIEW,
            "research_question": "Web pause review",
        }
    )

    settings = MagicMock()
    rc = MagicMock()
    rc.web_mode = True

    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-0003",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        run_context=rc,
    )
    state.artifacts["protocol"] = str(run_dir / "doc_protocol.md")
    state.artifacts["prospero_form_md"] = str(run_dir / "doc_prospero_registration.md")
    state.artifacts["prospero_form"] = str(run_dir / "doc_prospero_registration.docx")

    with (
        patch("src.orchestration.runners.prospero_gate_runner.get_db") as mock_get_db,
        patch("src.orchestration.runners.prospero_gate_runner.WorkflowRepository") as mock_repo_cls,
        patch("src.orchestration.runners.prospero_gate_runner.register_workflow", new_callable=AsyncMock),
        patch("src.orchestration.runners.prospero_gate_runner.update_status", new_callable=AsyncMock) as mock_update,
        patch(
            "src.orchestration.runners.prospero_gate_runner.find_by_workflow_id",
            new_callable=AsyncMock,
            return_value=MagicMock(status="running"),
        ),
        patch(
            "src.protocol.generator.ProtocolGenerator.generate_pre_registration_artifacts",
            return_value={
                "protocol": run_dir / "doc_protocol.md",
                "prospero_markdown": run_dir / "doc_prospero_registration.md",
                "prospero_docx": run_dir / "doc_prospero_registration.docx",
            },
        ),
        patch("src.orchestration.runners.prospero_gate_runner.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        mock_repo_cls.return_value = AsyncMock()

        paused = await run_prospero_gate(state)

    assert paused is True
    mock_sleep.assert_not_awaited()
    update_calls = [call.args for call in mock_update.await_args_list]
    assert any(call[2] == "awaiting_prospero" for call in update_calls)
    assert not any(call[2] == "running" for call in update_calls)


@pytest.mark.asyncio
async def test_run_prospero_gate_polls_until_running(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-0001" / "run_20260101"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(
        {
            **_MINIMAL_REVIEW,
            "research_question": "Test review question for PROSPERO gate",
        }
    )
    snapshot_path = run_dir / "config_snapshot.yaml"
    snapshot_path.write_text(yaml.safe_dump(review.model_dump(mode="json")), encoding="utf-8")

    settings = MagicMock()
    settings.human_in_the_loop.poll_interval_seconds = 0
    settings.human_in_the_loop.max_wait_seconds = 1

    state = ReviewState(
        review_path=str(snapshot_path),
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-0001",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        run_id="20260101",
    )
    state.artifacts["protocol"] = str(run_dir / "doc_protocol.md")
    state.artifacts["prospero_form_md"] = str(run_dir / "doc_prospero_registration.md")
    state.artifacts["prospero_form"] = str(run_dir / "doc_prospero_registration.docx")

    statuses = iter(["awaiting_prospero", "running"])

    async def _fake_find(_run_root: str, _workflow_id: str):
        status = next(statuses, "running")
        return MagicMock(status=status)

    with (
        patch("src.orchestration.runners.prospero_gate_runner.get_db") as mock_get_db,
        patch("src.orchestration.runners.prospero_gate_runner.WorkflowRepository") as mock_repo_cls,
        patch("src.orchestration.runners.prospero_gate_runner.register_workflow", new_callable=AsyncMock),
        patch("src.orchestration.runners.prospero_gate_runner.update_status", new_callable=AsyncMock) as mock_update,
        patch("src.orchestration.runners.prospero_gate_runner.find_by_workflow_id", side_effect=_fake_find),
        patch(
            "src.protocol.generator.ProtocolGenerator.generate_pre_registration_artifacts",
            return_value={
                "protocol": run_dir / "doc_protocol.md",
                "prospero_markdown": run_dir / "doc_prospero_registration.md",
                "prospero_docx": run_dir / "doc_prospero_registration.docx",
            },
        ),
    ):
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        paused = await run_prospero_gate(state)

    assert paused is False
    mock_repo.save_checkpoint.assert_awaited_once_with("wf-0001", "phase_1_prospero_gate", papers_processed=0)
    update_calls = [call.args for call in mock_update.await_args_list]
    assert any(call[2] == "awaiting_prospero" for call in update_calls)
    assert any(call[2] == "running" for call in update_calls)


@pytest.mark.asyncio
async def test_run_prospero_gate_skips_poll_when_already_registered(tmp_path: Path) -> None:
    run_dir = tmp_path / "wf-0002" / "run_20260102"
    run_dir.mkdir(parents=True)
    db_path = run_dir / "runtime.db"
    db_path.write_text("", encoding="utf-8")

    review = ReviewConfig.model_validate(
        {
            **_MINIMAL_REVIEW,
            "research_question": "Registered review",
            "protocol": {
                "registered": True,
                "registration_number": "CRD42025678901",
                "registration_date": "2026-01-15",
            },
        }
    )

    settings = MagicMock()
    settings.human_in_the_loop.poll_interval_seconds = 5
    settings.human_in_the_loop.max_wait_seconds = 30

    state = ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-0002",
        review=review,
        settings=settings,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
    )
    state.artifacts["protocol"] = str(run_dir / "doc_protocol.md")
    state.artifacts["prospero_form_md"] = str(run_dir / "doc_prospero_registration.md")
    state.artifacts["prospero_form"] = str(run_dir / "doc_prospero_registration.docx")

    with (
        patch("src.orchestration.runners.prospero_gate_runner.get_db") as mock_get_db,
        patch("src.orchestration.runners.prospero_gate_runner.WorkflowRepository") as mock_repo_cls,
        patch("src.orchestration.runners.prospero_gate_runner.register_workflow", new_callable=AsyncMock),
        patch("src.orchestration.runners.prospero_gate_runner.update_status", new_callable=AsyncMock),
        patch(
            "src.orchestration.runners.prospero_gate_runner.find_by_workflow_id",
            new_callable=AsyncMock,
            return_value=MagicMock(status="running"),
        ),
        patch(
            "src.protocol.generator.ProtocolGenerator.generate_pre_registration_artifacts",
            return_value={
                "protocol": run_dir / "doc_protocol.md",
                "prospero_markdown": run_dir / "doc_prospero_registration.md",
                "prospero_docx": run_dir / "doc_prospero_registration.docx",
            },
        ),
        patch("src.orchestration.runners.prospero_gate_runner.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_db = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_db
        mock_repo_cls.return_value = AsyncMock()

        paused = await run_prospero_gate(state)

    assert paused is False
    mock_sleep.assert_not_awaited()
