"""RoB 2 assessor for randomized studies."""

from __future__ import annotations

from src.models import ExtractionRecord, RiskOfBiasJudgment, RoB2Assessment


def _max_judgment(values: list[RiskOfBiasJudgment]) -> RiskOfBiasJudgment:
    if RiskOfBiasJudgment.HIGH in values:
        return RiskOfBiasJudgment.HIGH
    if RiskOfBiasJudgment.SOME_CONCERNS in values:
        return RiskOfBiasJudgment.SOME_CONCERNS
    return RiskOfBiasJudgment.LOW


class Rob2Assessor:
    """Assess five RoB2 domains with deterministic rules."""

    def assess(self, record: ExtractionRecord) -> RoB2Assessment:
        summary = (record.results_summary.get("summary") or "").lower()
        d1 = RiskOfBiasJudgment.LOW if "random" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d2 = RiskOfBiasJudgment.LOW if "protocol" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d3 = RiskOfBiasJudgment.HIGH if "missing data" in summary else RiskOfBiasJudgment.LOW
        d4 = RiskOfBiasJudgment.LOW if "validated" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d5 = RiskOfBiasJudgment.SOME_CONCERNS if "selective" in summary else RiskOfBiasJudgment.LOW
        overall = _max_judgment([d1, d2, d3, d4, d5])
        return RoB2Assessment(
            paper_id=record.paper_id,
            domain_1_randomization=d1,
            domain_1_rationale="Heuristic randomization signal check.",
            domain_2_deviations=d2,
            domain_2_rationale="Heuristic protocol deviation signal check.",
            domain_3_missing_data=d3,
            domain_3_rationale="Heuristic missing-data signal check.",
            domain_4_measurement=d4,
            domain_4_rationale="Heuristic measurement validity signal check.",
            domain_5_selection=d5,
            domain_5_rationale="Heuristic reporting-selection signal check.",
            overall_judgment=overall,
            overall_rationale="Overall follows RoB2 aggregation rule.",
        )
