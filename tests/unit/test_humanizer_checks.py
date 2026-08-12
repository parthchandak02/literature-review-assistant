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
    assert len(high) >= 2


def test_academic_sr_prose_not_flagged_high() -> None:
    text = (
        "The meta-analysis used robust standard errors after a comprehensive search of MEDLINE and Embase "
        "to enhance comparability."
    )
    flags = scan_humanizer_flags(text)
    high_blacklist = [f for f in flags if f.tier == "high" and f.code == "blacklist_term"]
    assert not high_blacklist
    assert has_high_severity(flags) is False


def test_manuscript_like_text_has_no_high_flags() -> None:
    text = (
        "Among included studies, pooled effect estimates remained directionally consistent across sensitivity analyses "
        "[Smith2023]. Risk-of-bias concerns were concentrated in allocation concealment domains [Jones2024]."
    )
    flags = scan_humanizer_flags(text)
    assert has_high_severity(flags) is False


def test_new_upstream_patterns_flagged() -> None:
    text = (
        "At its core, what really matters is readiness. Let's dive in to the details. "
        "She maintains a low profile and keeps personal details private."
    )
    flags = scan_humanizer_flags(text)
    codes = {flag.code for flag in flags}
    assert "persuasive_authority_trope" in codes
    assert "signposting_announcement" in codes
    assert "cutoff_disclaimer" in codes
    assert any(flag.code == "cutoff_disclaimer" and flag.tier == "high" for flag in flags)


def test_em_dash_is_high_severity() -> None:
    flags = scan_humanizer_flags("This is a test — with an em dash.")
    em_flags = [flag for flag in flags if flag.code == "em_dash_overuse"]
    assert em_flags
    assert all(flag.tier == "high" for flag in em_flags)


def test_en_dash_in_numeric_ranges_not_flagged() -> None:
    """En dashes in CI and age ranges are legitimate in manuscripts."""
    samples = [
        "The OR was 1.47 (95% CI 1.20–3.40) [Smith2023].",
        "Participants aged 15–20 years were included.",
    ]
    for text in samples:
        flags = scan_humanizer_flags(text)
        assert not any(flag.code == "em_dash_overuse" for flag in flags), (
            f"en-dash false positive in: {text!r}"
        )
        assert has_high_severity(flags) is False


def test_expanded_blacklist_terms() -> None:
    flags = scan_humanizer_flags("The cohort was vibrant and heterogeneous.")
    terms = [flag.message for flag in flags if flag.code == "blacklist_term"]
    assert any("vibrant" in msg.lower() for msg in terms)


def test_format_flags_for_repair_high_only() -> None:
    flags = scan_humanizer_flags("In today's landscape, this is crucial.")
    rendered = format_flags_for_repair(flags)
    assert "formulaic_opening" in rendered
    assert "metric_" not in rendered
