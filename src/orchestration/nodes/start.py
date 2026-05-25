from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.start_runner import run_start_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import SearchNode


class StartNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> SearchNode:
        state = ctx.state
        await run_start_node(state)
        from src.orchestration.workflow import SearchNode

        return SearchNode()
