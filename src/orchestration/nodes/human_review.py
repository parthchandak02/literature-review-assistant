from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.hitl_runner import run_human_review_checkpoint
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import ExtractionQualityNode


class HumanReviewCheckpointNode(BaseNode[ReviewState]):
    """Optional pause between screening and extraction for human review."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> ExtractionQualityNode:
        state = ctx.state
        await run_human_review_checkpoint(state)
        from src.orchestration.workflow import ExtractionQualityNode

        return ExtractionQualityNode()
