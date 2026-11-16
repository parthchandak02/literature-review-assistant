"""Unit tests for adaptive screening threshold calibration (Enhancement #9)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.models import CandidatePaper, ReviewerType, ScreeningDecision, ScreeningDecisionType
from src.models.screening import DualScreeningResult
from src.screening.reliability import CalibratedThresholds, calibrate_threshold, compute_cohens_kappa


def _make_paper(paper_id: str) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Study {paper_id}",
        authors=["Author A"],
        source_database="openalex",
    )


def _make_result(
    paper_id: str, decision_a: ScreeningDecisionType, decision_b: ScreeningDecisionType
) -> DualScreeningResult:
    return DualScreeningResult(
        paper_id=paper_id,
        reviewer_a=ScreeningDecision(
            paper_id=paper_id,
            decision=decision_a,
            reviewer_type=ReviewerType.REVIEWER_A,
            confidence=0.9,
        ),
        reviewer_b=ScreeningDecision(
            paper_id=paper_id,
            decision=decision_b,
            reviewer_type=ReviewerType.REVIEWER_B,
            confidence=0.8,
        ),
        agreement=decision_a == decision_b,
        final_decision=decision_a,
    )


def _perfect_agreement_results(papers):
    """Mixed include/exclude but both reviewers always agree -> kappa=1.0."""
    results = []
    for i, p in enumerate(papers):
        dec = ScreeningDecisionType.INCLUDE if i % 2 == 0 else ScreeningDecisionType.EXCLUDE
        results.append(_make_result(p.paper_id, dec, dec))
    return results


def _total_disagreement_results(papers):
    """Reviewers always disagree -> kappa near 0."""
    results = []
    for i, p in enumerate(papers):
        a = ScreeningDecisionType.INCLUDE if i % 2 == 0 else ScreeningDecisionType.EXCLUDE
        b = ScreeningDecisionType.EXCLUDE if i % 2 == 0 else ScreeningDecisionType.INCLUDE
        results.append(_make_result(p.paper_id, a, b))
    return results


def test_calibrated_thresholds_dataclass():
    ct = CalibratedThresholds(
        include_threshold=0.85,
        exclude_threshold=0.80,
        achieved_kappa=0.75,
        iterations=2,
        sample_size=30,
    )
    assert ct.include_threshold == 0.85
    assert ct.exclude_threshold == 0.80
    assert ct.achieved_kappa == 0.75
    assert ct.iterations == 2
    assert ct.sample_size == 30


@pytest.mark.asyncio
async def test_calibrate_returns_best_threshold_when_target_met_immediately():
    """Perfect agreement on first attempt -> stops after 1 iteration."""
    papers = [_make_paper(f"p{i}") for i in range(10)]
    high_kappa_results = _perfect_agreement_results(papers)

    screener_fn = AsyncMock(return_value=high_kappa_results)
    result = await calibrate_threshold(
        papers=papers,
        screener_fn=screener_fn,
        target_kappa=0.7,
        max_iterations=5,
        sample_size=10,
        initial_include_threshold=0.85,
    )
    # Target kappa is met immediately -> should not run max_iterations.
    assert screener_fn.call_count == 1
    assert result.include_threshold == 0.85
    assert result.achieved_kappa >= 0.7


@pytest.mark.asyncio
async def test_calibrate_runs_all_iterations_when_kappa_never_improves():
    """Total disagreement -> runs all max_iterations without stopping early."""
    papers = [_make_paper(f"p{i}") for i in range(10)]
    low_kappa_results = _total_disagreement_results(papers)

    screener_fn = AsyncMock(return_value=low_kappa_results)
    result = await calibrate_threshold(
        papers=papers,
        screener_fn=screener_fn,
        target_kappa=0.99,  # impossible -> runs all iterations
        max_iterations=3,
        sample_size=10,
        initial_include_threshold=0.85,
    )
    assert screener_fn.call_count == 3
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_calibrate_bisection_lowers_current_threshold():
    """Bisection should pass progressively lower thresholds to the screener_fn."""
    papers = [_make_paper(f"p{i}") for i in range(10)]
    low_kappa_results = _total_disagreement_results(papers)

    thresholds_seen = []

    async def _capturing_screener(sample, threshold):
        thresholds_seen.append(threshold)
        return low_kappa_results

    result = await calibrate_threshold(
        papers=papers,
        screener_fn=_capturing_screener,
        target_kappa=0.99,
        max_iterations=3,
        sample_size=10,
        initial_include_threshold=0.85,
    )
    # The bisection should lower the threshold on each failed iteration.
    assert thresholds_seen[0] == 0.85, "First call should use initial threshold"
    assert thresholds_seen[1] < thresholds_seen[0], "Second call should use a lower threshold"


@pytest.mark.asyncio
async def test_calibrate_handles_empty_screener_result():
    """Empty screener result -> no crash, returns initial threshold unchanged."""
    papers = [_make_paper("p1"), _make_paper("p2")]
    screener_fn = AsyncMock(return_value=[])
    result = await calibrate_threshold(
        papers=papers,
        screener_fn=screener_fn,
        target_kappa=0.7,
        max_iterations=2,
        sample_size=2,
        initial_include_threshold=0.80,
    )
    assert result.include_threshold == 0.80
    assert result.exclude_threshold >= 0.0


@pytest.mark.asyncio
async def test_calibrate_sample_is_capped_at_paper_count():
    """Requesting 30 samples from 5 papers -> sample_size reported as 5."""
    papers = [_make_paper(f"p{i}") for i in range(5)]
    all_results = _perfect_agreement_results(papers)
    screener_fn = AsyncMock(return_value=all_results)
    result = await calibrate_threshold(
        papers=papers,
        screener_fn=screener_fn,
        target_kappa=0.7,
        max_iterations=1,
        sample_size=30,
        initial_include_threshold=0.85,
    )
    assert result.sample_size == 5


@pytest.mark.asyncio
async def test_calibrate_exclude_is_never_negative():
    """Very low initial threshold -> exclude_threshold must be >= 0.0."""
    papers = [_make_paper("p1"), _make_paper("p2")]
    screener_fn = AsyncMock(return_value=_perfect_agreement_results(papers))
    result = await calibrate_threshold(
        papers=papers,
        screener_fn=screener_fn,
        target_kappa=0.7,
        max_iterations=1,
        sample_size=2,
        initial_include_threshold=0.02,
    )
    assert result.exclude_threshold >= 0.0


def _balanced_disagreement(papers, agreements: set[int]) -> list[DualScreeningResult]:
    """Balanced include/exclude labels. `agreements` indexes the papers where reviewers match."""
    results = []
    for i, paper in enumerate(papers):
        decision_a = ScreeningDecisionType.INCLUDE if i < len(papers) / 2 else ScreeningDecisionType.EXCLUDE
        if i in agreements:
            decision_b = decision_a
        else:
            decision_b = (
                ScreeningDecisionType.EXCLUDE
                if decision_a is ScreeningDecisionType.INCLUDE
                else ScreeningDecisionType.INCLUDE
            )
        results.append(_make_result(paper.paper_id, decision_a, decision_b))
    return results


@pytest.mark.asyncio
async def test_calibrate_keeps_best_negative_kappa():
    """A kappa below zero is a real score and must be able to win.

    The search used to seed the best score at 0, so every negative kappa was
    discarded. The run then reported kappa 0 and kept the initial threshold
    even when a later threshold agreed more.
    """
    papers = [_make_paper(f"p{i}") for i in range(6)]
    worse = _balanced_disagreement(papers, agreements=set())
    better = _balanced_disagreement(papers, agreements={2, 4})
    worse_kappa = compute_cohens_kappa(worse, stage="calibration").cohens_kappa
    better_kappa = compute_cohens_kappa(better, stage="calibration").cohens_kappa
    assert worse_kappa < better_kappa < 0

    observed: list[tuple[float, float]] = []

    async def _screener(sample, threshold):
        batch = worse if not observed else better
        observed.append((threshold, compute_cohens_kappa(batch, stage="calibration").cohens_kappa))
        return batch

    result = await calibrate_threshold(
        papers=papers,
        screener_fn=_screener,
        target_kappa=0.7,
        max_iterations=3,
        sample_size=6,
        initial_include_threshold=0.85,
    )

    best_threshold, best_kappa = max(observed, key=lambda item: item[1])
    assert result.achieved_kappa == round(best_kappa, 4)
    assert result.include_threshold == round(best_threshold, 3)
    assert result.achieved_kappa < 0
    assert result.include_threshold != 0.85
