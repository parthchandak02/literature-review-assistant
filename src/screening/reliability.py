"""Inter-rater reliability utilities for screening."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from sklearn.metrics import cohen_kappa_score

from src.db.repositories import WorkflowRepository
from src.models import DecisionLogEntry, DualScreeningResult, InterRaterReliability

if TYPE_CHECKING:
    from src.models import CandidatePaper

logger = logging.getLogger(__name__)


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


@dataclass
class CalibratedThresholds:
    """Result of threshold calibration: adjusted include/exclude thresholds."""

    include_threshold: float
    exclude_threshold: float
    achieved_kappa: float
    iterations: int
    sample_size: int


async def calibrate_threshold(
    papers: "list[CandidatePaper]",
    screener_fn: Callable[["list[CandidatePaper]", float], "Sequence[DualScreeningResult]"],
    target_kappa: float = 0.7,
    max_iterations: int = 3,
    sample_size: int = 30,
    initial_include_threshold: float = 0.85,
) -> CalibratedThresholds:
    """Calibrate the screening inclusion threshold via bisection on a paper sample.

    Screens a random subset of `sample_size` papers at progressively adjusted
    thresholds until Cohen's kappa >= `target_kappa` or `max_iterations` are
    exhausted. The exclude_threshold is kept 0.05 below include_threshold.

    Args:
        papers: Full candidate paper list; a random sample is drawn from these.
        screener_fn: Async callable(papers, threshold) -> list[DualScreeningResult].
            The caller should partially apply the screener with its workflow_id etc.
        target_kappa: Minimum acceptable kappa (default 0.7).
        max_iterations: Maximum bisection rounds (default 3).
        sample_size: Number of papers to screen per calibration round.
        initial_include_threshold: Starting threshold for bisection.

    Returns:
        CalibratedThresholds with the best threshold found.
    """
    sample = random.sample(papers, min(sample_size, len(papers)))
    lo, hi = 0.5, 0.95
    current = initial_include_threshold
    best_kappa = 0.0
    best_threshold = current

    for iteration in range(1, max_iterations + 1):
        results: Sequence[DualScreeningResult] = await screener_fn(sample, current)  # type: ignore[arg-type]

        if not results:
            logger.warning("calibrate_threshold: screener returned no results (iteration %d)", iteration)
            break

        reliability = compute_cohens_kappa(list(results), stage="calibration")
        kappa = reliability.cohens_kappa
        logger.info(
            "calibrate_threshold iter=%d threshold=%.3f kappa=%.4f (target=%.2f)",
            iteration, current, kappa, target_kappa,
        )

        if kappa > best_kappa:
            best_kappa = kappa
            best_threshold = current

        if kappa >= target_kappa:
            break

        # Bisect: if kappa is too low, widen the uncertain band (lower threshold).
        # Lower threshold -> more papers reviewed -> higher reviewer agreement on clear cases.
        hi = current
        current = (lo + hi) / 2.0

    exclude = max(0.0, best_threshold - 0.05)
    result = CalibratedThresholds(
        include_threshold=round(best_threshold, 3),
        exclude_threshold=round(exclude, 3),
        achieved_kappa=round(best_kappa, 4),
        iterations=min(max_iterations, iteration),
        sample_size=len(sample),
    )
    logger.info(
        "calibrate_threshold: final include=%.3f exclude=%.3f kappa=%.4f after %d iter",
        result.include_threshold, result.exclude_threshold,
        result.achieved_kappa, result.iterations,
    )
    return result


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
