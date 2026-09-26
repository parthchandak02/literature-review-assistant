"""`prospero` CLI regeneration works on finished runs without replaying phases."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from rich.console import Console

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import register as register_workflow
from src.main import _run_prospero, main
from src.orchestration import regenerate_prospero_form
from src.orchestration.context import RunContext
from src.orchestration.phase_catalog import PHASE_ORDER
from src.orchestration.resume import ResumeNotAllowedError, validate_resume_allowed
from tests.integration.conftest import MINIMAL_REVIEW, init_runtime_workflow_db

_WF = "wf-prospero-regen"


async def _seed_completed_run(tmp_path: Path) -> tuple[Path, Path]:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-01-01" / _WF / "run_01"
    db_path = run_dir / "runtime.db"
    await init_runtime_workflow_db(db_path, _WF, topic=MINIMAL_REVIEW["research_question"], status="completed")
    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        for phase in PHASE_ORDER:
            await repo.save_checkpoint(_WF, phase, papers_processed=0, status="completed")
        await db.commit()
    await register_workflow(
        run_root=str(run_root),
        workflow_id=_WF,
        topic=MINIMAL_REVIEW["research_question"],
        config_hash="hash",
        db_path=str(db_path),
        status="completed",
    )
    (run_dir / "config_snapshot.yaml").write_text(yaml.safe_dump(MINIMAL_REVIEW, sort_keys=False), encoding="utf-8")
    return run_root, db_path


async def _checkpoints(db_path: Path) -> dict[str, str]:
    async with get_db(str(db_path)) as db:
        return await WorkflowRepository(db).get_checkpoints(_WF)


@pytest.mark.asyncio
async def test_regenerate_prospero_on_completed_run_does_not_replay(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    review_path, settings_path = minimal_config_paths
    run_root, db_path = await _seed_completed_run(tmp_path)
    with pytest.raises(ResumeNotAllowedError):
        await validate_resume_allowed(str(db_path), _WF, from_phase="finalize")
    before = await _checkpoints(db_path)

    with patch("src.orchestration.workflow.run_graph_with_budget", new=AsyncMock()) as graph_run:
        path = await regenerate_prospero_form(
            workflow_id=_WF,
            review_path=str(review_path),
            settings_path=str(settings_path),
            run_root=str(run_root),
        )

    graph_run.assert_not_awaited()
    assert path == db_path.parent / "doc_prospero_registration.docx"
    assert path.exists() and path.stat().st_size > 0
    assert (db_path.parent / "doc_prospero_registration.md").exists()
    assert await _checkpoints(db_path) == before


@pytest.mark.asyncio
async def test_run_prospero_cli_helper_returns_docx_for_completed_run(
    tmp_path: Path,
    minimal_config_paths: tuple[Path, Path],
) -> None:
    review_path, settings_path = minimal_config_paths
    run_root, db_path = await _seed_completed_run(tmp_path)

    path = await _run_prospero(
        workflow_id=_WF,
        run_root=str(run_root),
        review_path=str(review_path),
        settings_path=str(settings_path),
        run_context=RunContext(console=Console(quiet=True)),
    )

    assert Path(path).exists()
    assert await _checkpoints(db_path) == {phase: "completed" for phase in PHASE_ORDER}


def test_prospero_cli_unknown_workflow_exits_nonzero(tmp_path: Path) -> None:
    code = main(["prospero", "--workflow-id", "wf-missing", "--run-root", str(tmp_path / "runs")])
    assert code == 1
