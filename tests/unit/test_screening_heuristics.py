"""Decision rules that auto-exclude papers before any screening LLM call."""

from __future__ import annotations

import pytest

from src.models import (
    CandidatePaper,
    DomainExpertConfig,
    ExclusionReason,
    ReviewConfig,
    ReviewerType,
    ReviewType,
    ScreeningDecision,
    ScreeningDecisionType,
    SettingsConfig,
)
from src.models.config import ScreeningConfig
from src.screening.heuristics import (
    PROTOCOL_TITLE_PATTERNS,
    TITLE_ONLY_ABSTRACT_PHRASES,
    enforce_fulltext_exclusion_reason,
    has_intervention_anchor_match,
    is_insufficient_content,
    is_protocol_only,
    no_fulltext_decision,
)

_ABSTRACT_NO_RESULTS_PHRASES = (
    "no results are available",
    "results will be reported",
    "results are not yet available",
    "trial is ongoing",
    "study is ongoing",
    "data collection is underway",
    "data collection has not",
)


def _paper(**overrides: object) -> CandidatePaper:
    fields: dict[str, object] = {
        "paper_id": "p-1",
        "title": "Effects of a classroom intervention on a learning endpoint",
        "authors": ["Ada Lovelace"],
        "source_database": "openalex",
        "abstract": "Background and methods. Participants were enrolled and the primary endpoint was measured.",
    }
    fields.update(overrides)
    return CandidatePaper(**fields)  # type: ignore[arg-type]


def _review(**overrides: object) -> ReviewConfig:
    fields: dict[str, object] = {
        "research_question": "Does the intervention improve the endpoint?",
        "review_type": ReviewType.SYSTEMATIC,
        "pico": {
            "population": "undergraduate students",
            "intervention": "ai tutoring",
            "comparison": "lecture",
            "outcome": "exam scores",
        },
        "keywords": ["simulation"],
        "domain": "education",
        "scope": "undergraduate training",
        "inclusion_criteria": ["primary empirical studies"],
        "exclusion_criteria": ["protocol only records"],
        "date_range_start": 2015,
        "date_range_end": 2026,
        "target_databases": ["openalex"],
    }
    fields.update(overrides)
    return ReviewConfig(**fields)  # type: ignore[arg-type]


def _settings(min_words: int) -> SettingsConfig:
    return SettingsConfig(
        agents={"screening_reviewer_a": {"model": "google:gemini-2.5-flash", "temperature": 0.1}},
        screening=ScreeningConfig(insufficient_content_min_words=min_words),
    )


def _exclude(reason: ExclusionReason | None = None) -> ScreeningDecision:
    return ScreeningDecision(
        paper_id="p-1",
        decision=ScreeningDecisionType.EXCLUDE,
        reviewer_type=ReviewerType.REVIEWER_A,
        confidence=0.91,
        exclusion_reason=reason,
    )


@pytest.mark.parametrize("pattern", PROTOCOL_TITLE_PATTERNS)
def test_protocol_title_markers_auto_exclude(pattern: str) -> None:
    paper = _paper(title=f"Preliminary report {pattern} for a learning trial", abstract="Planned analyses only.")
    assert is_protocol_only(paper) is True


@pytest.mark.parametrize("phrase", _ABSTRACT_NO_RESULTS_PHRASES)
def test_protocol_abstract_no_results_phrases_auto_exclude(phrase: str) -> None:
    paper = _paper(abstract=f"Methods are described. {phrase.capitalize()} after recruitment finishes.")
    assert is_protocol_only(paper) is True


def test_completed_empirical_paper_is_not_protocol_only() -> None:
    paper = _paper(
        title="Randomized trial of a classroom intervention",
        abstract="We enrolled 120 participants. The primary endpoint improved by 12 points.",
    )
    assert is_protocol_only(paper) is False


def test_protocol_word_alone_does_not_exclude() -> None:
    paper = _paper(title="Network protocol latency in classroom software", abstract="Measured round trip time.")
    assert is_protocol_only(paper) is False


def test_protocol_markers_are_case_insensitive_and_title_only() -> None:
    assert is_protocol_only(_paper(title="STUDY PROTOCOL for a tutoring trial")) is True
    # Abstract mentions a protocol, but title markers are not applied to the abstract.
    kept = _paper(
        title="Effects of a classroom intervention",
        abstract="This manuscript is a study protocol with a registered analysis plan.",
    )
    assert is_protocol_only(kept) is False


def test_ongoing_trial_phrase_in_the_title_does_not_count_as_protocol_only() -> None:
    paper = _paper(
        title="Trial is ongoing",
        abstract="Final outcomes from 200 participants are reported in the results.",
    )
    assert is_protocol_only(paper) is False


