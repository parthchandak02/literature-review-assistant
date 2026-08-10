from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.models.workflow import WorkflowRunResult
from src.orchestration.runners.hitl_runner import run_human_review_checkpoint
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import ExtractionQualityNode


class HumanReviewCheckpointNode(BaseNode[ReviewState]):
    """Optional pause between screening and extraction for human review."""

    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> ExtractionQualityNode | End[WorkflowRunResult]:
        state = ctx.state
        paused = await run_human_review_checkpoint(state)
        if paused:
            return End(WorkflowRunResult.awaiting_review(state.workflow_id, state.db_path))
        from src.orchestration.workflow import ExtractionQualityNode

        return ExtractionQualityNode()
