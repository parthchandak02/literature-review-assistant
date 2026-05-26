from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.synthesis_runner import run_synthesis_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.knowledge_graph_node import KnowledgeGraphNode


class SynthesisNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> KnowledgeGraphNode:
        state = ctx.state
        await run_synthesis_node(state, ctx)
        from src.orchestration.knowledge_graph_node import KnowledgeGraphNode

        return KnowledgeGraphNode()
