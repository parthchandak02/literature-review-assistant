from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import BaseNode, End, GraphRunContext

from src.models.workflow import WorkflowRunResult
from src.orchestration.runners.prospero_gate_runner import run_prospero_gate
from src.orchestration.state import ReviewState

if TYPE_CHECKING:
    from src.orchestration.workflow import SearchNode


class ProsperoGateNode(BaseNode[ReviewState]):
    """Pause after start until PROSPERO registration is submitted."""

    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> SearchNode | End[WorkflowRunResult]:
        state = ctx.state
        paused = await run_prospero_gate(state)
        if paused:
            return End(WorkflowRunResult.awaiting_prospero(state.workflow_id, state.db_path))
        from src.orchestration.workflow import SearchNode

        return SearchNode()
