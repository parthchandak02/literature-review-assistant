"""Unit tests for deterministic humanizer checks."""

from __future__ import annotations

from src.writing.humanizer_checks import format_flags_for_repair, has_high_severity, scan_humanizer_flags


def test_blacklist_and_formulaic_opening_flagged_high() -> None:
    text = "In today's rapidly evolving digital landscape, this robust approach is crucial."
    flags = scan_humanizer_flags(text)
    assert has_high_severity(flags) is True
    assert any(flag.code == "formulaic_opening" for flag in flags)
    assert any(flag.code == "blacklist_term" for flag in flags)


def test_before_example_has_multiple_high_flags() -> None:
    text = (
        "In today's rapidly evolving digital landscape, cybersecurity has become a crucial and pivotal concern. "
        "Moreover, the increasing sophistication of cyber threats underscores the importance of implementing robust "
        "and comprehensive security measures. Studies show that a holistic approach serves as the most effective "
        "strategy. However, despite these challenges, the future outlook remains promising."
    )
    flags = scan_humanizer_flags(text)
    high = [flag for flag in flags if flag.tier == "high"]
    assert len(high) >= 4


def test_manuscript_like_text_has_no_high_flags() -> None:
    text = (
        "Among included studies, pooled effect estimates remained directionally consistent across sensitivity analyses "
        "[Smith2023]. Risk-of-bias concerns were concentrated in allocation concealment domains [Jones2024]."
    )
    flags = scan_humanizer_flags(text)
    assert has_high_severity(flags) is False


def test_format_flags_for_repair_high_only() -> None:
    flags = scan_humanizer_flags("In today's landscape, this is crucial.")
    rendered = format_flags_for_repair(flags)
    assert "formulaic_opening" in rendered
    assert "metric_" not in rendered
