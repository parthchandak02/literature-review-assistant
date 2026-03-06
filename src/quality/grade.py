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
            "Inconsistency/indirectness: not auto-computed from pipeline data -- manual review required."
        )
        return assessment.model_copy(
            update={
                "justification": justification,
                "inconsistency_assessed": False,
                "indirectness_assessed": False,
            }
        )


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

# Canonical outcome theme clustering rules.
# Each theme maps to a list of keyword fragments; if an outcome name (lowercased)
# contains any of the fragments it is assigned to that theme.  Earlier themes take
# priority (first match wins), so order matters: put most specific first.
#
# These themes are intentionally GENERIC -- they apply to any health intervention
# systematic review (technology assessments, clinical treatments, public health
# programs, etc.).  Do NOT add domain-specific or topic-specific keyword fragments
# here.  Intervention-specific terms belong in the review.yaml config, not in this
# shared clustering logic.
_OUTCOME_THEME_RULES: list[tuple[str, list[str]]] = [
    (
        "Accuracy and error rates",
        [
            "accuracy",
            "error rate",
            "error",
            "near-miss",
            "near miss",
            "adverse drug",
            "wrong",
            "mistake",
            "failure rate",
            "false positive",
            "false negative",
            "detection rate",
            "sensitivity",
            "specificity",
        ],
    ),
    (
        "Operational efficiency and time",
        [
            "efficiency",
            "throughput",
            "turnaround",
            "waiting time",
            "wait time",
            "processing time",
            "treatment time",
            "response time",
            "workload",
            "productivity",
            "output",
            "volume",
            "utilization",
            "capacity",
        ],
    ),
    (
        "Patient safety and clinical outcomes",
        [
            "safety",
            "harm",
            "adverse event",
            "incident",
            "near miss",
            "near-miss",
            "patient outcome",
            "clinical outcome",
            "mortality",
            "morbidity",
            "complication",
            "readmission",
            "infection rate",
            "survival",
        ],
    ),
    (
        "Cost and resource utilization",
        [
            "cost",
            "roi",
            "return on investment",
            "savings",
            "expenditure",
            "budget",
            "resource",
            "staff",
            "labour",
            "labor",
            "workforce",
            "fte",
            "economic",
        ],
    ),
    (
        "Implementation barriers and facilitators",
        [
            "barrier",
            "facilitator",
            "adoption",
            "implementation",
            "workflow",
            "satisfaction",
            "perception",
            "attitude",
            "acceptance",
            "training",
            "challenge",
        ],
    ),
]


