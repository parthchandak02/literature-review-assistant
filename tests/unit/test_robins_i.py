from src.models import ExtractionRecord, RobinsIJudgment, StudyDesign
from src.quality.robins_i import RobinsIAssessor


def _record(summary: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="p2",
        study_design=StudyDesign.NON_RANDOMIZED,
        intervention_description="Chatbot support",
        outcomes=[{"name": "engagement", "description": "retention"}],
        results_summary={"summary": summary},
    )


def test_robins_i_defaults_to_moderate_without_major_signals() -> None:
    assessor = RobinsIAssessor()
    assessment = assessor.assess(_record("observational educational intervention with clear outcomes"))
    assert assessment.overall_judgment == RobinsIJudgment.MODERATE


def test_robins_i_serious_when_confounding_or_missing_signals_present() -> None:
    assessor = RobinsIAssessor()
    assessment = assessor.assess(_record("confounding present with missing data and selective reporting"))
    assert assessment.domain_1_confounding == RobinsIJudgment.SERIOUS
    assert assessment.domain_5_missing_data == RobinsIJudgment.SERIOUS
    assert assessment.overall_judgment == RobinsIJudgment.SERIOUS
