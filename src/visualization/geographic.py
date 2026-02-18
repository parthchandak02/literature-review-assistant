"""Geographic distribution of included studies."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from src.models import CandidatePaper


def render_geographic(papers: list[CandidatePaper], output_path: str) -> Path:
    """Plot geographic distribution as bar chart when country data exists."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    n = len(papers)
    countries = [p.country for p in papers if p.country]
    if not countries:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.set_title("Geographic Distribution")
        ax.text(
            0.5,
            0.5,
            f"Geographic data not yet extracted.\n{n} studies included (country from affiliation).",
            ha="center",
            va="center",
            fontsize=10,
        )
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    counts = Counter(countries)
    labels = list(counts.keys())
    values = list(counts.values())
    labels, values = zip(*sorted(zip(labels, values), key=lambda x: -x[1]))

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.6), 4))
    ax.bar(range(len(labels)), values, color="steelblue", edgecolor="black")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Number of studies")
    ax.set_title("Geographic Distribution of Included Studies")
    ax.set_xlim(-0.5, len(labels) - 0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
