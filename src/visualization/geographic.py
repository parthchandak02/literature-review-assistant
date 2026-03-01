"""Geographic distribution of included studies.

When country data is available on CandidatePaper it is used directly.
When not available (the common case -- search APIs rarely return affiliation
country), the function falls back to a source-database distribution bar chart,
which accurately reflects where the literature was indexed and is still
meaningful to readers assessing database coverage.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

from src.models import CandidatePaper

# Human-readable display names for known source database identifiers.
_DB_DISPLAY = {
    "pubmed": "PubMed",
    "arxiv": "arXiv",
    "crossref": "Crossref",
    "semantic_scholar": "Semantic Scholar",
    "ieee_xplore": "IEEE Xplore",
    "openalex": "OpenAlex",
    "perplexity_web": "Web (Perplexity)",
    "web": "Web",
}


def _render_bar(ax, labels, values, title: str, ylabel: str, color: str = "steelblue") -> None:
    bars = ax.bar(range(len(labels)), values, color=color, edgecolor="black", linewidth=0.6)
    ax.bar_label(bars, padding=4, fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(labels)))
    # Use horizontal labels when all labels are short enough; otherwise tilt slightly.
    max_label_len = max(len(lbl) for lbl in labels) if labels else 0
    if max_label_len <= 12:
        ax.set_xticklabels(labels, rotation=0, ha="center", fontsize=9)
    else:
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xlim(-0.5, len(labels) - 0.5)
    # Add headroom above bars so labels are not clipped
    ax.set_ylim(0, max(values) * 1.2)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def render_geographic(papers: list[CandidatePaper], output_path: str) -> Path:
    """Plot geographic distribution when country data exists, else source-database breakdown."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    total_papers = len(papers)
    countries = [p.country for p in papers if p.country]
    n_missing = total_papers - len(countries)

    if countries:
        counts = Counter(countries)
        labels_raw, values = zip(*sorted(counts.items(), key=lambda x: -x[1]))
        labels = list(labels_raw)
        values = list(values)

        # Append "Not reported" bar so readers know coverage is partial
        if n_missing > 0:
            labels.append("Not reported")
            values.append(n_missing)

        n_with_data = total_papers - n_missing
        if n_missing > 0:
            title = (
                f"Geographic Distribution of Included Studies "
                f"(country reported for {n_with_data} of {total_papers} studies)"
            )
        else:
            title = "Geographic Distribution of Included Studies"

        fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.9), 4))
        _render_bar(ax, labels, values, title=title, ylabel="Number of studies")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
        plt.close(fig)
        return path

    # Country data not available -- fall back to source-database distribution.
    sources = [
        _DB_DISPLAY.get(p.source_database or "", p.source_database or "Unknown")
        for p in papers
        if p.source_database
    ]
    if not sources:
        # Absolute last resort: plain text notice
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("Source Distribution")
        ax.text(0.5, 0.5, f"No source metadata available ({len(papers)} studies).",
                ha="center", va="center", fontsize=9)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
        plt.close(fig)
        return path

    counts = Counter(sources)
    labels_raw, values = zip(*sorted(counts.items(), key=lambda x: -x[1]))
    labels = list(labels_raw)
    values = list(values)
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.0), 5))
    _render_bar(
        ax, labels, values,
        title=f"Included Studies by Source Database (n={len(papers)})",
        ylabel="Number of studies",
        color="steelblue",
    )
    # Footnote in figure coordinates (not axes coords) so it never overlaps x-tick labels.
    fig.subplots_adjust(bottom=0.22)
    fig.text(
        0.5, 0.01,
        "Note: Country of origin not available from search API metadata. "
        "Chart shows the database from which each included study was retrieved.",
        ha="center", va="bottom", fontsize=7, color="gray",
        wrap=True,
    )
    fig.savefig(path, dpi=150, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return path
