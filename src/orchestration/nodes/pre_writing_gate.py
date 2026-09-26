from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.models.workflow import WorkflowRunResult
from src.orchestration.runners.pre_writing_gate_runner import run_pre_writing_gate_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.embedding_node import EmbeddingNode
    from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
    from src.orchestration.workflow import ExtractionQualityNode, SynthesisNode, WritingNode


class PreWritingGateNode(BaseNode[ReviewState]):
    """Validate canonical prerequisites before writing and rewind automatically when safe."""

    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> (
        WritingNode
        | ExtractionQualityNode
        | EmbeddingNode
        | SynthesisNode
        | KnowledgeGraphNode
        | End[WorkflowRunResult]
    ):
        state = ctx.state
        return await run_pre_writing_gate_node(state, ctx)
