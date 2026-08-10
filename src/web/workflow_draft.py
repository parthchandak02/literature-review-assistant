"""Reserve workflow IDs and persist config drafts before the pipeline starts."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import (
    DRAFT_REGISTRY_STATUSES,
    allocate_workflow_id,
    find_by_workflow_id,
)
from src.db.workflow_registry import (
    register as register_workflow,
)
from src.orchestration.helpers.runtime import hash_config as helper_hash_config
from src.utils.logging_paths import create_run_paths


async def reserve_workflow_draft(*, run_root: str, topic: str) -> dict[str, str]:
    """Allocate wf-ID, create run dir + runtime.db, register as config_generating."""
    cleaned = topic.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="topic must not be empty")

    workflow_id = await allocate_workflow_id(run_root)
    run_paths = create_run_paths(run_root=run_root, workflow_description=cleaned, workflow_id=workflow_id)
    db_path = str(run_paths.runtime_db)

    async with get_db(db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(workflow_id, cleaned, "")

    await register_workflow(
        run_root=run_root,
        workflow_id=workflow_id,
        topic=cleaned,
        config_hash="",
        db_path=db_path,
        status="config_generating",
    )

    meta_path = run_paths.run_dir / "draft_meta.json"
    meta_path.write_text(
        json.dumps({"topic": cleaned, "workflow_id": workflow_id}, indent=2),
        encoding="utf-8",
    )

    return {
        "workflow_id": workflow_id,
        "db_path": db_path,
        "run_dir": str(run_paths.run_dir),
    }


async def save_workflow_config_draft(
    *,
    run_root: str,
    workflow_id: str,
    review_yaml: str,
) -> None:
    """Persist generated review YAML and mark the workflow config_ready."""
    cleaned_yaml = review_yaml.strip()
    if not cleaned_yaml:
        raise HTTPException(status_code=422, detail="review_yaml must not be empty")

    entry = await find_by_workflow_id(run_root, workflow_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    if entry.status not in DRAFT_REGISTRY_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow {workflow_id} is not a config draft (status={entry.status})",
        )

    run_dir = Path(entry.db_path).parent
    review_path = run_dir / "review.yaml"
    review_path.write_text(cleaned_yaml, encoding="utf-8")

    header = (
        f"# workflow_id: {workflow_id}\n"
        f"# run_dir: {run_dir}\n"
        f"# draft_saved_at: generated\n#\n"
    )
    (run_dir / "config_snapshot.yaml").write_text(header + cleaned_yaml, encoding="utf-8")

    config_hash = helper_hash_config(str(review_path))
    async with get_db(entry.db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(workflow_id, entry.topic, config_hash)

    await register_workflow(
        run_root=run_root,
        workflow_id=workflow_id,
        topic=entry.topic,
        config_hash=config_hash,
        db_path=entry.db_path,
        status="config_ready",
    )
