"""Entry nodes extracted from workflow monolith."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.start_runner import resolve_resume_next_phase, run_start_node

if TYPE_CHECKING:
    from src.orchestration.state import ReviewState


class ResumeStartNode(BaseNode["ReviewState"]):
    """Entry node for resume: routes to the next pending runtime phase."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> BaseNode[ReviewState]:
        from src.orchestration.workflow import (
            EmbeddingNode,
            ExtractionQualityNode,
            FinalizeNode,
            HumanReviewCheckpointNode,
            KnowledgeGraphNode,
            PreWritingGateNode,
            ScreeningNode,
            SearchNode,
            SynthesisNode,
            WritingNode,
        )

        phase = await resolve_resume_next_phase(ctx.state)
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
            # Backward compatibility for historic checkpoint rows only.
            return FinalizeNode()
        if phase == "finalize":
            return FinalizeNode()
        return SearchNode()


class StartNode(BaseNode["ReviewState"]):
    """Entry node for new workflows."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> BaseNode[ReviewState]:
        from src.orchestration.workflow import SearchNode

        await run_start_node(ctx.state)
        return SearchNode()
