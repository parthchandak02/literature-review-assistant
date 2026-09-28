"""Template (fallback) abstract: objective phrasing, punctuation, and run-data grounding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.models.enums import ReviewType
from src.writing.abstract_utils import (
    _ensure_structured_abstract,
    parse_structured_abstract_markdown,
    question_to_objective_phrase,
    review_objective_phrase,
)
from src.writing.section_fallbacks import build_empty_section_placeholder, resolve_section_manifest_outcome

_QUESTION = (
    "What are the multi-dimensional impacts of pickleball participation on physical, "
    "psychological, and social outcomes among adult populations?"
)
_PRISMA = (
    "Of the 57 reports sought for retrieval, 50 were not retrieved and 7 were assessed for eligibility, "
    "with 6 studies ultimately included."
)
_BANNED = (
    "configured protocol and settings",
    "for the topic",
    "Evidence synthesis was generated from included studies",
    "?.",
    "evaluated What",
    "review question: What",
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (_QUESTION, _QUESTION[len("What are ") :].rstrip("?")),
        ("What is the effectiveness of CBT for insomnia?", "the effectiveness of CBT for insomnia"),
        ("what are barriers to telehealth adoption", "barriers to telehealth adoption"),
        (
            "What factors influence vaccine uptake in adolescents?",
            "the factors that influence vaccine uptake in adolescents",
        ),
        ("Which interventions reduce falls in care homes?", "the interventions that reduce falls in care homes"),
        ("What is known about AI scribes in primary care?", "current evidence on AI scribes in primary care"),
        (
            "What are the effects of X on Y, and how do they vary by age?",
            "the effects of X on Y",
        ),
    ],
)
def test_question_to_objective_phrase(question: str, expected: str) -> None:
    assert question_to_objective_phrase(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "How does exercise affect mood?",
        "Does pickleball improve balance?",
        "What role does sleep play in recovery?",
        "What proportion of adults play pickleball?",
        "",
    ],
)
def test_question_to_objective_phrase_declines_unsafe_rewrites(question: str) -> None:
    assert question_to_objective_phrase(question) is None


def test_review_objective_phrase_falls_back_to_pico() -> None:
    pico = SimpleNamespace(population="older adults", intervention="pickleball", outcome="balance")
    assert review_objective_phrase("Does pickleball improve balance?", pico) == (
        "the effects of pickleball on balance in older adults"
    )


def test_review_objective_phrase_quotes_question_without_trailing_question_mark() -> None:
    phrase = review_objective_phrase("How does exercise affect mood?")
    assert phrase == 'the research question "How does exercise affect mood"'


def _review(review_type: ReviewType = ReviewType.SYSTEMATIC) -> SimpleNamespace:
    return SimpleNamespace(
        research_question=_QUESTION,
        review_type=review_type,
        pico=SimpleNamespace(population="adults", intervention="pickleball", outcome="wellbeing"),
        keywords=["pickleball", "mental health", "older adults"],
        date_range_start=2010,
        date_range_end=2025,
    )


def _grounding() -> SimpleNamespace:
    return SimpleNamespace(
        databases_searched=["PubMed", "Scopus", "OpenAlex"],
        search_date="2026-09-20",
        screening_method_description="",
        study_design_counts={"cross_sectional": 4, "rct": 2},
        total_included=6,
        synthesis_direction="mixed",
    )


def test_template_abstract_uses_run_data_and_has_no_leakage() -> None:
    text = build_empty_section_placeholder(
        "abstract",
        research_question=_QUESTION,
        prisma_sentence=_PRISMA,
        review=_review(),
        grounding=_grounding(),
    )
    assert text is not None
    for banned in _BANNED:
        assert banned not in text
    assert "PubMed, Scopus, and OpenAlex were searched on 2026-09-20" in text
    assert "between 2010 and 2025" in text
    assert "the multi-dimensional impacts of pickleball participation" in text
    assert _PRISMA in text
    assert "cross sectional (n=4) and rct (n=2)." in text
    assert "Across the 6 included studies, the overall direction of evidence was mixed" in text
    assert "**Keywords:** pickleball, mental health, older adults." in text

    parsed = parse_structured_abstract_markdown(text)
    assert parsed.objectives.startswith("To identify, appraise, and synthesize studies on the multi-dimensional")
    for field in (parsed.background, parsed.objectives, parsed.methods, parsed.results, parsed.conclusions):
        assert field.endswith(".")
        assert not field.endswith("?.")


def test_template_abstract_labels_scoping_review() -> None:
    text = build_empty_section_placeholder(
        "abstract",
        research_question=_QUESTION,
        prisma_sentence=_PRISMA,
        review=_review(ReviewType.SCOPING),
        grounding=_grounding(),
    )
    assert text is not None
    assert "This scoping review" in text
    assert "To map the available studies on" in text


def test_template_abstract_without_run_data_is_still_clean() -> None:
    text = build_empty_section_placeholder("abstract", research_question=_QUESTION, prisma_sentence="")
    assert text is not None
    for banned in _BANNED:
        assert banned not in text
    assert "Bibliographic databases were searched." in text


def test_ensure_structured_abstract_objective_default_is_phrased() -> None:
    text = _ensure_structured_abstract("**Background:** Context.", _QUESTION)
    assert "addressed the multi-dimensional impacts" in text
    assert "?." not in text


def test_placeholder_abstract_is_flagged_as_fallback_in_manifest() -> None:
    status, fallback_used, issues = resolve_section_manifest_outcome(
        "abstract",
        writer_fallback_used=False,
        validation_issues=[],
        failed_sections=[],
        placeholder_sections={"abstract"},
    )
    assert status == "failed"
    assert fallback_used is True
    assert "empty_section_placeholder:abstract" in issues
