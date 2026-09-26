"""Pre-writing gate rewind bound survives the gate's own rollback (no endless rewind loop)."""

from __future__ import annotations

import pytest
from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.orchestration.embedding_node import EmbeddingNode
from src.orchestration.nodes.pre_writing_gate import PreWritingGateNode
from src.orchestration.state import ReviewState
from tests.integration.conftest import WorkflowDbFixture
from tests.integration.test_graph_transitions import _seed_pre_writing_blocked_state

_GATE_PHASE = "phase_5c_pre_writing_gate"
_GATE_STEP = "pre_writing_validation"


def _ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


@pytest.mark.asyncio
async def test_persistent_gate_failure_rewinds_once_then_blocks(tmp_workflow_db: WorkflowDbFixture) -> None:
    state = await _seed_pre_writing_blocked_state(tmp_workflow_db, rewinds_exhausted=False)

    first = await PreWritingGateNode().run(_ctx(state))
    assert isinstance(first, EmbeddingNode)

    async with get_db(str(tmp_workflow_db.db_path)) as db:
        repo = WorkflowRepository(db)
        policies = await repo.list_recovery_policies(tmp_workflow_db.workflow_id, _GATE_PHASE)
    assert len(policies) == 1
    assert policies[0].current_rewinds == 1

    # Rewind target did not fix the blocking condition: the second visit must not rewind again.
    with pytest.raises(RuntimeError, match="pre-writing gate blocked"):
        await PreWritingGateNode().run(_ctx(state))

    async with get_db(str(tmp_workflow_db.db_path)) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(tmp_workflow_db.workflow_id)
        policies = await repo.list_recovery_policies(tmp_workflow_db.workflow_id, _GATE_PHASE)
    assert checkpoints[_GATE_PHASE] == "blocked"
    assert policies[0].current_rewinds == 1


@pytest.mark.asyncio
async def test_gate_rewind_preserves_gate_policy_but_user_rollback_clears_it(
    tmp_workflow_db: WorkflowDbFixture,
) -> None:
    from src.orchestration.helpers.pre_writing_gate import rewind_pre_writing_phase

    wf = tmp_workflow_db.workflow_id
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.get_or_create_recovery_policy(wf, _GATE_PHASE, _GATE_STEP, max_retries=0, max_rewinds=1)
        await repo.get_or_create_recovery_policy(wf, "phase_5_synthesis", "synthesis", max_rewinds=1)
        await repo.increment_rewind_count(wf, _GATE_PHASE, _GATE_STEP)

        await rewind_pre_writing_phase(repository=repo, workflow_id=wf, rewind_phase="phase_4_extraction_quality")
        await db.commit()
        kept = await repo.list_recovery_policies(wf)
        assert {(p.phase, p.current_rewinds) for p in kept} == {(_GATE_PHASE, 1)}

        # Explicit user resume-from-phase rollback still resets every downstream policy.
        await repo.rollback_phase_data(wf, "phase_4_extraction_quality")
        await db.commit()
        assert await repo.list_recovery_policies(wf) == []
