"""Screening heuristics shared across single and batch paths."""

from __future__ import annotations

from src.models import (
    CandidatePaper,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ScreeningDecision,
    ScreeningDecisionType,
    SettingsConfig,
)

PROTOCOL_TITLE_PATTERNS: tuple[str, ...] = (
    "protocol for",
    "protocol of",
    "study protocol",
    "trial protocol",
    "research protocol",
    "protocol paper",
    "protocol article",
    ": a protocol",
    "- a protocol",
    "design and methods",
    "study design and",
    "rationale and design",
    "prospero registration",
    "trial registration",
)

TITLE_ONLY_ABSTRACT_PHRASES: tuple[str, ...] = (
    "title only",
    "title-only",
    "[no abstract]",
    "no abstract available",
    "abstract not available",
    "abstract unavailable",
    "[abstract not available]",
)

DEFAULT_TITLE_ONLY_ABSTRACT_WORD_THRESHOLD = 5


def has_intervention_anchor_match(review: ReviewConfig, paper: CandidatePaper, full_text: str | None = None) -> bool:
    text_parts = [paper.title or "", paper.abstract or "", full_text or ""]
    haystack = " ".join(part for part in text_parts if part).lower()
    if not haystack.strip():
        return False
    anchor_terms = review.intervention_anchor_terms(limit=10)
    return any(term.strip().lower() in haystack for term in anchor_terms if term.strip())


def is_insufficient_content(settings: SettingsConfig, paper: CandidatePaper) -> bool:
    abstract = (paper.abstract or "").strip()
    title = (paper.title or "").strip()
    min_words = getattr(
        settings.screening,
        "insufficient_content_min_words",
        DEFAULT_TITLE_ONLY_ABSTRACT_WORD_THRESHOLD,
    )
    if not abstract:
        return min_words > 0
    if abstract.lower() == title.lower():
        return True
    abstract_lower = abstract.lower()
    if any(phrase in abstract_lower for phrase in TITLE_ONLY_ABSTRACT_PHRASES):
        return True
    return len(abstract.split()) < min_words


def is_protocol_only(paper: CandidatePaper) -> bool:
    title_lower = (paper.title or "").lower()
    abstract_lower = (paper.abstract or "").lower()
    if any(pattern in title_lower for pattern in PROTOCOL_TITLE_PATTERNS):
        return True
    no_results_phrases = (
        "no results are available",
        "results will be reported",
        "results are not yet available",
        "trial is ongoing",
        "study is ongoing",
        "data collection is underway",
        "data collection has not",
    )
    return any(phrase in abstract_lower for phrase in no_results_phrases)


def enforce_fulltext_exclusion_reason(decision: ScreeningDecision) -> ScreeningDecision:
    if decision.exclusion_reason is not None:
        return decision
    return decision.model_copy(update={"exclusion_reason": ExclusionReason.OTHER})


def no_fulltext_decision(paper_id: str) -> ScreeningDecision:
    return ScreeningDecision(
        paper_id=paper_id,
        decision=ScreeningDecisionType.EXCLUDE,
        confidence=1.0,
        reason="Full text not retrievable.",
        reviewer_type=ReviewerType.ADJUDICATOR,
        exclusion_reason=ExclusionReason.NO_FULL_TEXT,
    )
