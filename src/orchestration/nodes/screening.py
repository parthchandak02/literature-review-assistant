from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.orchestration.runners.screening_runner import run_screening_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.nodes.human_review import HumanReviewCheckpointNode


class ScreeningNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> HumanReviewCheckpointNode | End[dict]:
        state = ctx.state
        result = await run_screening_node(state, ctx)
        if result is not None:
            return result
        from src.orchestration.nodes.human_review import HumanReviewCheckpointNode

        return HumanReviewCheckpointNode()
