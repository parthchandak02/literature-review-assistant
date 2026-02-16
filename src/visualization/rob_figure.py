"""Risk-of-bias traffic-light figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from src.models import RiskOfBiasJudgment, RoB2Assessment


def _color_for(judgment: RiskOfBiasJudgment) -> str:
    if judgment == RiskOfBiasJudgment.LOW:
        return "green"
    if judgment == RiskOfBiasJudgment.SOME_CONCERNS:
        return "gold"
    return "red"


def render_rob_traffic_light(assessments: list[RoB2Assessment], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not assessments:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("RoB2 Traffic-Light Summary")
        ax.text(0.5, 0.5, "No assessments available", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        return path

    domains = [
        "domain_1_randomization",
        "domain_2_deviations",
        "domain_3_missing_data",
        "domain_4_measurement",
        "domain_5_selection",
    ]
    fig, ax = plt.subplots(figsize=(8, max(3, len(assessments) * 0.6)))
    for row_idx, assessment in enumerate(assessments):
        for col_idx, domain in enumerate(domains):
            judgment = getattr(assessment, domain)
            ax.scatter(
                col_idx,
                row_idx,
                s=260,
                c=_color_for(judgment),
                marker="o",
                edgecolors="black",
            )
    ax.set_xticks(range(len(domains)))
    ax.set_xticklabels(["D1", "D2", "D3", "D4", "D5"])
    ax.set_yticks(range(len(assessments)))
    ax.set_yticklabels([item.paper_id for item in assessments])
    ax.set_title("RoB2 Traffic-Light Summary")
    ax.set_xlim(-0.6, len(domains) - 0.4)
    ax.set_ylim(-0.6, len(assessments) - 0.4)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
