"""Early workflow reservation before config generation or pipeline start."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.web.workflow_draft import reserve_workflow_draft, save_workflow_config_draft

router = APIRouter(tags=["workflow-draft"])


class ReserveWorkflowDraftRequest(BaseModel):
    topic: str = Field(min_length=1)
    run_root: str = "runs"


class ReserveWorkflowDraftResponse(BaseModel):
    workflow_id: str
    db_path: str
    run_dir: str


class SaveConfigDraftRequest(BaseModel):
    review_yaml: str = Field(min_length=1)
    run_root: str = "runs"


@router.post("/api/workflow/reserve", response_model=ReserveWorkflowDraftResponse)
async def reserve_workflow(req: ReserveWorkflowDraftRequest) -> ReserveWorkflowDraftResponse:
    payload = await reserve_workflow_draft(run_root=req.run_root, topic=req.topic)
    return ReserveWorkflowDraftResponse(**payload)


@router.put("/api/workflow/{workflow_id}/config-draft")
async def save_config_draft(workflow_id: str, req: SaveConfigDraftRequest) -> dict[str, str]:
    await save_workflow_config_draft(
        run_root=req.run_root,
        workflow_id=workflow_id,
        review_yaml=req.review_yaml,
    )
    return {"workflow_id": workflow_id, "status": "config_ready"}
