"""Meta-analysis pooling wrappers around statsmodels."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats
from statsmodels.stats.meta_analysis import combine_effects

from src.models import MetaAnalysisResult


def _i_squared_percent(cochrans_q: float, df: int) -> float:
    if cochrans_q <= 0.0:
        return 0.0
    value = ((cochrans_q - df) / cochrans_q) * 100.0
    return float(max(0.0, min(100.0, value)))


def _pooled_stats(mean_effect: float, variance: float) -> tuple[float, float, float, float]:
    safe_variance = max(variance, 1e-12)
    std_error = float(np.sqrt(safe_variance))
    z = float(stats.norm.ppf(0.975))
    ci_lower = float(mean_effect - z * std_error)
    ci_upper = float(mean_effect + z * std_error)
    if std_error <= 0.0:
        p_value = 1.0
    else:
        z_stat = float(mean_effect / std_error)
        p_value = float(2.0 * (1.0 - stats.norm.cdf(abs(z_stat))))
    return std_error, ci_lower, ci_upper, p_value


def pool_effects(
    outcome_name: str,
    effect_measure: str,
    effects: Sequence[float],
    variances: Sequence[float],
    heterogeneity_threshold: float = 40.0,
) -> MetaAnalysisResult:
    if len(effects) != len(variances):
        raise ValueError("effects and variances must be the same length")
    if len(effects) < 2:
        raise ValueError("at least two studies are required for pooling")

    effect_array = np.asarray(effects, dtype=float)
    variance_array = np.asarray(variances, dtype=float)
    base = combine_effects(effect_array, variance_array, method_re="dl")
    q = float(base.q)
    df = len(effects) - 1
    i_squared = _i_squared_percent(q, df)

    if i_squared < heterogeneity_threshold:
        model = "fixed"
        pooled_effect = float(base.mean_effect_fe)
        pooled_variance = float(base.var_eff_w_fe)
        method_re = None
        tau_squared = None
    else:
        model = "random"
        pooled_effect = float(base.mean_effect_re)
        pooled_variance = float(base.var_eff_w_re)
        if pooled_variance <= 0.0:
            pooled_variance = float(base.var_hksj_re) if float(base.var_hksj_re) > 0.0 else float(base.var_eff_w_fe)
        method_re = "dl"
        tau_squared = max(0.0, float(base.tau2))

    _, ci_lower, ci_upper, p_value = _pooled_stats(pooled_effect, pooled_variance)

    return MetaAnalysisResult(
        outcome_name=outcome_name,
        n_studies=len(effects),
        effect_measure=effect_measure,
        pooled_effect=pooled_effect,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        p_value=p_value,
        model=model,
        method_re=method_re,
        cochrans_q=q,
        i_squared=i_squared,
        tau_squared=tau_squared,
    )
