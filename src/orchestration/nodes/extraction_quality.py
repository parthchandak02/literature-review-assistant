from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.orchestration.runners.extraction_runner import run_extraction_quality_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.embedding_node import EmbeddingNode


class ExtractionQualityNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> EmbeddingNode | End[dict]:
        state = ctx.state
        result = await run_extraction_quality_node(state, ctx)
        if result is not None:
            return result
        from src.orchestration.embedding_node import EmbeddingNode

        return EmbeddingNode()
