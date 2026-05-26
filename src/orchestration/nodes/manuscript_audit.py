from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.orchestration.runners.audit_runner import run_manuscript_audit_node
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import FinalizeNode


class ManuscriptAuditNode(BaseNode[ReviewState]):
    """Run bounded profile-based manuscript audit before finalize."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> FinalizeNode | End[dict]:
        state = ctx.state
        result = await run_manuscript_audit_node(state, ctx)
        if result is not None:
            return result
        from src.orchestration.workflow import FinalizeNode

        return FinalizeNode()
