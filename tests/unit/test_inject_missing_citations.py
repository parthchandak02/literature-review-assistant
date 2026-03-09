"""Unit tests for scripts/inject_missing_citations.py.

Tests the pure helper functions (no DB, no file I/O) so they run fast
without any external dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the scripts directory importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from inject_missing_citations import (
    _SENTINEL,
    _build_coverage_paragraph,
    _find_uncited_included_keys,
    _patch_results_draft,
)

# ---------------------------------------------------------------------------
# _find_uncited_included_keys
# ---------------------------------------------------------------------------


def test_find_uncited_all_cited() -> None:
    """All keys already cited -> empty list."""
    all_drafts = "See [Smith2023] and [Jones2024] for evidence."
    all_keys = ["Smith2023", "Jones2024"]
    source_type_map = {"Smith2023": "included", "Jones2024": "included"}
    uncited = _find_uncited_included_keys(all_drafts, all_keys, source_type_map)
    assert uncited == []


def test_find_uncited_one_missing() -> None:
    """One included key not in any draft -> returned."""
    all_drafts = "See [Smith2023] for evidence."
    all_keys = ["Smith2023", "Jones2024"]
    source_type_map = {"Smith2023": "included", "Jones2024": "included"}
    uncited = _find_uncited_included_keys(all_drafts, all_keys, source_type_map)
    assert uncited == ["Jones2024"]


def test_find_uncited_excludes_methodology() -> None:
    """Methodology citekeys are never required and must be excluded."""
    all_drafts = "We used PRISMA [Page2021]."
    all_keys = ["Smith2023", "Page2021"]
    source_type_map = {"Smith2023": "included", "Page2021": "methodology"}
    uncited = _find_uncited_included_keys(all_drafts, all_keys, source_type_map)
    assert uncited == ["Smith2023"]


def test_find_uncited_excludes_background_sr() -> None:
    """Background SR citekeys are excluded from required coverage."""
    all_drafts = "No relevant included study cited here."
    all_keys = ["Smith2023", "Prior2020SR"]
    source_type_map = {"Smith2023": "included", "Prior2020SR": "background_sr"}
    uncited = _find_uncited_included_keys(all_drafts, all_keys, source_type_map)
    assert uncited == ["Smith2023"]


def test_find_uncited_fallback_methodology_set() -> None:
    """Old DB with no source_type_map: known methodology keys excluded by pattern."""
    all_drafts = "No included study cited."
    all_keys = ["Smith2023", "Cohen1960", "Page2021", "Sterne2019"]
    # Empty source_type_map -> fallback path
    uncited = _find_uncited_included_keys(all_drafts, all_keys, {})
    assert uncited == ["Smith2023"]
    assert "Cohen1960" not in uncited
    assert "Page2021" not in uncited
    assert "Sterne2019" not in uncited


def test_find_uncited_fallback_sr_suffix() -> None:
    """Old DB: citekeys ending in 'SR' excluded by suffix heuristic."""
    all_drafts = "No studies cited."
    all_keys = ["Smith2023", "Jones2021SR"]
    uncited = _find_uncited_included_keys(all_drafts, all_keys, {})
    assert uncited == ["Smith2023"]


def test_find_uncited_empty_db() -> None:
    """Empty DB -> nothing to find."""
    uncited = _find_uncited_included_keys("text", [], {})
    assert uncited == []


# ---------------------------------------------------------------------------
# _build_coverage_paragraph
# ---------------------------------------------------------------------------


def test_build_coverage_paragraph_empty() -> None:
    """No uncited keys -> empty string."""
    assert _build_coverage_paragraph([]) == ""


def test_build_coverage_paragraph_single_key() -> None:
    """Single uncited key -> paragraph with that key."""
    para = _build_coverage_paragraph(["Smith2023"])
    assert "[Smith2023]" in para
    assert _SENTINEL in para


def test_build_coverage_paragraph_multiple_keys() -> None:
    """Multiple keys appear in the paragraph."""
    keys = ["Smith2023", "Jones2024", "Brown2021"]
    para = _build_coverage_paragraph(keys)
    assert "Smith2023" in para
    assert "Jones2024" in para
    assert "Brown2021" in para


def test_build_coverage_paragraph_large_group_chunks() -> None:
    """More than 8 keys split into multiple clusters."""
    keys = [f"Author{i}20{i:02d}" for i in range(12)]
    para = _build_coverage_paragraph(keys)
    # Should contain at least two citation groups separated by ';'
    assert ";" in para


# ---------------------------------------------------------------------------
# _patch_results_draft
# ---------------------------------------------------------------------------


def test_patch_inserts_before_rob_heading() -> None:
    """Patch is injected just before ### Risk of Bias."""
    draft = "### Study Characteristics\n\nSome studies [Smith2023].\n\n### Risk of Bias Assessment\n\nLow bias."
    para = "Additional studies [Jones2024]."
    patched = _patch_results_draft(draft, para)
    rob_idx = patched.index("### Risk of Bias")
    jones_idx = patched.index("Jones2024")
    assert jones_idx < rob_idx


def test_patch_appends_when_no_rob_heading() -> None:
    """When Risk of Bias heading absent, patch is appended to end of draft."""
    draft = "### Study Characteristics\n\nSome studies [Smith2023]."
    para = "Additional studies [Jones2024]."
    patched = _patch_results_draft(draft, para)
    assert patched.endswith("Additional studies [Jones2024].")


def test_patch_is_idempotent() -> None:
    """Running _patch_results_draft twice does NOT double-inject."""
    draft = "### Study Characteristics\n\n### Risk of Bias Assessment\n\n"
    para = f"{_SENTINEL}\nExtra [Jones2024]."
    patched_once = _patch_results_draft(draft, para)
    patched_twice = _patch_results_draft(patched_once, para)
    # Sentinel appears exactly once
    assert patched_twice.count(_SENTINEL) == 1
    assert patched_twice.count("[Jones2024]") == 1


def test_patch_empty_draft() -> None:
    """Empty draft -> coverage paragraph is appended."""
    para = "Extra [Jones2024]."
    patched = _patch_results_draft("", para)
    assert "Jones2024" in patched