def test_empty_record_is_not_protocol_only() -> None:
    assert is_protocol_only(_paper(title="   ", abstract=None)) is False
    assert is_protocol_only(_paper(title="   ", abstract="   ")) is False


@pytest.mark.parametrize(
    ("abstract", "min_words", "expected"),
    [
        (None, 5, True),
        ("", 5, True),
        ("   ", 5, True),
        (None, 0, False),
        ("one two three four", 5, True),
        ("one two three four five", 5, False),
        ("one two", 0, False),
    ],
)
def test_insufficient_content_word_threshold(abstract: str | None, min_words: int, expected: bool) -> None:
    paper = _paper(title="Distinct title", abstract=abstract)
    assert is_insufficient_content(_settings(min_words), paper) is expected


def test_abstract_that_repeats_the_title_is_insufficient_even_when_long() -> None:
    title = "Effects of a classroom intervention on a learning endpoint"
    paper = _paper(title=title, abstract=title.upper())
    assert is_insufficient_content(_settings(0), paper) is True


@pytest.mark.parametrize("phrase", TITLE_ONLY_ABSTRACT_PHRASES)
def test_explicit_no_abstract_markers_exclude_even_when_threshold_is_disabled(phrase: str) -> None:
    filler = "word " * 40
    paper = _paper(title="Distinct title", abstract=f"{filler}{phrase}{filler}")
    assert is_insufficient_content(_settings(0), paper) is True


def test_usable_abstract_is_not_insufficient() -> None:
    paper = _paper(abstract="We enrolled 80 students and measured exam performance after eight weeks of instruction.")
    assert is_insufficient_content(_settings(5), paper) is False


def test_anchor_match_checks_title_abstract_and_full_text_only() -> None:
    review = _review()
    assert has_intervention_anchor_match(review, _paper(title="AI tutoring in lectures")) is True
    assert has_intervention_anchor_match(review, _paper(abstract="Students used AI tutoring twice a week.")) is True
    body_only = _paper()
    assert has_intervention_anchor_match(review, body_only, "Daily AI tutoring sessions.") is True
    assert has_intervention_anchor_match(review, body_only, None) is False
    assert has_intervention_anchor_match(review, body_only, "   ") is False
    keyword_only = _paper(keywords=["ai tutoring"])
    assert has_intervention_anchor_match(review, keyword_only) is False


def test_anchor_match_ignores_blank_records_and_blank_terms() -> None:
    review = _review(domain_expert=DomainExpertConfig(canonical_terms=["  ", "a"]))
    assert has_intervention_anchor_match(review, _paper(title="   ", abstract=None)) is False


def test_anchor_match_stops_after_ten_terms() -> None:
    canonical = [f"canon {i}" for i in range(10)]
    review = _review(domain_expert=DomainExpertConfig(canonical_terms=canonical))
    assert "ai tutoring" not in [term.casefold() for term in review.intervention_anchor_terms(limit=10)]
    assert has_intervention_anchor_match(review, _paper(title="AI tutoring trial")) is False
    assert has_intervention_anchor_match(review, _paper(title="Canon 3 trial")) is True


def test_anchor_match_falls_back_when_intervention_terms_are_unusable() -> None:
    review = _review(
        pico={
            "population": "students",
            "intervention": "x",
            "comparison": "lecture",
            "outcome": "scores",
        },
        keywords=["simulation"],
    )
    assert has_intervention_anchor_match(review, _paper(title="Simulation lab outcomes")) is True
    assert has_intervention_anchor_match(review, _paper(title="Unrelated laboratory course")) is False


def test_fulltext_exclusion_without_a_reason_becomes_other() -> None:
    original = _exclude()
    filled = enforce_fulltext_exclusion_reason(original)
    assert filled.exclusion_reason == ExclusionReason.OTHER
    assert filled.decision == ScreeningDecisionType.EXCLUDE
    assert original.exclusion_reason is None
    kept = _exclude(ExclusionReason.WRONG_OUTCOME)
    assert enforce_fulltext_exclusion_reason(kept) is kept


def test_no_fulltext_decision_is_a_certain_adjudicator_exclusion() -> None:
    decision = no_fulltext_decision("paper-9")
    assert decision.paper_id == "paper-9"
    assert decision.decision == ScreeningDecisionType.EXCLUDE
    assert decision.confidence == 1.0
    assert decision.reviewer_type == ReviewerType.ADJUDICATOR
    assert decision.exclusion_reason == ExclusionReason.NO_FULL_TEXT
    assert decision.reason == "Full text not retrievable."
