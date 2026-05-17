"""Thin web-facing seam around orchestration entrypoints."""

from __future__ import annotations

from src.orchestration.context import RunContext
from src.orchestration.workflow import run_workflow, run_workflow_resume


async def start_workflow_run(
    *,
    review_path: str,
    settings_path: str,
    run_root: str,
    run_context: RunContext | None,
    parent_db_path: str | None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    """Start a fresh workflow from web/API callers."""
    return await run_workflow(
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
        run_context=run_context,
        fresh=True,
        parent_db_path=parent_db_path,
    )


async def resume_workflow_run(
    *,
    workflow_id: str,
    review_path: str,
    settings_path: str,
    run_root: str,
    run_context: RunContext | None,
    from_phase: str | None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    """Resume an existing workflow from web/API callers."""
    return await run_workflow_resume(
        workflow_id=workflow_id,
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
        run_context=run_context,
        from_phase=from_phase,
    )
