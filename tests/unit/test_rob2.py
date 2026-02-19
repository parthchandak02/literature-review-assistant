import pytest

from src.models import ExtractionRecord, RiskOfBiasJudgment, StudyDesign
from src.quality.rob2 import Rob2Assessor


def _record(summary: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="p1",
        study_design=StudyDesign.RCT,
        intervention_description="AI tutor intervention",
        outcomes=[{"name": "score", "description": "exam performance"}],
        results_summary={"summary": summary},
    )


@pytest.mark.asyncio
async def test_rob2_all_low_when_positive_signals_present() -> None:
    assessor = Rob2Assessor()
    assessment = await assessor.assess(_record("random protocol validated outcome reporting complete"))
    assert assessment.overall_judgment == RiskOfBiasJudgment.LOW


@pytest.mark.asyncio
async def test_rob2_high_when_missing_data_signal_present() -> None:
    assessor = Rob2Assessor()
    assessment = await assessor.assess(_record("random protocol validated missing data concerns"))
    assert assessment.domain_3_missing_data == RiskOfBiasJudgment.HIGH
    assert assessment.overall_judgment == RiskOfBiasJudgment.HIGH


@pytest.mark.asyncio
async def test_rob2_some_concerns_when_no_high_and_not_all_low() -> None:
    assessor = Rob2Assessor()
    assessment = await assessor.assess(_record("randomized trial"))
    assert assessment.overall_judgment == RiskOfBiasJudgment.SOME_CONCERNS
