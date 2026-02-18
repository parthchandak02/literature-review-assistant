"""Risk-of-bias traffic-light figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from src.models import RiskOfBiasJudgment, RobinsIAssessment, RobinsIJudgment, RoB2Assessment


def _color_for_rob2(judgment: RiskOfBiasJudgment) -> str:
    if judgment == RiskOfBiasJudgment.LOW:
        return "green"
    if judgment == RiskOfBiasJudgment.SOME_CONCERNS:
        return "gold"
    return "red"


def _color_for_robins_i(judgment: RobinsIJudgment) -> str:
    if judgment == RobinsIJudgment.LOW:
        return "green"
    if judgment == RobinsIJudgment.MODERATE:
        return "gold"
    if judgment in (RobinsIJudgment.SERIOUS, RobinsIJudgment.CRITICAL):
        return "red"
    return "gray"


def render_rob_traffic_light(
    rob2: list[RoB2Assessment],
    robins_i: list[RobinsIAssessment],
    output_path: str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rob2 and not robins_i:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title("Risk of Bias Traffic-Light Summary")
        ax.text(0.5, 0.5, "No assessments available", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        return path

    total_rows = len(rob2) + len(robins_i)
    fig, ax = plt.subplots(figsize=(10, max(3, total_rows * 0.5)))
    row_idx = 0
    y_labels: list[str] = []
    rob2_domains = [
        "domain_1_randomization",
        "domain_2_deviations",
        "domain_3_missing_data",
        "domain_4_measurement",
        "domain_5_selection",
    ]
    robins_i_domains = [
        "domain_1_confounding",
        "domain_2_selection",
        "domain_3_classification",
        "domain_4_deviations",
        "domain_5_missing_data",
        "domain_6_measurement",
        "domain_7_reported_result",
    ]

    if rob2:
        for assessment in rob2:
            for col_idx, domain in enumerate(rob2_domains):
                judgment = getattr(assessment, domain)
                ax.scatter(
                    col_idx,
                    row_idx,
                    s=220,
                    c=_color_for_rob2(judgment),
                    marker="o",
                    edgecolors="black",
                )
            y_labels.append(f"{assessment.paper_id[:8]} (RoB2)")
            row_idx += 1

    if robins_i:
        x_offset = len(rob2_domains) + 1.5 if rob2 else 0
        for assessment in robins_i:
            for col_idx, domain in enumerate(robins_i_domains):
                judgment = getattr(assessment, domain)
                ax.scatter(
                    x_offset + col_idx,
                    row_idx,
                    s=220,
                    c=_color_for_robins_i(judgment),
                    marker="o",
                    edgecolors="black",
                )
            y_labels.append(f"{assessment.paper_id[:8]} (ROBINS-I)")
            row_idx += 1

    ax.set_yticks(range(total_rows))
    ax.set_yticklabels(y_labels, fontsize=8)
    ax.set_ylim(-0.6, total_rows - 0.4)

    if rob2 and robins_i:
        ax.axvline(x=len(rob2_domains) + 0.5, color="black", linestyle="-", linewidth=1)
        ax.set_xticks(
            list(range(len(rob2_domains))) + [len(rob2_domains) + 1.5 + i for i in range(len(robins_i_domains))]
        )
        ax.set_xticklabels(
            ["D1", "D2", "D3", "D4", "D5"] + ["D1", "D2", "D3", "D4", "D5", "D6", "D7"],
            fontsize=8,
        )
        ax.set_xlim(-0.6, len(rob2_domains) + 1.5 + len(robins_i_domains) - 0.4)
        ax.set_title("Risk of Bias Traffic-Light Summary (RoB 2 | ROBINS-I)")
    elif rob2:
        ax.set_xticks(range(len(rob2_domains)))
        ax.set_xticklabels(["D1", "D2", "D3", "D4", "D5"])
        ax.set_xlim(-0.6, len(rob2_domains) - 0.4)
        ax.set_title("RoB 2 Traffic-Light Summary")
    else:
        ax.set_xticks(range(len(robins_i_domains)))
        ax.set_xticklabels(["D1", "D2", "D3", "D4", "D5", "D6", "D7"])
        ax.set_xlim(-0.6, len(robins_i_domains) - 0.4)
        ax.set_title("ROBINS-I Traffic-Light Summary")

    ax.grid(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
