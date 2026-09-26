import pytest

from src.models import ExtractionRecord, RiskOfBiasJudgment, StudyDesign
from src.quality.rob2 import Rob2Assessor, compute_rob2_overall


def _record(summary: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.RCT,
        intervention_description="AI tutor intervention",
        outcomes=[{"name": "score", "description": "exam performance"}],
        results_summary={"summary": summary},
    )


def test_compute_rob2_overall_missing_domain_is_not_assessed() -> None:
    domains = [
        RiskOfBiasJudgment.LOW,
        RiskOfBiasJudgment.LOW,
        RiskOfBiasJudgment.NOT_ASSESSED,
        RiskOfBiasJudgment.LOW,
        RiskOfBiasJudgment.LOW,
    ]
    assert compute_rob2_overall(domains) == RiskOfBiasJudgment.NOT_ASSESSED


@pytest.mark.asyncio
async def test_rob2_heuristic_marks_fallback_used() -> None:
    assessor = Rob2Assessor()
    assessment = await assessor.assess(_record("random protocol validated outcome reporting complete"))
    assert assessment.overall_judgment == RiskOfBiasJudgment.NOT_ASSESSED
    assert assessment.fallback_used is True
    assert assessment.domain_1_randomization == RiskOfBiasJudgment.NOT_ASSESSED
    assert assessment.domain_5_selection == RiskOfBiasJudgment.NOT_ASSESSED


@pytest.mark.asyncio
async def test_rob2_heuristic_never_assigns_low_without_llm() -> None:
    assessor = Rob2Assessor()
    assessment = await assessor.assess(_record("randomized trial missing data concerns"))
    assert assessment.domain_3_missing_data == RiskOfBiasJudgment.NOT_ASSESSED
    assert assessment.overall_judgment == RiskOfBiasJudgment.NOT_ASSESSED
    assert assessment.fallback_used is True
