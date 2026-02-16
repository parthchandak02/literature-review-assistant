"""Inter-rater reliability utilities for screening."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from sklearn.metrics import cohen_kappa_score

from src.db.repositories import WorkflowRepository
from src.models import DecisionLogEntry, DualScreeningResult, InterRaterReliability


def compute_cohens_kappa(results: Sequence[DualScreeningResult], stage: str) -> InterRaterReliability:
    if not results:
        return InterRaterReliability(
            stage=stage,
            total_screened=0,
            total_agreements=0,
            total_disagreements=0,
            cohens_kappa=0.0,
            percent_agreement=0.0,
        )
    reviewer_a = [item.reviewer_a.decision.value for item in results]
    reviewer_b = [item.reviewer_b.decision.value for item in results]
    agreements = sum(1 for a, b in zip(reviewer_a, reviewer_b) if a == b)
    total = len(results)
    kappa = float(cohen_kappa_score(reviewer_a, reviewer_b))
    return InterRaterReliability(
        stage=stage,
        total_screened=total,
        total_agreements=agreements,
        total_disagreements=total - agreements,
        cohens_kappa=kappa,
        percent_agreement=agreements / total,
    )


def generate_disagreements_report(output_path: str, results: Sequence[DualScreeningResult], stage: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Disagreements Report",
        "",
        f"Stage: {stage}",
        "",
    ]
    disagreements = [result for result in results if not result.agreement]
    if not disagreements:
        lines.append("No reviewer disagreements were detected.")
    else:
        for item in disagreements:
            lines.extend(
                [
                    f"## Paper {item.paper_id}",
                    f"- Reviewer A: {item.reviewer_a.decision.value} ({item.reviewer_a.reason or ''})",
                    f"- Reviewer B: {item.reviewer_b.decision.value} ({item.reviewer_b.reason or ''})",
                    f"- Final: {item.final_decision.value}",
                    "",
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def log_reliability_to_decision_log(
    repository: WorkflowRepository,
    reliability: InterRaterReliability,
) -> None:
    await repository.append_decision_log(
        DecisionLogEntry(
            decision_type="inter_rater_reliability",
            decision=f"kappa={reliability.cohens_kappa:.4f}",
            rationale=(
                f"stage={reliability.stage}, agreements={reliability.total_agreements}, "
                f"disagreements={reliability.total_disagreements}, "
                f"percent_agreement={reliability.percent_agreement:.4f}"
            ),
            actor="screening_reliability",
            phase="phase_3_screening",
        )
    )
