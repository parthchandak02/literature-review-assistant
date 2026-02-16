"""ROBINS-I assessor for non-randomized studies."""

from __future__ import annotations

from src.models import ExtractionRecord, RobinsIAssessment, RobinsIJudgment


def _worst(values: list[RobinsIJudgment]) -> RobinsIJudgment:
    ranking = {
        RobinsIJudgment.LOW: 0,
        RobinsIJudgment.MODERATE: 1,
        RobinsIJudgment.SERIOUS: 2,
        RobinsIJudgment.CRITICAL: 3,
        RobinsIJudgment.NO_INFORMATION: 4,
    }
    return max(values, key=lambda item: ranking[item])


class RobinsIAssessor:
    """Assess seven ROBINS-I domains using deterministic heuristics."""

    def assess(self, record: ExtractionRecord) -> RobinsIAssessment:
        summary = (record.results_summary.get("summary") or "").lower()
        d1 = RobinsIJudgment.SERIOUS if "confound" in summary else RobinsIJudgment.MODERATE
        d2 = RobinsIJudgment.MODERATE
        d3 = RobinsIJudgment.MODERATE
        d4 = RobinsIJudgment.MODERATE
        d5 = RobinsIJudgment.SERIOUS if "missing data" in summary else RobinsIJudgment.MODERATE
        d6 = RobinsIJudgment.MODERATE
        d7 = RobinsIJudgment.SERIOUS if "selective" in summary else RobinsIJudgment.MODERATE
        overall = _worst([d1, d2, d3, d4, d5, d6, d7])
        return RobinsIAssessment(
            paper_id=record.paper_id,
            domain_1_confounding=d1,
            domain_1_rationale="Heuristic confounding signal check.",
            domain_2_selection=d2,
            domain_2_rationale="Conservative default for selection bias.",
            domain_3_classification=d3,
            domain_3_rationale="Conservative default for intervention classification.",
            domain_4_deviations=d4,
            domain_4_rationale="Conservative default for deviations.",
            domain_5_missing_data=d5,
            domain_5_rationale="Heuristic missing-data signal check.",
            domain_6_measurement=d6,
            domain_6_rationale="Conservative default for measurement bias.",
            domain_7_reported_result=d7,
            domain_7_rationale="Heuristic selective-reporting signal check.",
            overall_judgment=overall,
            overall_rationale="Overall follows worst-domain ROBINS-I logic.",
        )
