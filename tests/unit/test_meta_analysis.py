from __future__ import annotations

import pytest

from src.synthesis.meta_analysis import pool_effects


def test_pool_effects_selects_fixed_model_for_low_heterogeneity() -> None:
    result = pool_effects(
        outcome_name="knowledge_retention",
        effect_measure="mean_difference",
        effects=[0.20, 0.22, 0.21, 0.23],
        variances=[0.04, 0.04, 0.05, 0.04],
        heterogeneity_threshold=40.0,
    )
    assert result.model == "fixed"
    assert result.i_squared < 40.0


def test_pool_effects_selects_random_model_for_high_heterogeneity() -> None:
    result = pool_effects(
        outcome_name="knowledge_retention",
        effect_measure="mean_difference",
        effects=[-0.70, 0.10, 0.95, -0.20, 1.10],
        variances=[0.03, 0.02, 0.03, 0.02, 0.03],
        heterogeneity_threshold=40.0,
    )
    assert result.model == "random"
    assert result.method_re == "dl"
    assert result.i_squared >= 40.0


def test_pool_effects_requires_two_or_more_studies() -> None:
    with pytest.raises(ValueError, match="at least two studies"):
        pool_effects(
            outcome_name="knowledge_retention",
            effect_measure="mean_difference",
            effects=[0.2],
            variances=[0.04],
        )
