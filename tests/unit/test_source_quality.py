"""Unit tests for deterministic source-quality priors used in search and screening."""

from __future__ import annotations

import pytest

from src.models.papers import CandidatePaper
from src.search.source_quality import (
    apply_source_quality_prior,
    quality_priority_score,
    screening_quality_hint,
    source_quality_prior,
)


def _paper(**overrides: object) -> CandidatePaper:
    base: dict[str, object] = {
        "title": "Example study",
        "authors": ["A. Author"],
        "source_database": "openalex",
    }
    base.update(overrides)
    return CandidatePaper(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("pubmed", ("high", True, True)),
        ("PubMed", ("high", True, True)),
        ("  SCOPUS ", ("high", True, False)),
        ("arxiv", ("medium", False, True)),
        ("perplexity_search", ("low", False, True)),
        ("wos", ("high", True, False)),
        ("clinicaltrials", ("medium", False, True)),
        ("clinicaltrials_gov", ("medium", False, True)),
        ("mystery_db", ("unknown", False, True)),
        ("", ("unknown", False, True)),
    ],
)
def test_source_quality_prior_aliases_and_defaults(source: str, expected: tuple[str, bool, bool]) -> None:
    assert source_quality_prior(source) == expected


def test_apply_source_quality_prior_fills_missing_fields() -> None:
    paper = _paper(source_database="pubmed")
    filled = apply_source_quality_prior(paper)
    assert filled is not paper
    assert filled.source_quality_tier == "high"
    assert filled.source_peer_reviewed is True
    assert filled.source_open_index is True


def test_apply_source_quality_prior_preserves_fully_set_fields() -> None:
    paper = _paper(
        source_database="arxiv",
        source_quality_tier="custom",
        source_peer_reviewed=True,
        source_open_index=False,
    )
    filled = apply_source_quality_prior(paper)
    assert filled is paper
    assert filled.source_quality_tier == "custom"
    assert filled.source_peer_reviewed is True
    assert filled.source_open_index is False


def test_apply_source_quality_prior_fills_only_unset_fields() -> None:
    paper = _paper(
        source_database="scopus",
        source_quality_tier="already_set",
        source_peer_reviewed=None,
        source_open_index=None,
    )
    filled = apply_source_quality_prior(paper)
    assert filled.source_quality_tier == "already_set"
    assert filled.source_peer_reviewed is True
    assert filled.source_open_index is False


def test_screening_quality_hint_describes_peer_and_openness() -> None:
    peer_hint = screening_quality_hint(_paper(source_database="pubmed"))
    assert peer_hint == ("Source prior: pubmed (high quality tier; peer-reviewed index likely; open index).")

    mixed_hint = screening_quality_hint(_paper(source_database="arxiv"))
    assert mixed_hint == ("Source prior: arxiv (medium quality tier; non-peer-reviewed or mixed source; open index).")

    licensed_hint = screening_quality_hint(_paper(source_database="scopus"))
    assert "licensed index" in licensed_hint
    assert "high quality tier" in licensed_hint


def test_quality_priority_score_ranks_known_sources() -> None:
    # Default: high+peer+open=1.3, high+peer=1.2, medium+peer+open=1.0,
    # medium+open=0.8, low+open=0.5, unknown+open=0.6
    assert quality_priority_score("pubmed") == pytest.approx(1.3)
    assert quality_priority_score("scopus") == pytest.approx(1.2)
    assert quality_priority_score("openalex") == pytest.approx(1.0)
    assert quality_priority_score("arxiv") == pytest.approx(0.8)
    assert quality_priority_score("perplexity_search") == pytest.approx(0.5)
    assert quality_priority_score("unknown_source") == pytest.approx(0.6)

    assert quality_priority_score("pubmed") > quality_priority_score("openalex")
    assert quality_priority_score("openalex") > quality_priority_score("arxiv")
    assert quality_priority_score("arxiv") > quality_priority_score("perplexity_search")


def test_quality_priority_score_respects_custom_weights_and_bonuses() -> None:
    score = quality_priority_score(
        "pubmed",
        tier_weights={"high": 2.0, "unknown": 0.0},
        peer_review_bonus=0.5,
        open_index_bonus=0.25,
    )
    assert score == pytest.approx(2.75)
