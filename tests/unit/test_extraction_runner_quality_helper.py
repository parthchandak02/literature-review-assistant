"""Shared RoB2/ROBINS-I/CASP/MMAT persistence helper in extraction_runner."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.orchestration.runners.extraction_runner import _assess_and_persist_quality


def _assessor(result: object) -> SimpleNamespace:
    return SimpleNamespace(assess=AsyncMock(return_value=result))


def _assessors(**overrides: object) -> dict[str, SimpleNamespace]:
    base = {name: _assessor(None) for name in ("rob2", "robins_i", "casp", "mmat")}
    base.update({k: _assessor(v) for k, v in overrides.items()})
    return base


_RECORD = SimpleNamespace(paper_id="p1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "save_method"),
    [("rob2", "save_rob2_assessment"), ("robins_i", "save_robins_i_assessment")],
)
async def test_rob_tools_persist_and_report_judgment(tool: str, save_method: str) -> None:
    assessment = SimpleNamespace(
        overall_judgment=SimpleNamespace(value="low"),
        fallback_used=True,
        overall_rationale="heuristic",
    )
    repo = AsyncMock()
    outcome = await _assess_and_persist_quality(
        tool, _RECORD, "text", repository=repo, workflow_id="wf", **_assessors(**{tool: assessment})
    )
    assert outcome is not None
    assert outcome.rob_judgment == "low"
    assert outcome.rob_assessment is assessment
    assert outcome.mmat_result is None
    getattr(repo, save_method).assert_awaited_once_with("wf", assessment)
    event = repo.save_fallback_event.await_args.args[0]
    assert event.module == f"quality.{tool}"
    assert event.reason == "heuristic"
    repo.append_decision_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_casp_logs_decision_without_fallback() -> None:
    assessment = SimpleNamespace(overall_summary="x" * 100, fallback_used=False)
    repo = AsyncMock()
    outcome = await _assess_and_persist_quality(
        "casp", _RECORD, "", repository=repo, workflow_id="wf", **_assessors(casp=assessment)
    )
    assert outcome is not None
    assert outcome.rob_judgment == "x" * 80
    assert outcome.rob_assessment is None
    repo.save_casp_assessment.assert_awaited_once_with("wf", "p1", assessment)
    repo.save_fallback_event.assert_not_awaited()
    assert repo.append_decision_log.await_args.args[0].decision_type == "casp_assessment"


@pytest.mark.asyncio
async def test_mmat_returns_result_for_low_quality_check() -> None:
    result = SimpleNamespace(overall_score=2, overall_summary="weak", fallback_used=False)
    repo = AsyncMock()
    outcome = await _assess_and_persist_quality(
        "mmat", _RECORD, "", repository=repo, workflow_id="wf", **_assessors(mmat=result)
    )
    assert outcome is not None
    assert outcome.mmat_result is result
    assert outcome.rob_judgment == "MMAT score 2/5"
    repo.save_mmat_assessment.assert_awaited_once_with("wf", "p1", result)
    assert repo.append_decision_log.await_args.args[0].decision_type == "mmat_assessment"


@pytest.mark.asyncio
async def test_unrouted_tool_returns_none_without_writes() -> None:
    repo = AsyncMock()
    outcome = await _assess_and_persist_quality(
        "not_applicable", _RECORD, "", repository=repo, workflow_id="wf", **_assessors()
    )
    assert outcome is None
    assert repo.mock_calls == []
