"""GRADE outcome assessor.

The `GradeAssessor.assess_outcome()` method accepts explicit downgrade/upgrade
factors. Callers should use `GradeAssessor.assess_from_rob()` to auto-compute
those factors from actual pipeline outputs (RoB 2 / ROBINS-I assessments and
extraction records), ensuring GRADE is data-driven and not hard-coded to zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from src.models import GRADECertainty, GRADEOutcomeAssessment, StudyDesign


def _certainty_to_score(certainty: GRADECertainty) -> int:
    mapping = {
        GRADECertainty.HIGH: 3,
        GRADECertainty.MODERATE: 2,
        GRADECertainty.LOW: 1,
        GRADECertainty.VERY_LOW: 0,
    }
    return mapping[certainty]


def _score_to_certainty(score: int) -> GRADECertainty:
    bounded = max(0, min(3, score))
    mapping = {
        3: GRADECertainty.HIGH,
        2: GRADECertainty.MODERATE,
        1: GRADECertainty.LOW,
        0: GRADECertainty.VERY_LOW,
    }
    return mapping[bounded]


class GradeAssessor:
    """Build a GRADE assessment row from quality factor scores."""

    def assess_outcome(
        self,
        outcome_name: str,
        number_of_studies: int,
        study_design: StudyDesign,
        risk_of_bias_downgrade: int = 0,
        inconsistency_downgrade: int = 0,
        indirectness_downgrade: int = 0,
        imprecision_downgrade: int = 0,
        publication_bias_downgrade: int = 0,
        large_effect_upgrade: int = 0,
        dose_response_upgrade: int = 0,
        residual_confounding_upgrade: int = 0,
    ) -> GRADEOutcomeAssessment:
        starting = (
            GRADECertainty.HIGH
            if study_design == StudyDesign.RCT
            else GRADECertainty.LOW
        )
        score = _certainty_to_score(starting)
        score -= risk_of_bias_downgrade
        score -= inconsistency_downgrade
        score -= indirectness_downgrade
        score -= imprecision_downgrade
        score -= publication_bias_downgrade
        score += large_effect_upgrade
        score += dose_response_upgrade
        score += residual_confounding_upgrade
        final_certainty = _score_to_certainty(score)

        return GRADEOutcomeAssessment(
            outcome_name=outcome_name,
            number_of_studies=number_of_studies,
            study_designs=study_design.value,
            starting_certainty=starting,
            risk_of_bias_downgrade=risk_of_bias_downgrade,
            inconsistency_downgrade=inconsistency_downgrade,
            indirectness_downgrade=indirectness_downgrade,
            imprecision_downgrade=imprecision_downgrade,
            publication_bias_downgrade=publication_bias_downgrade,
            large_effect_upgrade=large_effect_upgrade,
            dose_response_upgrade=dose_response_upgrade,
            residual_confounding_upgrade=residual_confounding_upgrade,
            final_certainty=final_certainty,
            justification="Computed from configured downgrade/upgrade factors.",
        )

    def assess_from_rob(
        self,
        outcome_name: str,
        study_design: StudyDesign,
        rob_assessments: Sequence[object],
        extraction_records: Sequence[object],
    ) -> GRADEOutcomeAssessment:
        """Derive GRADE downgrade factors from actual pipeline data.

        Risk-of-bias downgrade is computed from the worst overall judgment
        across all included RoB/ROBINS-I assessments:
          - HIGH / CRITICAL -> downgrade 2
          - SOME_CONCERNS / SERIOUS -> downgrade 1
          - LOW / MODERATE -> downgrade 0

        Imprecision downgrade is applied when the total participant count
        across studies reporting N is below 300 (a conservative threshold
        for small aggregate sample size).

        Inconsistency, indirectness, and publication bias are not
        auto-computed from current data (would require effect-size variance
        and funnel-plot asymmetry); they default to 0 and should be reviewed.
        """
        from src.models.enums import RiskOfBiasJudgment, RobinsIJudgment

        # -- Risk of bias downgrade --
        rob_downgrade = 0
        for rob in rob_assessments:
            overall = getattr(rob, "overall_judgment", None)
            if overall is None:
                continue
            if isinstance(overall, RiskOfBiasJudgment):
                if overall == RiskOfBiasJudgment.HIGH:
                    rob_downgrade = max(rob_downgrade, 2)
                elif overall == RiskOfBiasJudgment.SOME_CONCERNS:
                    rob_downgrade = max(rob_downgrade, 1)
            elif isinstance(overall, RobinsIJudgment):
                if overall in {RobinsIJudgment.CRITICAL}:
                    rob_downgrade = max(rob_downgrade, 2)
                elif overall in {RobinsIJudgment.SERIOUS, RobinsIJudgment.MODERATE}:
                    rob_downgrade = max(rob_downgrade, 1)
        rob_downgrade = min(rob_downgrade, 2)

        # -- Imprecision downgrade --
        total_n = sum(
            getattr(r, "participant_count", None) or 0
            for r in extraction_records
        )
        imprecision_downgrade = 1 if total_n > 0 and total_n < 300 else 0

        n_studies = len(extraction_records)
        assessment = self.assess_outcome(
            outcome_name=outcome_name,
            number_of_studies=n_studies,
            study_design=study_design,
            risk_of_bias_downgrade=rob_downgrade,
            inconsistency_downgrade=0,
            indirectness_downgrade=0,
            imprecision_downgrade=imprecision_downgrade,
            publication_bias_downgrade=0,
        )
        justification = (
            f"RoB downgrade={rob_downgrade} (worst-case across {len(rob_assessments)} assessments). "
            f"Imprecision downgrade={imprecision_downgrade} (total N={total_n}). "
            "Inconsistency/indirectness/publication-bias: not auto-computed; review manually."
        )
        return assessment.model_copy(update={"justification": justification})
