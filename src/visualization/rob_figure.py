"""Risk-of-bias traffic-light figures.

Produces up to two separate PNG files:
  1. ROBINS-I figure  (output_path)   -- non-randomized interventional studies
  2. RoB 2 figure     (rob2_output_path) -- RCTs only, separate axes with RoB2 domains

A disclosure note is embedded in each figure when studies were not assessable
(OTHER design: systematic reviews, technical reports, proof-of-concept papers).

Layout per figure (top to bottom):
  Panel 0 -- dot matrix  (one row per study, one column per domain)
  Panel 1 -- color legend
  Panel 2 -- summary stacked % bar chart
  Panel 3 -- domain key table
  Panel 4 -- disclosure note (when not_applicable_count > 0, ROBINS-I figure only)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.models import (
    CandidatePaper,
    RiskOfBiasJudgment,
    RoB2Assessment,
    RobinsIAssessment,
    RobinsIJudgment,
)

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
_COLOR_LOW = "#00CC00"
_COLOR_MODERATE = "#E6AC00"
_COLOR_SERIOUS = "#CC0000"
_COLOR_NOT_ASSESSED = "#808080"

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
    paper = paper_lookup.get(paper_id)
    if paper is None:
        return f"Paper{index + 1}"

    year_str = str(paper.year) if paper.year else "n.d."

    if paper.display_label:
        return f"{paper.display_label} ({year_str})"

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


def _rob2_color_key(judgment: RiskOfBiasJudgment) -> str:
    if judgment == RiskOfBiasJudgment.LOW:
        return "low"
    if judgment == RiskOfBiasJudgment.SOME_CONCERNS:
        return "moderate"
    return "serious"


def _color_for_robins_i(judgment: RobinsIJudgment) -> str:
    if judgment == RobinsIJudgment.LOW:
        return _COLOR_LOW
    if judgment == RobinsIJudgment.MODERATE:
        return _COLOR_MODERATE
    if judgment in (RobinsIJudgment.SERIOUS, RobinsIJudgment.CRITICAL):
        return _COLOR_SERIOUS
    return _COLOR_NOT_ASSESSED


def _robins_i_color_key(judgment: RobinsIJudgment) -> str:
    if judgment == RobinsIJudgment.LOW:
        return "low"
    if judgment == RobinsIJudgment.MODERATE:
        return "moderate"
    if judgment in (RobinsIJudgment.SERIOUS, RobinsIJudgment.CRITICAL):
        return "serious"
    return "not_assessed"


# ---------------------------------------------------------------------------
# Single-tool figure renderer (shared logic for both RoB2 and ROBINS-I)
# ---------------------------------------------------------------------------

def _render_single_tool_figure(
    domains: list,
    row_data: list[tuple[str, list[str]]],  # [(label, [color_keys_per_domain])]
    dot_colors: list[list[str]],             # [row][col] -> hex color
    title: str,
    path: Path,
    disclosure_note: str = "",
) -> None:
    """Render a traffic-light figure for a single RoB tool."""
    n_domains = len(domains)
    n_studies = len(row_data)

    has_note = bool(disclosure_note)
    note_height = 0.5 if has_note else 0.0
    dot_height = max(4, n_studies * 0.45)
    legend_height = 0.5
    summary_height = 2.0
    key_height = max(1.8, n_domains * 0.28)
    total_height = dot_height + legend_height + summary_height + key_height + note_height

    n_rows_gs = 5 if has_note else 4
    height_ratios = [dot_height, legend_height, summary_height, key_height]
    if has_note:
        height_ratios.append(note_height)

    fig = plt.figure(figsize=(max(10, n_domains * 1.3), total_height))
    gs = gridspec.GridSpec(n_rows_gs, 1, height_ratios=height_ratios, hspace=0.08, figure=fig)

    ax_dots = fig.add_subplot(gs[0])
    ax_legend = fig.add_subplot(gs[1])
    ax_summary = fig.add_subplot(gs[2])
    ax_key = fig.add_subplot(gs[3])
    ax_note = fig.add_subplot(gs[4]) if has_note else None

    # --- Panel 0: Dot matrix ---
    y_labels = [label for label, _ in row_data]
    domain_colors_per_col: List[List[str]] = [[] for _ in range(n_domains)]

    for row_idx, (label, color_keys) in enumerate(row_data):
        for col_idx, (hex_color, key) in enumerate(zip(dot_colors[row_idx], color_keys)):
            ax_dots.scatter(
                col_idx, row_idx, s=260, c=hex_color, marker="o",
                edgecolors="black", linewidths=0.6, zorder=3,
            )
            domain_colors_per_col[col_idx].append(key)

    ax_dots.set_yticks(range(n_studies))
    ax_dots.set_yticklabels(y_labels, fontsize=8)
    ax_dots.set_ylim(-0.6, n_studies - 0.4)
    ax_dots.set_xticks(range(n_domains))
    ax_dots.set_xticklabels([d[0] for d in domains], fontsize=9, fontweight="bold")
    ax_dots.set_xlim(-0.6, n_domains - 0.4)
    ax_dots.tick_params(axis="x", which="both", bottom=False)
    ax_dots.grid(axis="x", color="#e0e0e0", linewidth=0.5, zorder=0)
    ax_dots.set_frame_on(True)
    ax_dots.set_title(title, fontsize=11, pad=6, fontweight="bold")

    # --- Panel 1: Color legend ---
    ax_legend.axis("off")
    legend_patches = [
        mpatches.Patch(facecolor=_COLOR_LOW, edgecolor="black", linewidth=0.6, label="Low risk"),
        mpatches.Patch(facecolor=_COLOR_MODERATE, edgecolor="black", linewidth=0.6, label="Moderate / Some concerns"),
        mpatches.Patch(facecolor=_COLOR_SERIOUS, edgecolor="black", linewidth=0.6, label="Serious / Critical / High risk"),
        mpatches.Patch(facecolor=_COLOR_NOT_ASSESSED, edgecolor="black", linewidth=0.6, label="Not assessed / No information"),
    ]
    ax_legend.legend(handles=legend_patches, loc="center", ncol=4, frameon=False,
                     fontsize=8.5, handlelength=1.4, handleheight=0.9)

    # --- Panel 2: Summary stacked % bar chart ---
    bucket_order = ["low", "moderate", "serious", "not_assessed"]
    bucket_colors = {
        "low": _COLOR_LOW, "moderate": _COLOR_MODERATE,
        "serious": _COLOR_SERIOUS, "not_assessed": _COLOR_NOT_ASSESSED,
    }
    bucket_labels = {
        "low": "Low", "moderate": "Moderate",
        "serious": "Serious/Critical", "not_assessed": "Not assessed",
    }
    x_pos = list(range(n_domains))
    left = [0.0] * n_domains
    for bucket in bucket_order:
        proportions = []
        for col_idx in range(n_domains):
            col = domain_colors_per_col[col_idx]
            pct = (col.count(bucket) / len(col) * 100) if col else 0.0
            proportions.append(pct)
        ax_summary.bar(x_pos, proportions, bottom=left, color=bucket_colors[bucket],
                       edgecolor="white", linewidth=0.4, label=bucket_labels[bucket], width=0.6)
        for xi, (prop, bot) in enumerate(zip(proportions, left)):
            if prop >= 12:
                ax_summary.text(xi, bot + prop / 2, f"{prop:.0f}%", ha="center", va="center",
                                fontsize=7, fontweight="bold", color="white")
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

    # --- Panel 3: Domain key table ---
    ax_key.axis("off")
    ax_key.set_title("Domain Key", fontsize=9, fontweight="bold", pad=2, loc="left")
    if len(domains[0]) == 4:
        rows = [(d[0], d[2], d[3]) for d in domains]
    else:
        rows = [(d[0], d[2], "") for d in domains]

    n_rows = len(rows)
    row_h = 1.0 / (n_rows + 1)
    col_x = [0.01, 0.09, 0.38]
    for x, hdr in zip(col_x, ["Code", "Domain name", "What it assesses"]):
        ax_key.text(x, 1.0 - row_h * 0.4, hdr, transform=ax_key.transAxes,
                    fontsize=8, fontweight="bold", va="top", color="#333333")
    ax_key.axhline(y=1.0 - row_h * 0.85, xmin=0.01, xmax=0.99, color="#aaaaaa", linewidth=0.6)
    for i, (code, name, desc) in enumerate(rows):
        y = 1.0 - row_h * (i + 1.2)
        ax_key.text(col_x[0], y, code, transform=ax_key.transAxes,
                    fontsize=8, fontweight="bold", va="top", color="#333333")
        ax_key.text(col_x[1], y, name, transform=ax_key.transAxes,
                    fontsize=8, va="top", color="#222222")
        if desc:
            ax_key.text(col_x[2], y, desc, transform=ax_key.transAxes,
                        fontsize=7.5, va="top", color="#555555", style="italic")

    # --- Panel 4: Disclosure note ---
    if ax_note is not None:
        ax_note.axis("off")
        ax_note.text(0.0, 0.6, disclosure_note, transform=ax_note.transAxes,
                     fontsize=7.5, va="top", color="#555555", style="italic", wrap=True)

    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_rob_traffic_light(
    rob2: List[RoB2Assessment],
    robins_i: List[RobinsIAssessment],
    output_path: str,
    paper_lookup: Optional[Dict[str, CandidatePaper]] = None,
    not_applicable_count: int = 0,
    rob2_output_path: Optional[str] = None,
) -> Path:
    """Render separate ROBINS-I and RoB2 traffic-light figures.

    - output_path       -> ROBINS-I figure (or empty-state placeholder)
    - rob2_output_path  -> RoB2 figure (when rob2 list is non-empty and path provided)
    - not_applicable_count -> number of OTHER-design studies; disclosed in figure note
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lookup = paper_lookup or {}

    if not rob2 and not robins_i:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("Risk of Bias Traffic-Light Summary")
        msg = "No assessments available."
        if not_applicable_count:
            msg += (
                f" {not_applicable_count} included studies (systematic reviews, "
                "technical reports) were not amenable to ROBINS-I or RoB2 assessment."
            )
        ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=8, wrap=True)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    # Build disclosure note for ROBINS-I figure
    disclosure_parts = []
    if not_applicable_count:
        disclosure_parts.append(
            f"Note: {not_applicable_count} included studies (systematic reviews, "
            "technical reports, proof-of-concept papers) are not primary interventional "
            "studies and were not assessed with ROBINS-I. They are excluded from this figure."
        )
    if rob2 and robins_i and rob2_output_path:
        disclosure_parts.append(
            f"Note: {len(rob2)} RCT(s) were assessed using RoB2 and are shown in a separate figure."
        )
    disclosure_note = " ".join(disclosure_parts)

    # --- Render ROBINS-I figure ---
    if robins_i:
        row_data: list[tuple[str, list[str]]] = []
        dot_colors_robins: list[list[str]] = []
        for idx, assessment in enumerate(robins_i):
            label = _paper_label(assessment.paper_id, lookup, idx)
            color_keys = []
            hex_colors = []
            for _code, attr, *_rest in _ROBINS_I_DOMAINS:
                judgment = getattr(assessment, attr)
                hex_colors.append(_color_for_robins_i(judgment))
                color_keys.append(_robins_i_color_key(judgment))
            row_data.append((label, color_keys))
            dot_colors_robins.append(hex_colors)

        n = len(robins_i)
        title = f"ROBINS-I Traffic-Light Summary  (n={n} {'study' if n == 1 else 'studies'})"
        _render_single_tool_figure(
            domains=_ROBINS_I_DOMAINS,
            row_data=row_data,
            dot_colors=dot_colors_robins,
            title=title,
            path=path,
            disclosure_note=disclosure_note,
        )
    else:
        # No ROBINS-I studies; write a minimal placeholder
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("ROBINS-I Traffic-Light Summary")
        msg = "No non-randomized interventional studies assessed with ROBINS-I."
        if disclosure_note:
            msg += f" {disclosure_note}"
        ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=8, wrap=True)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    # --- Render separate RoB2 figure ---
    if rob2 and rob2_output_path:
        rob2_path = Path(rob2_output_path)
        rob2_path.parent.mkdir(parents=True, exist_ok=True)

        row_data_rob2: list[tuple[str, list[str]]] = []
        dot_colors_rob2: list[list[str]] = []
        for idx, assessment in enumerate(rob2):
            label = _paper_label(assessment.paper_id, lookup, idx)
            color_keys = []
            hex_colors = []
            for _code, attr, *_rest in _ROB2_DOMAINS:
                judgment = getattr(assessment, attr)
                hex_colors.append(_color_for_rob2(judgment))
                color_keys.append(_rob2_color_key(judgment))
            row_data_rob2.append((label, color_keys))
            dot_colors_rob2.append(hex_colors)

        n = len(rob2)
        title_rob2 = f"RoB 2 Traffic-Light Summary  (n={n} {'RCT' if n == 1 else 'RCTs'})"
        _render_single_tool_figure(
            domains=_ROB2_DOMAINS,
            row_data=row_data_rob2,
            dot_colors=dot_colors_rob2,
            title=title_rob2,
            path=rob2_path,
        )

    return path
