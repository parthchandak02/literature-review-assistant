"""Funnel plot rendering for publication bias inspection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt


def render_funnel_plot(
    effect_sizes: Sequence[float],
    standard_errors: Sequence[float],
    pooled_effect: float,
    output_path: str,
    title: str,
    minimum_studies: int = 10,
) -> str | None:
    if len(effect_sizes) != len(standard_errors):
        raise ValueError("effect_sizes and standard_errors must have the same length")
    if len(effect_sizes) < minimum_studies:
        return None

    effects = np.asarray(effect_sizes, dtype=float)
    ses = np.asarray(standard_errors, dtype=float)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(effects, ses, alpha=0.8)
    ax.axvline(x=pooled_effect, linestyle="--")
    upper = np.max(ses)
    lower = np.min(ses)
    ax.plot(
        [pooled_effect - 1.96 * upper, pooled_effect, pooled_effect + 1.96 * upper],
        [upper, 0.0, upper],
        linestyle="--",
    )
    ax.set_title(title)
    ax.set_xlabel("Effect size")
    ax.set_ylabel("Standard error")
    ax.set_ylim(max(upper * 1.05, 0.1), max(lower * 0.8, 0.0))
    ax.invert_yaxis()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return str(path)
