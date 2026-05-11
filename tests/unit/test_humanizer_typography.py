"""Typography and AI-lexicon normalization in humanizer guardrails."""

from __future__ import annotations

from src.writing.humanizer_guardrails import (
    apply_deterministic_guardrails,
    count_guardrail_phrases,
    count_unicode_dash_markers,
    extract_citation_blocks,
    extract_numeric_tokens,
)


def test_em_dash_replaced_comma_preserves_citekey() -> None:
    # U+2014 em dash between clauses
    text = "The effect was clear\u2014outcomes improved [Smith2023] in the trial."
    out = apply_deterministic_guardrails(text)
    assert "\u2014" not in out
    assert extract_citation_blocks(out) == extract_citation_blocks(text)
    assert "[Smith2023]" in out


def test_en_dash_numeric_range_to_ascii_hyphen() -> None:
    text = "Eligibility spanned ages 18\u201365 years and follow-up 1\u20132 years [A2020]."
    out = apply_deterministic_guardrails(text)
    assert "\u2013" not in out
    assert "18-65" in out or "18- 65" not in out
    assert "1-2" in out
    assert extract_citation_blocks(out) == extract_citation_blocks(text)


def test_unicode_minus_before_digit() -> None:
    text = "Odds ratios below unity (e.g. OR \u22120.8) were rare [Jones2021]."
    out = apply_deterministic_guardrails(text)
    assert "\u2212" not in out
    assert "OR -0.8" in out or "OR-0.8" in out
    assert extract_citation_blocks(out) == extract_citation_blocks(text)


def test_ai_lexicon_delve_replaced() -> None:
    text = "We delve into the protocol criteria before synthesis [Ref2022]."
    out = apply_deterministic_guardrails(text)
    assert "delve" not in out.lower()
    assert "examine" in out.lower()
    assert extract_citation_blocks(out) == extract_citation_blocks(text)


def test_numeric_tokens_stable_after_normalization() -> None:
    text = "Mean difference \u22122.4 points, 95% CI 1.12\u20131.63, and threshold 18\u201365 mmHg [Stat2024]."
    before_toks = extract_numeric_tokens(text)
    out = apply_deterministic_guardrails(text)
    after_toks = extract_numeric_tokens(out)
    assert before_toks == after_toks


def test_count_unicode_dash_markers() -> None:
    raw = "A\u2014B and C\u2013D plus \u22121"
    assert count_unicode_dash_markers(raw) == 3
    cleaned = apply_deterministic_guardrails(raw)
    assert count_unicode_dash_markers(cleaned) == 0


def test_count_guardrail_phrases_includes_dash_and_lexicon_keys() -> None:
    metrics = count_guardrail_phrases("Note\u2014text")
    assert "unicode_dash_markers" in metrics
    assert "ai_lexicon_hits" in metrics
