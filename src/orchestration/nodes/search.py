from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.orchestration.runners.search_runner import run_search_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import ScreeningNode


class SearchNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> ScreeningNode | End[dict]:
        state = ctx.state
        result = await run_search_node(state, ctx)
        if result is not None:
            return result
        from src.orchestration.workflow import ScreeningNode

        return ScreeningNode()
