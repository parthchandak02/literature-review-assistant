"""Non-LLM keyword pre-filter for title/abstract screening.

Papers that match fewer than `screening.keyword_filter_min_matches` terms from
the review config keywords + PICO intervention are auto-excluded before any LLM
call is made. This typically reduces LLM screening cost by 80-90% for broad
database queries.
"""

from __future__ import annotations

from src.models.config import ReviewConfig, ScreeningConfig
from src.models.enums import ExclusionReason, ReviewerType, ScreeningDecisionType
from src.models.papers import CandidatePaper
from src.models.screening import ScreeningDecision


def keyword_prefilter(
    papers: list[CandidatePaper],
    config: ReviewConfig,
    screening: ScreeningConfig,
) -> tuple[list[ScreeningDecision], list[CandidatePaper]]:
    """Score each paper against intervention keywords from the review config.

    Returns (auto_excluded_decisions, papers_needing_llm_review). Papers with
    fewer than screening.keyword_filter_min_matches keyword hits are
    auto-excluded (no LLM call). When min_matches == 0 the pre-filter is
    disabled and all papers are forwarded to LLM screening.
    """
    min_matches = screening.keyword_filter_min_matches
    if min_matches <= 0:
        return [], list(papers)

    terms = [t.lower() for t in (config.keywords or []) + [config.pico.intervention]]
    if not terms:
        return [], list(papers)

    auto_excluded: list[ScreeningDecision] = []
    for_llm: list[CandidatePaper] = []

    for paper in papers:
        text = f"{paper.title or ''} {paper.abstract or ''}".lower()
        matches = sum(1 for term in terms if term in text)
        if matches >= min_matches:
            for_llm.append(paper)
        else:
            auto_excluded.append(
                ScreeningDecision(
                    paper_id=paper.paper_id,
                    decision=ScreeningDecisionType.EXCLUDE,
                    confidence=1.0,
                    reason=(
                        f"Keyword pre-filter: matched {matches}/{len(terms)} "
                        f"intervention terms in title/abstract."
                    ),
                    exclusion_reason=ExclusionReason.KEYWORD_FILTER,
                    reviewer_type=ReviewerType.KEYWORD_FILTER,
                )
            )

    return auto_excluded, for_llm
