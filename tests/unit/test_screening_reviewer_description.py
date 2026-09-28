"""Screening reviewer descriptions must match the actual screening setup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.manuscript.prisma_disclosure import _methodological_prisma_gaps
from src.writing.context_builder import _build_screening_method_description
from src.writing.section_fallbacks import build_empty_section_placeholder


def _d(actor: str) -> SimpleNamespace:
    return SimpleNamespace(actor=actor, phase="phase_3_screening")


def _describe(decisions: list[SimpleNamespace], **kwargs) -> str:
    return _build_screening_method_description(decisions, 100, cohens_kappa=kwargs.pop("kappa", 0.7), **kwargs)


def test_dual_review_is_labelled_automated() -> None:
    text = _describe([_d("reviewer_a")] * 10 + [_d("reviewer_b")] * 10 + [_d("adjudicator")])
    assert "two independent automated reviewers" in text
    assert "automated adjudication" in text
    assert "Cohen's kappa" in text
    assert "human" not in text.lower()
    assert "llm" not in text.lower()
    assert "language model" not in text.lower()


def test_fast_path_review_discloses_partial_second_review() -> None:
    text = _describe([_d("reviewer_a")] * 10 + [_d("reviewer_b")] * 3)
    assert "a primary automated reviewer, with a second reviewer when confidence was low" in text
    assert "Two independent" not in text


def test_single_review_does_not_claim_dual_or_kappa() -> None:
    text = _describe([_d("reviewer_a")] * 10)
    assert "a single automated reviewer" in text
    assert "two independent" not in text.lower()
    assert "adjudicat" not in text
    assert "Cohen's kappa" not in text
    assert "one reviewer" in text


def test_human_override_is_disclosed() -> None:
    text = _describe([_d("reviewer_a")] * 5 + [_d("reviewer_b")] * 5 + [_d("human_override")])
    assert "A human reviewer checked and could override screening decisions." in text


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"batch_screen_forwarded": 20, "batch_screen_excluded": 5},
    ],
)
def test_no_description_claims_unqualified_human_reviewers(kwargs: dict) -> None:
    decisions = [_d("keyword_filter")] * 50 + [_d("reviewer_a")] * 10 + [_d("reviewer_b")] * 10
    text = _describe(decisions, **kwargs)
    assert "Two independent reviewers" not in text
    assert "third reviewer" not in text
    assert "automated reviewer" in text


def test_automated_reviewer_wording_satisfies_prisma_selection_disclosure() -> None:
    text = _describe([_d("reviewer_a")] * 10).lower()
    assert "selection_process_independent_reviewers" not in _methodological_prisma_gaps(text)


def test_methods_placeholder_uses_run_screening_description() -> None:
    grounding = SimpleNamespace(
        screening_method_description="Titles and abstracts were screened by a single automated reviewer."
    )
    text = build_empty_section_placeholder(
        "methods", research_question="Q?", prisma_sentence="Of 5 reports...", grounding=grounding
    )
    assert text == ("Titles and abstracts were screened by a single automated reviewer. Of 5 reports...")


def test_methods_placeholder_without_grounding_is_neutral() -> None:
    text = build_empty_section_placeholder("methods", research_question="Q?", prisma_sentence="")
    assert text == "Records were screened against the predefined eligibility criteria."
    assert "independent" not in (text or "")
