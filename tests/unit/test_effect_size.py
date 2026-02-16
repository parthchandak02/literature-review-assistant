from __future__ import annotations

import math

from src.synthesis.effect_size import (
    compute_binary_effect_size,
    compute_mean_difference_effect_size,
    compute_standardized_mean_difference,
)


def test_standardized_mean_difference_returns_effect_and_variance() -> None:
    effect, variance = compute_standardized_mean_difference(
        mean_treatment=82.0,
        sd_treatment=10.0,
        n_treatment=50,
        mean_control=76.0,
        sd_control=11.0,
        n_control=50,
    )
    assert math.isfinite(effect)
    assert variance > 0.0


def test_binary_effect_size_risk_ratio_returns_finite_values() -> None:
    effect, variance = compute_binary_effect_size(
        events_treatment=30,
        n_treatment=100,
        events_control=20,
        n_control=100,
        measure="risk_ratio",
    )
    assert math.isfinite(effect)
    assert variance > 0.0


def test_mean_difference_uses_deterministic_formula() -> None:
    effect, variance = compute_mean_difference_effect_size(
        mean_treatment=5.0,
        sd_treatment=2.0,
        n_treatment=20,
        mean_control=3.0,
        sd_control=2.5,
        n_control=20,
    )
    assert effect == 2.0
    assert abs(variance - ((4.0 / 20.0) + (6.25 / 20.0))) < 1e-12
