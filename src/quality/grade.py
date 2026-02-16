"""GRADE outcome assessor."""

from __future__ import annotations

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
