"""gates.cost_budget_max stops the workflow before the next paid phase."""

from __future__ import annotations

import json

import pytest

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CostRecord, GateStatus
from src.models.workflow import WorkflowRunStatus
from src.orchestration.gates import GateRunner
from src.orchestration.nodes.search import SearchNode
from src.orchestration.state import ReviewState
from src.orchestration.workflow import run_graph_with_budget
from tests.integration.conftest import WorkflowDbFixture


async def _state(fixture: WorkflowDbFixture, *, spent: float, budget: float, profile: str) -> ReviewState:
    async with get_db(str(fixture.db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.save_cost_record(
            CostRecord(
                workflow_id=fixture.workflow_id,
                model="test:model",
                phase="phase_3_screening",
                tokens_in=10,
                tokens_out=10,
                cost_usd=spent,
                latency_ms=1,
            )
        )
    review, settings = load_configs("config/review.yaml", "config/settings.yaml")
    settings.gates.cost_budget_max = budget
    settings.gates.profile = profile
    run_dir = fixture.run_root / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(fixture.run_root),
        workflow_id=fixture.workflow_id,
        db_path=str(fixture.db_path),
        output_dir=str(run_dir),
        review=review,
        settings=settings,
        artifacts={"run_summary": str(run_dir / "run_summary.json")},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["strict", "warning"])
async def test_budget_exceeded_stops_before_paid_node(
    tmp_workflow_db: WorkflowDbFixture, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    state = await _state(tmp_workflow_db, spent=31.0, budget=30.0, profile=profile)

    async def _must_not_run(self: SearchNode, ctx: object) -> object:
        raise AssertionError("paid node ran despite exhausted budget")

    monkeypatch.setattr(SearchNode, "run", _must_not_run)
    result = await run_graph_with_budget(SearchNode(), state)

    assert result.status == WorkflowRunStatus.FAILED
    assert result.gate == "cost_budget"
    assert result.phase == "phase_2_search"
    assert result.to_output_dict()["status"] == "failed"

    async with get_db(str(tmp_workflow_db.db_path)) as db:
        repo = WorkflowRepository(db)
        gate = await repo.get_latest_gate_result(tmp_workflow_db.workflow_id, "phase_2_search", "cost_budget")
        cursor = await db.execute("SELECT status FROM workflows WHERE workflow_id = ?", (tmp_workflow_db.workflow_id,))
        row = await cursor.fetchone()
    assert gate is not None and gate.status == GateStatus.FAILED
    assert row[0] == "failed"
    summary = json.loads((tmp_workflow_db.run_root / "run" / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["gate"] == "cost_budget"
    assert summary["status"] == "failed"


@pytest.mark.asyncio
async def test_budget_under_limit_lets_node_run(
    tmp_workflow_db: WorkflowDbFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic_graph import End

    from src.models.workflow import WorkflowRunResult

    state = await _state(tmp_workflow_db, spent=1.0, budget=30.0, profile="strict")
    ran: list[bool] = []

    async def _fake_run(self: SearchNode, ctx: object) -> End[WorkflowRunResult]:
        ran.append(True)
        return End(WorkflowRunResult(status=WorkflowRunStatus.COMPLETED, workflow_id=state.workflow_id))

    monkeypatch.setattr(SearchNode, "run", _fake_run)
    result = await run_graph_with_budget(SearchNode(), state)

    assert ran == [True]
    assert result.status == WorkflowRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_boundary_gate_disabled_when_budget_non_positive(tmp_workflow_db: WorkflowDbFixture) -> None:
    state = await _state(tmp_workflow_db, spent=5.0, budget=0.0, profile="strict")
    async with get_db(str(tmp_workflow_db.db_path)) as db:
        runner = GateRunner(WorkflowRepository(db), state.settings)
        assert await runner.run_cost_budget_boundary_gate(state.workflow_id, "phase_3_screening") is None
