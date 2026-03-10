"""Unit tests for deterministic humanizer guardrails."""

from __future__ import annotations

from src.writing.humanizer_guardrails import (
    TOP5_HEURISTIC_CATEGORIES,
    apply_deterministic_guardrails,
    count_guardrail_phrases,
    extract_citation_blocks,
    extract_numeric_tokens,
)


def test_top5_heuristic_categories_stable() -> None:
    assert TOP5_HEURISTIC_CATEGORIES == (
        "boilerplate_transition_overuse",
        "repetitive_sentence_openings",
        "inflated_hedging_filler",
        "redundant_policy_conclusion_templates",
        "unnatural_lexical_repetition",
    )


def test_guardrails_preserve_citation_blocks() -> None:
    text = (
        "It is important to note that this suggests that results improved [Smith2023]. "
        "It is worth noting that confidence remained high [Jones2024]."
    )
    out = apply_deterministic_guardrails(text)
    assert extract_citation_blocks(out) == extract_citation_blocks(text)


def test_guardrails_preserve_numeric_tokens() -> None:
    text = (
        "The findings indicate that OR 1.47, 95% CI 1.12-1.63, p < 0.001 and 54.4% "
        "met criteria at 130 mmHg and 80 mmHg."
    )
    out = apply_deterministic_guardrails(text)
    assert extract_numeric_tokens(out) == extract_numeric_tokens(text)


def test_guardrails_reduce_filler_phrases() -> None:
    text = (
        "It is important to note that this suggests that we should act. "
        "It is worth noting that the findings indicate that interventions worked."
    )
    before = count_guardrail_phrases(text)["filler_phrases"]
    out = apply_deterministic_guardrails(text)
    after = count_guardrail_phrases(out)["filler_phrases"]
    assert after < before


def test_guardrails_idempotent() -> None:
    text = "This suggests that policy should change [Policy2024] with OR 2.10 and p 0.01."
    once = apply_deterministic_guardrails(text)
    twice = apply_deterministic_guardrails(once)
    assert once == twice
