"""Feasibility checks for quantitative synthesis.

Feasibility requires:
1. At least `min_studies` extraction records.
2. At least two records sharing a named, non-generic outcome name.
3. Both records must have effect_size AND standard error as numeric values.
4. No severe clinical heterogeneity signal (all-different study designs with
   small N implies high methodological heterogeneity -- warns but does not block).

Warnings (non-blocking) are surfaced via `measurement_warning` and
`heterogeneity_warning` for reviewer attention.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from src.models import ExtractionRecord

_GENERIC_OUTCOME_NAMES = frozenset(
    {
        "",
        "primary_outcome",
        "secondary_outcome",
        "not_reported",
        "not reported",
    }
)


def _is_numeric(val: str) -> bool:
    """Return True when val represents a finite float (handles trailing '%')."""
    try:
        float(str(val).strip().rstrip("%"))
        return True
    except (ValueError, TypeError):
        return False


def _detect_heterogeneity_warning(records: Sequence[ExtractionRecord]) -> str:
    """Return a human-readable heterogeneity warning string or empty string.

    Signals to surface:
    - All studies have different study designs (maximum design heterogeneity)
    - Total participant count is < 100 across all studies (very low power)
    - Any study has an unknown/null participant count (imprecision)

    These are warnings, not hard gates -- the feasibility function still
    returns feasible=True when effect sizes are poolable. The warning is
    injected into WritingGroundingData so the Discussion section can note
    the limitation.
    """
    warnings: list[str] = []

    designs = [r.study_design.value if r.study_design else "unknown" for r in records]
    design_counts = Counter(designs)
    n_unique_designs = len(design_counts)
    if n_unique_designs == len(records) and len(records) > 2:
        warnings.append(
            f"All {len(records)} included studies have different study designs "
            f"({', '.join(sorted(design_counts))}); high methodological heterogeneity expected."
        )

    total_n = sum(r.participant_count or 0 for r in records)
    missing_n = sum(1 for r in records if r.participant_count is None)
    if total_n > 0 and total_n < 100:
        warnings.append(
            f"Total participant count is very low (N={total_n} across {len(records)} studies); "
            "pooled estimates will have wide confidence intervals."
        )
    if missing_n > 0:
        warnings.append(
            f"{missing_n} of {len(records)} studies did not report participant count; "
            "true aggregate N is unknown."
        )

    return " ".join(warnings)


class SynthesisFeasibility(BaseModel):
    feasible: bool
    rationale: str
    groupings: list[str]
    measurement_warning: str = ""
    heterogeneity_warning: str = ""


def assess_meta_analysis_feasibility(
    records: Sequence[ExtractionRecord],
    min_studies: int = 2,
) -> SynthesisFeasibility:
    """Assess whether quantitative meta-analysis is feasible.

    Returns feasible=True only when at least two studies share a named outcome
    AND both have effect_size and se fields that are float-parseable numbers.
    Non-numeric strings such as '71%', 'High satisfaction', or qualitative
    descriptors do not satisfy the check, ensuring consistency with the
    float() parsing performed in _try_meta_analysis.
    """
    heterogeneity_warning = _detect_heterogeneity_warning(records)

    if len(records) < min_studies:
        return SynthesisFeasibility(
            feasible=False,
            rationale=f"Insufficient studies for pooling: n={len(records)}, minimum={min_studies}.",
            groupings=[],
            heterogeneity_warning=heterogeneity_warning,
        )

    outcome_data: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for record in records:
        for outcome in record.outcomes:
            name = outcome.name.strip().lower().replace(" ", "_")
            if not name or name in _GENERIC_OUTCOME_NAMES:
                continue
            has_es = _is_numeric(outcome.effect_size or "")
            has_se = _is_numeric(outcome.se or "")
            outcome_data[name].append((has_es, has_se))

    if not outcome_data:
        return SynthesisFeasibility(
            feasible=False,
            rationale="No structured outcomes available for grouping.",
            groupings=[],
            heterogeneity_warning=heterogeneity_warning,
        )

    poolable_groups: list[str] = []
    name_only_groups: list[str] = []

    for name, study_data in outcome_data.items():
        if len(study_data) < min_studies:
            continue
        studies_with_full_data = sum(1 for es, se in study_data if es and se)
        if studies_with_full_data >= min_studies:
            poolable_groups.append(name)
        else:
            name_only_groups.append(name)

    measurement_warning = ""
    if name_only_groups:
        measurement_warning = (
            f"Outcome groups present by name but lacking numeric effect size + SE "
            f"(manual check required): {', '.join(sorted(name_only_groups)[:5])}."
        )

    if poolable_groups:
        return SynthesisFeasibility(
            feasible=True,
            rationale=(
                f"Detected {len(poolable_groups)} poolable outcome group(s) with effect size "
                f"and SE from >= {min_studies} studies: {', '.join(poolable_groups[:5])}."
            ),
            groupings=sorted(poolable_groups),
            measurement_warning=measurement_warning,
            heterogeneity_warning=heterogeneity_warning,
        )

    all_named = sorted(outcome_data.keys())
    return SynthesisFeasibility(
        feasible=False,
        rationale=(
            f"Outcome names present ({len(all_named)} unique) but no group has "
            f">= {min_studies} studies with effect size and SE for pooling."
        ),
        groupings=[],
        measurement_warning=measurement_warning,
        heterogeneity_warning=heterogeneity_warning,
    )
