from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, GraphRunContext

from src.orchestration.runners.writing_runner import run_writing_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import ManuscriptAuditNode


class WritingNode(BaseNode[ReviewState]):
    """Write manuscript sections, validate citations, save drafts."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> ManuscriptAuditNode:
        state = ctx.state
        await run_writing_node(state, ctx)
        from src.orchestration.workflow import ManuscriptAuditNode

        return ManuscriptAuditNode()
