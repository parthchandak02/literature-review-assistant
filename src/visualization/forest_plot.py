"""Forest plot rendering for meta-analysis results."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from statsmodels.stats.meta_analysis import combine_effects


def render_forest_plot(
    effects: Sequence[float],
    variances: Sequence[float],
    labels: Sequence[str],
    output_path: str,
    title: str,
) -> str:
    if len(effects) != len(variances) or len(effects) != len(labels):
        raise ValueError("effects, variances, and labels must have the same length")
    if len(effects) < 2:
        raise ValueError("at least two studies are required for a forest plot")

    result = combine_effects(np.asarray(effects, dtype=float), np.asarray(variances, dtype=float), method_re="dl")
    q = float(result.q)
    df = max(1, len(effects) - 1)
    i2 = 0.0 if q <= 0.0 else max(0.0, min(100.0, ((q - df) / q) * 100.0))
    model = "fixed" if i2 < 40.0 else "random"
    fig = result.plot_forest(alpha=0.05, use_t=False)
    ax = fig.axes[0]
    ax.set_title(f"{title}\nmodel={model}, Q={q:.3f}, I2={i2:.1f}%")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(path)