def cluster_grade_assessments_by_theme(
    assessments: list[GRADEOutcomeAssessment],
) -> list[GRADEOutcomeAssessment]:
    """Cluster per-study GRADE assessments into canonical outcome themes.

    Each primary study may have a unique outcome name string, making it impossible
    to see cross-study patterns in the Summary of Findings table. This function
    groups semantically similar outcomes into 5 canonical themes and returns one
    aggregate GRADEOutcomeAssessment per theme (taking the worst-case downgrade
    across all studies in that theme and the total study count).

    Studies with non-placeholder, non-clusterable outcome names are returned as-is
    (deduplicated by exact name) to preserve any domain-specific outcomes.
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)

    if not assessments:
        return []

    # Map each assessment to a theme (or "other" bucket)
    theme_buckets: dict[str, list[GRADEOutcomeAssessment]] = {theme: [] for theme, _ in _OUTCOME_THEME_RULES}
    other_bucket: list[GRADEOutcomeAssessment] = []

    for a in assessments:
        raw_name = (getattr(a, "outcome_name", None) or "").lower().strip()
        if raw_name.replace("_", " ").replace("-", " ").strip() in {
            n.replace("_", " ") for n in _PLACEHOLDER_OUTCOME_NAMES
        }:
            # Skip true placeholders entirely -- they add no information
            continue
        matched = False
        for theme_name, keywords in _OUTCOME_THEME_RULES:
            if any(kw in raw_name for kw in keywords):
                theme_buckets[theme_name].append(a)
                matched = True
                break
        if not matched:
            other_bucket.append(a)

    # Build aggregate assessments per theme
    result: list[GRADEOutcomeAssessment] = []
    for theme_name, members in theme_buckets.items():
        if not members:
            continue
        if len(members) < 2:
            # Single study -- include as-is with its own outcome name
            result.append(members[0])
            continue
        # Take worst-case downgrade across all members; best-case upgrade
        worst_rob = max(m.risk_of_bias_downgrade for m in members)
        worst_inconsistency = max(m.inconsistency_downgrade for m in members)
        worst_indirectness = max(m.indirectness_downgrade for m in members)
        worst_imprecision = max(m.imprecision_downgrade for m in members)
        worst_pub_bias = max(m.publication_bias_downgrade for m in members)
        best_large_effect = max(m.large_effect_upgrade for m in members)
        best_dose_resp = max(m.dose_response_upgrade for m in members)
        best_residual = max(m.residual_confounding_upgrade for m in members)
        # Take study design from the most common design in this theme
        from collections import Counter as _Counter

        design_counts = _Counter(m.study_designs for m in members)
        primary_design = design_counts.most_common(1)[0][0]
        # Re-compute certainty using aggregate
        assessor = GradeAssessor()
        try:
            from src.models import StudyDesign as _StudyDesign

            design_enum = _StudyDesign(primary_design)
        except Exception:
            design_enum = None  # type: ignore[assignment]
        if design_enum is not None:
            agg = assessor.assess_outcome(
                outcome_name=theme_name,
                number_of_studies=len(members),
                study_design=design_enum,
                risk_of_bias_downgrade=worst_rob,
                inconsistency_downgrade=worst_inconsistency,
                indirectness_downgrade=worst_indirectness,
                imprecision_downgrade=worst_imprecision,
                publication_bias_downgrade=worst_pub_bias,
                large_effect_upgrade=best_large_effect,
                dose_response_upgrade=best_dose_resp,
                residual_confounding_upgrade=best_residual,
            )
            _log.info(
                "GRADE: clustered %d studies under theme '%s' -> certainty=%s",
                len(members),
                theme_name,
                agg.final_certainty.value,
            )
            result.append(agg)
        else:
            # Fallback: append members as-is
            result.extend(members)

    # Add non-clustered outcomes (unique domain-specific outcomes)
    seen_names: set[str] = set()
    for a in other_bucket:
        name_key = (getattr(a, "outcome_name", "") or "").lower().strip()
        if name_key not in seen_names:
            seen_names.add(name_key)
            result.append(a)

    return result


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
    for a in assessments:
        raw_name = getattr(a, "outcome_name", None) or ""
        name_norm = raw_name.lower().strip().replace(" ", "_")
        # Skip placeholder-named outcomes entirely (consistent with Evidence Profile behavior).
        # These carry no useful information and produce "Outcome from included studies (N)" noise.
        if name_norm in _PLACEHOLDER_OUTCOME_NAMES or not raw_name.strip():
            continue
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
                inconsistency=(
                    "not assessed*"
                    if not getattr(a, "inconsistency_assessed", True)
                    else _DOWNGRADE_LABEL.get(a.inconsistency_downgrade, "not serious")
                ),
                indirectness=(
                    "not assessed*"
                    if not getattr(a, "indirectness_assessed", True)
                    else _DOWNGRADE_LABEL.get(a.indirectness_downgrade, "not serious")
                ),
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
        # Truncate effect summary at a word boundary to avoid mid-sentence cuts.
        effect_raw = (r.effect_summary or "").replace("|", "/").replace("\n", " ").strip()
        _effect_limit = 160
        if len(effect_raw) > _effect_limit:
            # Find last space before limit to avoid cutting mid-word
            cutoff = effect_raw.rfind(" ", 0, _effect_limit)
            effect = effect_raw[: cutoff if cutoff > _effect_limit // 2 else _effect_limit] + "..."
        else:
            effect = effect_raw
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
        "residual confounding, and downgrades for suspected publication bias. "
        "* = not auto-computed from pipeline data; manual reviewer assessment required._\n"
    )
    return header + "\n".join(rows) + note
