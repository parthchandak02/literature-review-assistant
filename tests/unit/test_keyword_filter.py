from __future__ import annotations

from src.models import ReviewConfig, ReviewType
from src.models.config import ScreeningConfig
from src.models.enums import ExclusionReason
from src.models.papers import CandidatePaper
from src.screening.keyword_filter import keyword_prefilter


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does intervention improve outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "undergraduate medical students",
            "intervention": "ai tutoring",
            "comparison": "traditional teaching",
            "outcome": "exam scores",
        },
        keywords=["ai tutoring", "simulation", "medical education"],
        domain="medical education",
        scope="medical education",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews", "protocol-only"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _paper(title: str, abstract: str) -> CandidatePaper:
    return CandidatePaper(
        title=title,
        abstract=abstract,
        authors=["A. Author"],
        source_database="openalex",
    )


def test_keyword_prefilter_excludes_empty_abstract_when_enabled() -> None:
    cfg = ScreeningConfig(keyword_filter_min_matches=0, auto_exclude_empty_abstract=True)
    papers = [_paper("AI tutoring in medicine", "")]
    excluded, forwarded = keyword_prefilter(papers, _review(), cfg)
    assert len(excluded) == 1
    assert len(forwarded) == 0
    assert excluded[0].exclusion_reason == ExclusionReason.INSUFFICIENT_DATA


def test_keyword_prefilter_secondary_review_marker_excluded() -> None:
    cfg = ScreeningConfig(keyword_filter_min_matches=0)
    papers = [_paper("A systematic review of AI tutors", "Systematic review of prior studies.")]
    excluded, forwarded = keyword_prefilter(papers, _review(), cfg)
    assert len(excluded) == 1
    assert len(forwarded) == 0
    assert excluded[0].exclusion_reason == ExclusionReason.WRONG_STUDY_DESIGN


def test_keyword_prefilter_protocol_marker_excluded() -> None:
    cfg = ScreeningConfig(keyword_filter_min_matches=0)
    papers = [_paper("Protocol for randomized AI tutoring trial", "Study protocol and trial registration.")]
    excluded, forwarded = keyword_prefilter(papers, _review(), cfg)
    assert len(excluded) == 1
    assert len(forwarded) == 0
    assert excluded[0].exclusion_reason == ExclusionReason.PROTOCOL_ONLY


def test_keyword_prefilter_allowlist_bypasses_deterministic_marker() -> None:
    cfg = ScreeningConfig(
        keyword_filter_min_matches=0,
        deterministic_allowlist_patterns=["journal of narrative review studies"],
    )
    papers = [
        _paper(
            "Randomized trial in Journal of Narrative Review Studies",
            "Primary trial in undergraduate medical students.",
        )
    ]
    excluded, forwarded = keyword_prefilter(papers, _review(), cfg)
    assert len(excluded) == 0
    assert len(forwarded) == 1


def test_keyword_prefilter_empty_abstract_rescue_for_title_match() -> None:
    cfg = ScreeningConfig(
        keyword_filter_min_matches=0,
        auto_exclude_empty_abstract=True,
        empty_abstract_rescue_sample_size=1,
        empty_abstract_rescue_keyword_min_matches=2,
    )
    papers = [_paper("AI tutoring simulation for medical education", "")]
    excluded, forwarded = keyword_prefilter(papers, _review(), cfg)
    assert len(excluded) == 0
    assert len(forwarded) == 1
