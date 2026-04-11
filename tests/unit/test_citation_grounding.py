"""Unit tests for src/writing/citation_grounding.py."""

from __future__ import annotations

from src.writing.citation_grounding import (
    _fuzzy_match_citekey,
    extract_used_citekeys,
    repair_hallucinated_citekeys,
    verify_citation_grounding,
)

# ---------------------------------------------------------------------------
# extract_used_citekeys
# ---------------------------------------------------------------------------


def test_extract_used_citekeys_basic() -> None:
    text = "Findings from [Smith2023] and [Jones2024] support this."
    assert extract_used_citekeys(text) == ["Smith2023", "Jones2024"]


def test_extract_used_citekeys_deduplicates() -> None:
    text = "[Smith2023] confirmed by [Smith2023] again."
    assert extract_used_citekeys(text) == ["Smith2023"]


def test_extract_used_citekeys_preserves_order() -> None:
    text = "[Zebra2020] then [Apple2019] then [Mango2021]."
    assert extract_used_citekeys(text) == ["Zebra2020", "Apple2019", "Mango2021"]


def test_extract_used_citekeys_no_matches() -> None:
    text = "No citations here."
    assert extract_used_citekeys(text) == []


def test_extract_used_citekeys_includes_placeholder_patterns() -> None:
    text = "See [Ref141] and [Paper_ab12cd] plus [Smith2023]."
    assert extract_used_citekeys(text) == ["Ref141", "Paper_ab12cd", "Smith2023"]


# ---------------------------------------------------------------------------
# _fuzzy_match_citekey
# ---------------------------------------------------------------------------


def test_fuzzy_match_exact_year_substring() -> None:
    valid = ["Smith2023", "Jones2024", "Brown2021"]
    result = _fuzzy_match_citekey("Smith2023a", valid)
    assert result == "Smith2023"


def test_fuzzy_match_rejects_short_prefix() -> None:
    valid = ["Rodriguez2020", "Jones2021"]
    result = _fuzzy_match_citekey("Rod2020", valid)
    assert result is None


def test_fuzzy_match_no_year_returns_none() -> None:
    valid = ["Smith2023"]
    result = _fuzzy_match_citekey("NoYear", valid)
    assert result is None


def test_fuzzy_match_short_author_returns_none() -> None:
    valid = ["Smith2023"]
    result = _fuzzy_match_citekey("S2023", valid)
    assert result is None


def test_fuzzy_match_no_candidates_returns_none() -> None:
    valid = ["Smith2023", "Jones2024"]
    result = _fuzzy_match_citekey("Brown2021", valid)
    assert result is None


def test_fuzzy_match_ambiguous_prefix_returns_none() -> None:
    # Two candidates share a prefix -- no confident match.
    valid = ["SmithA2020", "SmithB2020"]
    result = _fuzzy_match_citekey("Smi2020", valid)
    assert result is None


def test_fuzzy_match_does_not_use_year_only_fallback() -> None:
    valid = ["PreviousSR2020"]
    result = _fuzzy_match_citekey("Pre2020", valid)
    assert result is None


# ---------------------------------------------------------------------------
# repair_hallucinated_citekeys
# ---------------------------------------------------------------------------


def test_repair_no_hallucinations() -> None:
    text = "Supported by [Smith2023]."
    result = repair_hallucinated_citekeys(text, [], ["Smith2023"])
    assert result == text


def test_repair_exact_fuzzy_match() -> None:
    # "SmithLong2023" author token "smithlong" contains "smith" -> maps to Smith2023
    text = "See [SmithLong2023] for details."
    result = repair_hallucinated_citekeys(text, ["SmithLong2023"], ["Smith2023"])
    assert "[Smith2023]" in result
    assert "[SmithLong2023]" not in result


def test_repair_no_match_drops_unresolved_token() -> None:
    text = "See [Xyz9999] for details."
    result = repair_hallucinated_citekeys(text, ["Xyz9999"], ["Smith2023", "Jones2024"])
    assert "[Xyz9999]" not in result
    assert "(citation unavailable)" not in result


def test_repair_replaces_all_occurrences() -> None:
    # Author token "smithlong" contains "smith" -> two occurrences both replaced
    text = "[SmithLong2023] found that [SmithLong2023] was significant."
    result = repair_hallucinated_citekeys(text, ["SmithLong2023"], ["Smith2023"])
    assert result.count("[Smith2023]") == 2
    assert "[SmithLong2023]" not in result


def test_repair_empty_text_unchanged() -> None:
    result = repair_hallucinated_citekeys("", ["Fake2020"], ["Smith2023"])
    assert result == ""


def test_repair_strips_uuid_like_bracket_tokens() -> None:
    text = "Result remained positive [5a40ea3d-547] after screening."
    result = repair_hallucinated_citekeys(text, [], ["Smith2023"])
    assert "[5a40ea3d-547]" not in result


def test_repair_strips_template_bracket_tokens() -> None:
    text = "Effect of [INTERVENTION] on [OUTCOME] in [POPULATION]."
    result = repair_hallucinated_citekeys(text, [], ["Smith2023"])
    assert "[INTERVENTION]" not in result
    assert "[OUTCOME]" not in result
    assert "[POPULATION]" not in result


# ---------------------------------------------------------------------------
# verify_citation_grounding
# ---------------------------------------------------------------------------


def test_verify_all_valid() -> None:
    text = "See [Smith2023] and [Jones2024]."
    valid = ["Smith2023", "Jones2024", "Brown2021"]
    verified, hallucinated = verify_citation_grounding(text, valid, "results")
    assert set(verified) == {"Smith2023", "Jones2024"}
    assert hallucinated == []


def test_verify_detects_hallucinated() -> None:
    text = "See [Smith2023] and [FakeRef2099]."
    valid = ["Smith2023", "Jones2024"]
    verified, hallucinated = verify_citation_grounding(text, valid, "results")
    assert "Smith2023" in verified
    assert "FakeRef2099" in hallucinated


def test_verify_empty_text() -> None:
    verified, hallucinated = verify_citation_grounding("", ["Smith2023"], "abstract")
    assert verified == []
    assert hallucinated == []


def test_verify_no_valid_keys() -> None:
    text = "See [Smith2023]."
    verified, hallucinated = verify_citation_grounding(text, [], "intro")
    assert verified == []
    assert "Smith2023" in hallucinated
