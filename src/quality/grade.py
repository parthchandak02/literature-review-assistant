"""GRADE outcome assessor.

The `GradeAssessor.assess_outcome()` method accepts explicit downgrade/upgrade
factors. Callers should use `GradeAssessor.assess_from_rob()` to auto-compute
those factors from actual pipeline outputs (RoB 2 / ROBINS-I assessments and
extraction records), ensuring GRADE is data-driven and not hard-coded to zero.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.models import GRADECertainty, GRADEOutcomeAssessment, StudyDesign
from src.models.quality import GradeSoFRow, GradeSoFTable


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
        starting = GRADECertainty.HIGH if study_design == StudyDesign.RCT else GRADECertainty.LOW
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
        total_n = sum(getattr(r, "participant_count", None) or 0 for r in extraction_records)
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


_DOWNGRADE_LABEL: dict[int, str] = {
    0: "not serious",
    1: "serious",
    2: "very serious",
}

_UPGRADE_LABEL: dict[int, str] = {
    0: "none",
    1: "large effect",
    2: "very large effect",
}


_PLACEHOLDER_OUTCOME_NAMES = frozenset(
    {
        "",
        "primary_outcome",
        "secondary_outcome",
        "not reported",
        "not_reported",
    }
)


def _outcome_display_name(raw_name: str, placeholder_index: int) -> str:
    """Return display name for SoF table; use fallback for placeholder names."""
    if not raw_name or not raw_name.strip():
        return f"Outcome from included studies ({placeholder_index})"
    name_norm = raw_name.lower().strip().replace(" ", "_")
    if name_norm in _PLACEHOLDER_OUTCOME_NAMES:
        return f"Outcome from included studies ({placeholder_index})"
    return raw_name.replace("_", " ").strip()


def build_sof_table(
    assessments: list[GRADEOutcomeAssessment],
    topic: str = "Systematic Review",
) -> GradeSoFTable:
    """Build a GRADE Summary of Findings table from a list of outcome assessments.

    Each GRADEOutcomeAssessment becomes one row with human-readable downgrade
    and upgrade labels so the table can be rendered as LaTeX or JSON.
    Placeholder outcome names (e.g. 'not reported', 'primary_outcome') are
    replaced with 'Outcome from included studies (N)' fallback labels.
    """
    rows: list[GradeSoFRow] = []
    placeholder_counter = 0
    for a in assessments:
        raw_name = getattr(a, "outcome_name", None) or ""
        name_norm = raw_name.lower().strip().replace(" ", "_")
        if name_norm in _PLACEHOLDER_OUTCOME_NAMES or not raw_name.strip():
            placeholder_counter += 1
            display_name = _outcome_display_name(raw_name, placeholder_counter)
        else:
            display_name = raw_name.replace("_", " ").strip()
        other: list[str] = []
        if a.large_effect_upgrade:
            other.append(_UPGRADE_LABEL.get(a.large_effect_upgrade, "upgrade"))
        if a.dose_response_upgrade:
            other.append("dose-response gradient")
        if a.residual_confounding_upgrade:
            other.append("residual confounding (protective)")
        if a.publication_bias_downgrade:
            other.append(f"publication bias ({_DOWNGRADE_LABEL.get(a.publication_bias_downgrade, '-')})")

        rows.append(
            GradeSoFRow(
                outcome_name=display_name,
                n_studies=a.number_of_studies,
                study_design=a.study_designs,
                risk_of_bias=_DOWNGRADE_LABEL.get(a.risk_of_bias_downgrade, "not serious"),
                inconsistency=_DOWNGRADE_LABEL.get(a.inconsistency_downgrade, "not serious"),
                indirectness=_DOWNGRADE_LABEL.get(a.indirectness_downgrade, "not serious"),
                imprecision=_DOWNGRADE_LABEL.get(a.imprecision_downgrade, "not serious"),
                other_considerations="; ".join(other) if other else "none",
                certainty=a.final_certainty,
                effect_summary=a.justification[:120] if a.justification else "",
            )
        )
    return GradeSoFTable(topic=topic, rows=rows)


def sof_table_to_markdown(table: GradeSoFTable) -> str:
    """Render a GradeSoFTable as a GFM markdown section for inclusion in the manuscript.

    Columns: Outcome, N Studies, Study Design, RoB, Inconsistency,
    Indirectness, Imprecision, Other, Certainty, Effect Summary.

    Returns an empty string when the table has no rows.
    """
    if not table.rows:
        return ""

    header = (
        "## GRADE Summary of Findings\n\n"
        f"_Topic: {table.topic}_\n\n"
        "| Outcome | N Studies | Study Design | Risk of Bias | Inconsistency | "
        "Indirectness | Imprecision | Other | Certainty | Effect / Reason |\n"
        "|---------|-----------|-------------|-------------|--------------|"
        "------------|------------|-------|-----------|----------------|\n"
    )
    rows: list[str] = []
    for r in table.rows:
        certainty_str = (
            r.certainty.value.upper().replace("_", " ") if hasattr(r.certainty, "value") else str(r.certainty).upper()
        )
        effect = (r.effect_summary or "").replace("|", "/").replace("\n", " ")[:120]
        rows.append(
            f"| {r.outcome_name} | {r.n_studies} | {r.study_design} "
            f"| {r.risk_of_bias} | {r.inconsistency} | {r.indirectness} "
            f"| {r.imprecision} | {r.other_considerations} | **{certainty_str}** "
            f"| {effect} |"
        )

    note = (
        "\n\n_GRADE certainty levels: HIGH, MODERATE, LOW, VERY LOW. "
        "RoB/Inconsistency/Indirectness/Imprecision rated as: "
        "not serious, serious, very serious. "
        "Other considerations include upgrades for large effect, dose-response, or "
        "residual confounding, and downgrades for suspected publication bias._\n"
    )
    return header + "\n".join(rows) + note
