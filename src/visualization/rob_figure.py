"""Risk-of-bias traffic-light figure.

Layout (top to bottom):
  1. Dot matrix  -- one row per study, one column per domain (D1-D7)
  2. Color legend -- Low / Moderate / Serious-Critical / Not assessed
  3. Summary bars -- stacked % bar per domain (aggregate view)
  4. Domain key   -- plain-text table: D1 = Confounding, D2 = ..., etc.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.models import CandidatePaper, RiskOfBiasJudgment, RobinsIAssessment, RobinsIJudgment, RoB2Assessment

# ---------------------------------------------------------------------------
# Domain metadata
# ---------------------------------------------------------------------------

_ROB2_DOMAINS = [
    ("D1", "domain_1_randomization", "Randomization process"),
    ("D2", "domain_2_deviations", "Deviations from interventions"),
    ("D3", "domain_3_missing_data", "Missing outcome data"),
    ("D4", "domain_4_measurement", "Outcome measurement"),
    ("D5", "domain_5_selection", "Selection of reported result"),
]

_ROBINS_I_DOMAINS = [
    ("D1", "domain_1_confounding", "Confounding", "Are there uncontrolled confounders?"),
    ("D2", "domain_2_selection", "Selection of participants", "Was selection of participants biased?"),
    ("D3", "domain_3_classification", "Classification of interventions", "Is the intervention correctly defined?"),
    ("D4", "domain_4_deviations", "Deviations from interventions", "Were co-interventions or crossover issues present?"),
    ("D5", "domain_5_missing_data", "Missing data", "Is outcome data complete?"),
    ("D6", "domain_6_measurement", "Outcome measurement", "Was the outcome measured without bias?"),
    ("D7", "domain_7_reported_result", "Reported result selection", "Was the reported result chosen selectively?"),
]

# Cochrane standard traffic-light colors
_COLOR_LOW = "#00CC00"        # green
_COLOR_MODERATE = "#E6AC00"   # amber/gold
_COLOR_SERIOUS = "#CC0000"    # red
_COLOR_NOT_ASSESSED = "#808080"  # gray

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GENERIC_AUTHORS = frozenset({"unknown", "none", "na", "author", "anonymous", "anon"})
_GENERIC_TITLE_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "being", "with", "this", "that",
    "fig", "figure", "table", "appendix", "section", "chapter",
    "methods", "method", "results", "result", "discussion", "conclusion",
    "conclusions", "introduction", "abstract", "study", "studies",
    "review", "systematic", "literature", "analysis", "impact",
    "effect", "effects", "use", "using", "based", "new", "novel",
    "analysing", "investigating", "usability", "examining", "exploring",
    "evaluating", "evaluation", "assessment", "towards", "toward",
    "role", "applying", "application", "understanding", "comparing",
    "developing", "improving", "educational", "learning", "teaching",
})


def _paper_label(paper_id: str, paper_lookup: Dict[str, CandidatePaper], index: int) -> str:
    """Build a short human-readable label for a paper row.

    Uses CandidatePaper.display_label (computed once at save time) when available.
    Falls back to local derivation for papers from older DBs that predate the
    display_label column.
    """
    paper = paper_lookup.get(paper_id)
    if paper is None:
        return f"Paper{index + 1}"

    year_str = str(paper.year) if paper.year else "n.d."

    # Preferred path: use the canonical label stored in the DB.
    if paper.display_label:
        return f"{paper.display_label} ({year_str})"

    # Fallback for papers from older DBs without display_label.
    author_token = ""
    if paper.authors:
        raw = str(paper.authors[0]).split()[0] if str(paper.authors[0]).split() else ""
        token = re.sub(r"[^a-zA-Z]", "", raw)
        if len(token) >= 2 and token.lower() not in _GENERIC_AUTHORS:
            author_token = token

    if not author_token and paper.title:
        for word in paper.title.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if len(candidate) >= 4 and candidate.lower() not in _GENERIC_TITLE_WORDS:
                author_token = candidate
                break

    if not author_token:
        if paper.title:
            truncated = paper.title[:22].strip()
            if len(paper.title) > 22:
                truncated += ".."
            return truncated
        return f"Paper{index + 1}"

    return f"{author_token} ({year_str})"


def _color_for_rob2(judgment: RiskOfBiasJudgment) -> str:
    if judgment == RiskOfBiasJudgment.LOW:
        return _COLOR_LOW
    if judgment == RiskOfBiasJudgment.SOME_CONCERNS:
        return _COLOR_MODERATE
    return _COLOR_SERIOUS


def _color_for_robins_i(judgment: RobinsIJudgment) -> str:
    if judgment == RobinsIJudgment.LOW:
        return _COLOR_LOW
    if judgment == RobinsIJudgment.MODERATE:
        return _COLOR_MODERATE
    if judgment in (RobinsIJudgment.SERIOUS, RobinsIJudgment.CRITICAL):
        return _COLOR_SERIOUS
    return _COLOR_NOT_ASSESSED


def _robins_i_color_key(judgment: RobinsIJudgment) -> str:
    """Return the bucket name used for summary bar aggregation."""
    if judgment == RobinsIJudgment.LOW:
        return "low"
    if judgment == RobinsIJudgment.MODERATE:
        return "moderate"
    if judgment in (RobinsIJudgment.SERIOUS, RobinsIJudgment.CRITICAL):
        return "serious"
    return "not_assessed"


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_rob_traffic_light(
    rob2: List[RoB2Assessment],
    robins_i: List[RobinsIAssessment],
    output_path: str,
    paper_lookup: Optional[Dict[str, CandidatePaper]] = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rob2 and not robins_i:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("Risk of Bias Traffic-Light Summary")
        ax.text(0.5, 0.5, "No assessments available", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    lookup = paper_lookup or {}

    # Determine which tool(s) are present and pick domain list
    # (current pipeline only produces ROBINS-I; keep RoB 2 path for completeness)
    using_robins = bool(robins_i)
    domains = _ROBINS_I_DOMAINS if using_robins else [
        (code, attr, name, "") for code, attr, name in _ROB2_DOMAINS
    ]
    n_domains = len(domains)
    total_rows = len(rob2) + len(robins_i)
    n_studies = total_rows

    # -----------------------------------------------------------------------
    # Figure layout: 4 panels stacked vertically via GridSpec
    #   row 0 -- dot matrix (tall, proportional to study count)
    #   row 1 -- color legend bar (fixed thin strip)
    #   row 2 -- summary stacked bar chart
    #   row 3 -- domain key table
    # -----------------------------------------------------------------------
    dot_height = max(4, n_studies * 0.45)
    legend_height = 0.5
    summary_height = 2.0
    key_height = max(1.8, n_domains * 0.28)
    total_height = dot_height + legend_height + summary_height + key_height

    fig = plt.figure(figsize=(max(10, n_domains * 1.3), total_height))
    gs = gridspec.GridSpec(
        4, 1,
        height_ratios=[dot_height, legend_height, summary_height, key_height],
        hspace=0.08,
        figure=fig,
    )

    ax_dots = fig.add_subplot(gs[0])
    ax_legend = fig.add_subplot(gs[1])
    ax_summary = fig.add_subplot(gs[2])
    ax_key = fig.add_subplot(gs[3])

    # -----------------------------------------------------------------------
    # Panel 1: Dot matrix
    # -----------------------------------------------------------------------
    y_labels: List[str] = []
    row_idx = 0

    domain_colors_per_col: List[List[str]] = [[] for _ in range(n_domains)]

    if rob2:
        for assessment in rob2:
            for col_idx, (code, attr, *_rest) in enumerate(_ROB2_DOMAINS):
                judgment = getattr(assessment, attr)
                color = _color_for_rob2(judgment)
                ax_dots.scatter(col_idx, row_idx, s=260, c=color, marker="o", edgecolors="black", linewidths=0.6, zorder=3)
                if col_idx < len(domain_colors_per_col):
                    domain_colors_per_col[col_idx].append(_robins_i_color_key(
                        RobinsIJudgment.MODERATE  # RoB 2 uses different enum -- map conservatively
                    ))
            label = _paper_label(assessment.paper_id, lookup, row_idx)
            y_labels.append(f"{label} (RoB2)")
            row_idx += 1

    if robins_i:
        for assessment in robins_i:
            for col_idx, (code, attr, *_rest) in enumerate(_ROBINS_I_DOMAINS):
                judgment = getattr(assessment, attr)
                color = _color_for_robins_i(judgment)
                ax_dots.scatter(col_idx, row_idx, s=260, c=color, marker="o", edgecolors="black", linewidths=0.6, zorder=3)
                domain_colors_per_col[col_idx].append(_robins_i_color_key(judgment))
            label = _paper_label(assessment.paper_id, lookup, row_idx)
            y_labels.append(f"{label} (ROBINS-I)")
            row_idx += 1

    ax_dots.set_yticks(range(total_rows))
    ax_dots.set_yticklabels(y_labels, fontsize=8)
    ax_dots.set_ylim(-0.6, total_rows - 0.4)
    ax_dots.set_xticks(range(n_domains))
    ax_dots.set_xticklabels([d[0] for d in domains], fontsize=9, fontweight="bold")
    ax_dots.set_xlim(-0.6, n_domains - 0.4)
    ax_dots.tick_params(axis="x", which="both", bottom=False)
    ax_dots.grid(axis="x", color="#e0e0e0", linewidth=0.5, zorder=0)
    ax_dots.set_frame_on(True)
    tool_label = "ROBINS-I" if using_robins else "RoB 2"
    ax_dots.set_title(
        f"{tool_label} Traffic-Light Summary  (n={n_studies} {'studies' if n_studies != 1 else 'study'})",
        fontsize=11, pad=6, fontweight="bold",
    )

    # -----------------------------------------------------------------------
    # Panel 2: Color legend
    # -----------------------------------------------------------------------
    ax_legend.axis("off")
    legend_patches = [
        mpatches.Patch(facecolor=_COLOR_LOW, edgecolor="black", linewidth=0.6, label="Low risk"),
        mpatches.Patch(facecolor=_COLOR_MODERATE, edgecolor="black", linewidth=0.6, label="Moderate risk"),
        mpatches.Patch(facecolor=_COLOR_SERIOUS, edgecolor="black", linewidth=0.6, label="Serious / Critical risk"),
        mpatches.Patch(facecolor=_COLOR_NOT_ASSESSED, edgecolor="black", linewidth=0.6, label="Not assessed / No information"),
    ]
    ax_legend.legend(
        handles=legend_patches,
        loc="center",
        ncol=4,
        frameon=False,
        fontsize=8.5,
        handlelength=1.4,
        handleheight=0.9,
    )

    # -----------------------------------------------------------------------
    # Panel 3: Summary stacked % bar chart (one bar per domain)
    # -----------------------------------------------------------------------
    bucket_order = ["low", "moderate", "serious", "not_assessed"]
    bucket_colors = {
        "low": _COLOR_LOW,
        "moderate": _COLOR_MODERATE,
        "serious": _COLOR_SERIOUS,
        "not_assessed": _COLOR_NOT_ASSESSED,
    }
    bucket_labels = {
        "low": "Low",
        "moderate": "Moderate",
        "serious": "Serious/Critical",
        "not_assessed": "Not assessed",
    }

    x_pos = list(range(n_domains))
    left = [0.0] * n_domains

    for bucket in bucket_order:
        proportions = []
        for col_idx in range(n_domains):
            col = domain_colors_per_col[col_idx]
            pct = (col.count(bucket) / len(col) * 100) if col else 0.0
            proportions.append(pct)
        ax_summary.bar(
            x_pos, proportions, bottom=left,
            color=bucket_colors[bucket],
            edgecolor="white", linewidth=0.4,
            label=bucket_labels[bucket],
            width=0.6,
        )
        # Add percentage labels inside bars where there is enough room
        for xi, (prop, bot) in enumerate(zip(proportions, left)):
            if prop >= 12:
                ax_summary.text(
                    xi, bot + prop / 2,
                    f"{prop:.0f}%",
                    ha="center", va="center",
                    fontsize=7, fontweight="bold", color="white",
                )
        left = [lv + p for lv, p in zip(left, proportions)]

    ax_summary.set_xticks(x_pos)
    ax_summary.set_xticklabels([d[0] for d in domains], fontsize=9, fontweight="bold")
    ax_summary.set_xlim(-0.6, n_domains - 0.4)
    ax_summary.set_ylim(0, 100)
    ax_summary.set_ylabel("% of studies", fontsize=8)
    ax_summary.set_title("Proportion of Studies per Risk Level by Domain", fontsize=9, pad=4)
    ax_summary.spines["top"].set_visible(False)
    ax_summary.spines["right"].set_visible(False)
    ax_summary.tick_params(axis="x", which="both", bottom=False)

    # -----------------------------------------------------------------------
    # Panel 4: Domain key table
    # -----------------------------------------------------------------------
    ax_key.axis("off")
    ax_key.set_title("Domain Key", fontsize=9, fontweight="bold", pad=2, loc="left")

    if using_robins:
        rows = [(code, name, desc) for code, _attr, name, desc in _ROBINS_I_DOMAINS]
    else:
        rows = [(code, name, "") for code, _attr, name in _ROB2_DOMAINS]

    n_rows = len(rows)
    row_h = 1.0 / (n_rows + 1)
    col_x = [0.01, 0.09, 0.38]  # code | name | description

    # Header
    for x, hdr in zip(col_x, ["Code", "Domain name", "What it assesses"]):
        ax_key.text(x, 1.0 - row_h * 0.4, hdr, transform=ax_key.transAxes,
                    fontsize=8, fontweight="bold", va="top", color="#333333")

    ax_key.axhline(y=1.0 - row_h * 0.85, xmin=0.01, xmax=0.99,
                   color="#aaaaaa", linewidth=0.6)

    for i, (code, name, desc) in enumerate(rows):
        y = 1.0 - row_h * (i + 1.2)
        ax_key.text(col_x[0], y, code, transform=ax_key.transAxes,
                    fontsize=8, fontweight="bold", va="top", color="#333333")
        ax_key.text(col_x[1], y, name, transform=ax_key.transAxes,
                    fontsize=8, va="top", color="#222222")
        if desc:
            ax_key.text(col_x[2], y, desc, transform=ax_key.transAxes,
                        fontsize=7.5, va="top", color="#555555", style="italic")

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
