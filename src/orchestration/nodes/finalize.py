from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext

from src.models.workflow import WorkflowRunResult
from src.orchestration.runners.finalize_runner import run_finalize_node
from src.orchestration.state import ReviewState


class FinalizeNode(BaseNode[ReviewState]):
    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> End[WorkflowRunResult]:
        state = ctx.state
        summary = await run_finalize_node(state, ctx)
        return End(WorkflowRunResult.from_summary(summary))
