"""Publication year distribution timeline for included studies."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from src.models import CandidatePaper


def render_timeline(papers: list[CandidatePaper], output_path: str) -> Path:
    """Plot publication year distribution as bar chart.

    Uses a continuous x-axis from min to max year so gap years appear as
    zero-height bars (making temporal patterns and gaps explicit).  Papers
    with no recorded publication year are counted and disclosed in a footnote.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    total_papers = len(papers)
    years = [p.year for p in papers if p.year is not None]
    n_missing_year = total_papers - len(years)

    if not years:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.set_title("Publication Timeline")
        ax.text(0.5, 0.5, "No publication years available", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    counts = Counter(years)
    min_year = min(years)
    max_year = max(years)
    # Continuous range: every year from min to max, zero for gaps
    all_years = list(range(min_year, max_year + 1))
    vals = [counts.get(y, 0) for y in all_years]

    # Width the figure proportionally to the year span
    fig_width = max(8, len(all_years) * 0.7)
    fig, ax = plt.subplots(figsize=(fig_width, 4))
    bars = ax.bar(all_years, vals, color="steelblue", edgecolor="black", linewidth=0.6)
    # Label only non-zero bars to avoid clutter
    for bar, val in zip(bars, vals):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(vals) * 0.02,
                str(val),
                ha="center", va="bottom", fontsize=9, fontweight="bold",
            )
    ax.set_xticks(all_years)
    ax.set_xticklabels([str(y) for y in all_years], fontsize=9, rotation=45, ha="right")
    ax.set_xlabel("Publication Year", fontsize=9)
    ax.set_ylabel("Number of Studies", fontsize=9)
    ax.set_title("Publication Timeline of Included Studies", fontsize=11, pad=8)
    ax.set_ylim(0, max(vals) * 1.25)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if n_missing_year > 0:
        fig.text(
            0.5, 0.01,
            f"Note: Publication year not reported for {n_missing_year} of {total_papers} included studies.",
            ha="center", va="bottom", fontsize=7.5, color="gray",
        )
        fig.subplots_adjust(bottom=0.18)

    fig.tight_layout(rect=[0, 0.05 if n_missing_year > 0 else 0, 1, 1])
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
