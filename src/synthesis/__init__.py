"""Synthesis and meta-analysis package."""

from src.synthesis.effect_size import (
    compute_binary_effect_size,
    compute_mean_difference_effect_size,
    compute_standardized_mean_difference,
)
from src.synthesis.feasibility import SynthesisFeasibility, assess_meta_analysis_feasibility
from src.synthesis.meta_analysis import pool_effects
from src.synthesis.narrative import NarrativeSynthesis, build_narrative_synthesis

__all__ = [
    "NarrativeSynthesis",
    "SynthesisFeasibility",
    "assess_meta_analysis_feasibility",
    "build_narrative_synthesis",
    "compute_binary_effect_size",
    "compute_mean_difference_effect_size",
    "compute_standardized_mean_difference",
    "pool_effects",
]
