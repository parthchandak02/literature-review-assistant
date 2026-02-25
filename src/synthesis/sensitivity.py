"""Sensitivity analysis: leave-one-out and subgroup pooled effects.

Only called when meta-analysis is feasible (i.e., at least 2 studies have
matching outcome names with effect_size and se populated). Uses the same
DerSimonian-Laird random-effects model as meta_analysis.pool_effects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from src.models import ExtractionRecord
from src.synthesis.meta_analysis import pool_effects

_log = logging.getLogger(__name__)


@dataclass
class LeaveOneOutResult:
    """Pooled estimate after dropping one study."""

    excluded_paper_id: str
    excluded_title: str
    pooled_effect: float
    ci_lower: float
    ci_upper: float
    n_studies: int
    i_squared: float


@dataclass
class SubgroupResult:
    """Pooled estimate for one subgroup."""

    subgroup_label: str
    pooled_effect: float
    ci_lower: float
    ci_upper: float
    n_studies: int
    i_squared: float


@dataclass
class SensitivityAnalysisResult:
    """Container for all sensitivity analysis outputs."""

    outcome_name: str
    overall_pooled_effect: float
    overall_ci_lower: float
    overall_ci_upper: float
    n_studies: int
    leave_one_out: list[LeaveOneOutResult] = field(default_factory=list)
    subgroup_results: dict[str, list[SubgroupResult]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_grounding_text(self) -> str:
        """Format for injection into the manuscript grounding block."""
        lines = [
            f"Sensitivity Analysis -- Outcome: {self.outcome_name}",
            f"Overall: effect={self.overall_pooled_effect:.3f} "
            f"95% CI [{self.overall_ci_lower:.3f}, {self.overall_ci_upper:.3f}], "
            f"N={self.n_studies} studies",
        ]
        if self.leave_one_out:
            lines.append("Leave-one-out results (effect [95% CI] after excluding each study):")
            for loo in self.leave_one_out:
                lines.append(
                    f"  - Excluding {loo.excluded_title[:60]}: "
                    f"{loo.pooled_effect:.3f} [{loo.ci_lower:.3f}, {loo.ci_upper:.3f}]"
                )
        for col, groups in self.subgroup_results.items():
            lines.append(f"Subgroup analysis by {col}:")
            for sg in groups:
                lines.append(
                    f"  - {sg.subgroup_label} (N={sg.n_studies}): "
                    f"{sg.pooled_effect:.3f} [{sg.ci_lower:.3f}, {sg.ci_upper:.3f}]"
                )
        if self.notes:
            lines.extend(self.notes)
        return "\n".join(lines)


def _collect_outcome_data(
    records: list[ExtractionRecord],
    outcome_name: str,
) -> tuple[list[str], list[str], list[float], list[float]]:
    """Extract paper_ids, titles (placeholders), effects, and variances for an outcome."""
    paper_ids: list[str] = []
    titles: list[str] = []
    effects: list[float] = []
    variances: list[float] = []

    for rec in records:
        for outcome in rec.outcomes:
            if outcome.get("name", "") != outcome_name:
                continue
            try:
                es_raw = outcome.get("effect_size")
                se_raw = outcome.get("se")
                if es_raw is None or se_raw is None:
                    continue
                es = float(es_raw)
                se = float(se_raw)
                if se <= 0.0:
                    continue
                paper_ids.append(rec.paper_id)
                titles.append(outcome.get("title", rec.paper_id))
                effects.append(es)
                variances.append(se ** 2)
            except (TypeError, ValueError):
                continue

    return paper_ids, titles, effects, variances


def leave_one_out(
    records: list[ExtractionRecord],
    outcome_name: str,
    effect_measure: str = "smd",
    heterogeneity_threshold: float = 40.0,
) -> list[LeaveOneOutResult]:
    """Run leave-one-out sensitivity analysis for a single outcome.

    Drops each study in turn and re-pools the remaining studies using the
    DerSimonian-Laird random-effects model. Requires at least 3 studies
    (otherwise dropping one leaves only 1, which cannot be pooled).
    """
    paper_ids, titles, effects, variances = _collect_outcome_data(records, outcome_name)
    if len(paper_ids) < 3:
        _log.info(
            "leave_one_out: fewer than 3 studies for outcome '%s'; skipping", outcome_name
        )
        return []

    results: list[LeaveOneOutResult] = []
    for i, (pid, title) in enumerate(zip(paper_ids, titles)):
        remaining_effects = effects[:i] + effects[i + 1 :]
        remaining_variances = variances[:i] + variances[i + 1 :]
        try:
            pooled = pool_effects(
                outcome_name=outcome_name,
                effect_measure=effect_measure,
                effects=remaining_effects,
                variances=remaining_variances,
                heterogeneity_threshold=heterogeneity_threshold,
            )
            results.append(
                LeaveOneOutResult(
                    excluded_paper_id=pid,
                    excluded_title=title,
                    pooled_effect=pooled.pooled_effect,
                    ci_lower=pooled.ci_lower,
                    ci_upper=pooled.ci_upper,
                    n_studies=len(remaining_effects),
                    i_squared=pooled.i_squared,
                )
            )
        except Exception as exc:
            _log.warning("leave_one_out failed for exclusion of %s: %s", pid, exc)

    return results


def subgroup_analysis(
    records: list[ExtractionRecord],
    outcome_name: str,
    subgroup_cols: list[str],
    paper_metadata: dict[str, dict[str, Any]] | None = None,
    effect_measure: str = "smd",
    heterogeneity_threshold: float = 40.0,
) -> dict[str, list[SubgroupResult]]:
    """Run subgroup analysis by one or more categorical columns.

    Args:
        records: Extraction records for included studies.
        outcome_name: The outcome to pool (must match outcome[*].name).
        subgroup_cols: List of metadata keys to stratify by (e.g. ["study_design", "country"]).
        paper_metadata: Optional dict mapping paper_id -> {col: value} for grouping.
            If None, falls back to ExtractionRecord attributes.
        effect_measure: Effect measure string passed to pool_effects.
        heterogeneity_threshold: I^2 threshold for random vs fixed effects selection.

    Returns:
        Dict mapping each subgroup_col to a list of SubgroupResult objects.
    """
    paper_ids, _, effects, variances = _collect_outcome_data(records, outcome_name)
    if len(paper_ids) < 2:
        return {}

    # Build a lookup for attribute values
    meta: dict[str, dict[str, Any]] = paper_metadata or {}
    # Fall back to ExtractionRecord fields for known columns
    for rec in records:
        if rec.paper_id not in meta:
            meta[rec.paper_id] = {}
        if "study_design" not in meta[rec.paper_id]:
            meta[rec.paper_id]["study_design"] = rec.study_design.value if rec.study_design else "other"
        if "setting" not in meta[rec.paper_id]:
            meta[rec.paper_id]["setting"] = rec.setting or "NR"

    all_subgroup_results: dict[str, list[SubgroupResult]] = {}

    for col in subgroup_cols:
        # Group paper indices by their value for this column
        groups: dict[str, list[int]] = {}
        for idx, pid in enumerate(paper_ids):
            val = str(meta.get(pid, {}).get(col, "NR"))
            groups.setdefault(val, []).append(idx)

        col_results: list[SubgroupResult] = []
        for label, indices in sorted(groups.items()):
            if len(indices) < 2:
                continue
            g_effects = [effects[i] for i in indices]
            g_variances = [variances[i] for i in indices]
            try:
                pooled = pool_effects(
                    outcome_name=f"{outcome_name} ({label})",
                    effect_measure=effect_measure,
                    effects=g_effects,
                    variances=g_variances,
                    heterogeneity_threshold=heterogeneity_threshold,
                )
                col_results.append(
                    SubgroupResult(
                        subgroup_label=label,
                        pooled_effect=pooled.pooled_effect,
                        ci_lower=pooled.ci_lower,
                        ci_upper=pooled.ci_upper,
                        n_studies=len(indices),
                        i_squared=pooled.i_squared,
                    )
                )
            except Exception as exc:
                _log.warning("subgroup_analysis failed for %s=%s: %s", col, label, exc)

        if col_results:
            all_subgroup_results[col] = col_results

    return all_subgroup_results


def run_sensitivity_analysis(
    records: list[ExtractionRecord],
    outcome_name: str,
    effect_measure: str = "smd",
    subgroup_cols: list[str] | None = None,
    paper_metadata: dict[str, dict[str, Any]] | None = None,
    heterogeneity_threshold: float = 40.0,
) -> SensitivityAnalysisResult | None:
    """Orchestrate leave-one-out and subgroup analyses for one outcome.

    Returns None if fewer than 2 studies have data for the outcome.
    """
    paper_ids, _, effects, variances = _collect_outcome_data(records, outcome_name)
    if len(paper_ids) < 2:
        return None

    try:
        overall = pool_effects(
            outcome_name=outcome_name,
            effect_measure=effect_measure,
            effects=effects,
            variances=variances,
            heterogeneity_threshold=heterogeneity_threshold,
        )
    except Exception as exc:
        _log.error("run_sensitivity_analysis: overall pooling failed: %s", exc)
        return None

    loo_results = leave_one_out(
        records=records,
        outcome_name=outcome_name,
        effect_measure=effect_measure,
        heterogeneity_threshold=heterogeneity_threshold,
    )

    subgroup_res = subgroup_analysis(
        records=records,
        outcome_name=outcome_name,
        subgroup_cols=subgroup_cols or ["study_design"],
        paper_metadata=paper_metadata,
        effect_measure=effect_measure,
        heterogeneity_threshold=heterogeneity_threshold,
    )

    return SensitivityAnalysisResult(
        outcome_name=outcome_name,
        overall_pooled_effect=overall.pooled_effect,
        overall_ci_lower=overall.ci_lower,
        overall_ci_upper=overall.ci_upper,
        n_studies=len(paper_ids),
        leave_one_out=loo_results,
        subgroup_results=subgroup_res,
    )
