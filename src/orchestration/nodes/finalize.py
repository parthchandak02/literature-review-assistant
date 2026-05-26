from __future__ import annotations

from pydantic_graph import BaseNode, End, GraphRunContext

from src.orchestration.runners.finalize_runner import run_finalize_node
from src.orchestration.state import ReviewState


class FinalizeNode(BaseNode[ReviewState]):
    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> End[dict[str, str | int | float | bool | dict[str, int] | dict[str, str]]]:
        state = ctx.state
        summary = await run_finalize_node(state, ctx)
        return End(summary)
