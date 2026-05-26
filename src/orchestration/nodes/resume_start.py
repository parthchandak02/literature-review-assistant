from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.start_runner import resolve_resume_next_phase
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.embedding_node import EmbeddingNode
    from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
    from src.orchestration.nodes.human_review import HumanReviewCheckpointNode
    from src.orchestration.workflow import (
        ExtractionQualityNode,
        FinalizeNode,
        ManuscriptAuditNode,
        PreWritingGateNode,
        ScreeningNode,
        SearchNode,
        SynthesisNode,
        WritingNode,
    )


class ResumeStartNode(BaseNode[ReviewState]):
    """Entry node for resume: loads state, configures logging, routes to next phase."""

    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> (
        SearchNode
        | ScreeningNode
        | HumanReviewCheckpointNode
        | ExtractionQualityNode
        | EmbeddingNode
        | SynthesisNode
        | KnowledgeGraphNode
        | PreWritingGateNode
        | WritingNode
        | ManuscriptAuditNode
        | FinalizeNode
    ):
        state = ctx.state
        phase = await resolve_resume_next_phase(state)
        from src.orchestration.embedding_node import EmbeddingNode
        from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
        from src.orchestration.nodes.human_review import HumanReviewCheckpointNode
        from src.orchestration.workflow import (
            ExtractionQualityNode,
            FinalizeNode,
            ManuscriptAuditNode,
            PreWritingGateNode,
            ScreeningNode,
            SearchNode,
            SynthesisNode,
            WritingNode,
        )

        if phase == "human_review_checkpoint":
            return HumanReviewCheckpointNode()
        if phase == "phase_2_search":
            return SearchNode()
        if phase == "phase_3_screening":
            return ScreeningNode()
        if phase == "phase_4_extraction_quality":
            return ExtractionQualityNode()
        if phase == "phase_4b_embedding":
            return EmbeddingNode()
        if phase == "phase_5_synthesis":
            return SynthesisNode()
        if phase == "phase_5b_knowledge_graph":
            return KnowledgeGraphNode()
        if phase == "phase_5c_pre_writing_gate":
            return PreWritingGateNode()
        if phase == "phase_6_writing":
            return WritingNode()
        if phase == "phase_7_audit":
            return ManuscriptAuditNode()
        if phase == "finalize":
            return FinalizeNode()
        return SearchNode()
