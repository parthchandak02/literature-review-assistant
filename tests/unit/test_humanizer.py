"""Unit tests for humanizer integrity guardrails."""

from __future__ import annotations

from src.writing.humanizer import _passes_integrity_checks


def test_integrity_checks_pass_for_safe_rewrite() -> None:
    before = "This suggests that effect size was 1.20 [Smith2023]."
    after = "Effect size was 1.20 [Smith2023]."
    assert _passes_integrity_checks(before, after) is True


def test_integrity_checks_fail_on_citation_change() -> None:
    before = "Result [Smith2023]."
    after = "Result [Jones2024]."
    assert _passes_integrity_checks(before, after) is False


def test_integrity_checks_fail_on_numeric_change() -> None:
    before = "OR 1.47 and p 0.01 [Smith2023]."
    after = "OR 2.47 and p 0.01 [Smith2023]."
    assert _passes_integrity_checks(before, after) is False
