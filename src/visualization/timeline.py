"""Publication year distribution timeline for included studies."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from src.models import CandidatePaper


def render_timeline(papers: list[CandidatePaper], output_path: str) -> Path:
    """Plot publication year distribution as bar chart."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    years = [p.year for p in papers if p.year is not None]
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
    sorted_years = sorted(counts.keys())
    vals = [counts[y] for y in sorted_years]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(sorted_years, vals, color="steelblue", edgecolor="black")
    ax.set_xlabel("Publication Year")
    ax.set_ylabel("Number of Studies")
    ax.set_title("Publication Timeline of Included Studies")
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
