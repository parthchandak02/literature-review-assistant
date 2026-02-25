"""Feasibility checks for quantitative synthesis.

Feasibility requires:
1. At least `min_studies` extraction records.
2. At least one named outcome (not a generic placeholder).
3. At least 2 records sharing the same outcome name AND both having an effect
   size AND standard error populated -- the data can actually be pooled.

A `measurement_warning` field flags when outcome names match across studies but
the numeric data needed for pooling is absent (would previously have triggered
a false-positive feasibility declaration).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from src.models import ExtractionRecord

_GENERIC_OUTCOME_NAMES = frozenset({
    "", "primary_outcome", "secondary_outcome", "not_reported", "not reported",
})


def _is_numeric(val: str) -> bool:
    """Return True when val represents a finite float (handles trailing '%')."""
    try:
        float(str(val).strip().rstrip("%"))
        return True
    except (ValueError, TypeError):
        return False


class SynthesisFeasibility(BaseModel):
    feasible: bool
    rationale: str
    groupings: list[str]
    measurement_warning: str = ""


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
    if len(records) < min_studies:
        return SynthesisFeasibility(
            feasible=False,
            rationale=f"Insufficient studies for pooling: n={len(records)}, minimum={min_studies}.",
            groupings=[],
        )

    outcome_data: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for record in records:
        for outcome in record.outcomes:
            name = outcome.get("name", "").strip().lower().replace(" ", "_")
            if not name or name in _GENERIC_OUTCOME_NAMES:
                continue
            has_es = _is_numeric(outcome.get("effect_size") or "")
            has_se = _is_numeric(outcome.get("se") or "")
            outcome_data[name].append((has_es, has_se))

    if not outcome_data:
        return SynthesisFeasibility(
            feasible=False,
            rationale="No structured outcomes available for grouping.",
            groupings=[],
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
    )
