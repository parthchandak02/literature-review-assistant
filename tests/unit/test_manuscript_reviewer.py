from __future__ import annotations

from src.manuscript.reviewer import _build_audit_pass_plan, _build_manuscript_excerpt, select_audit_profiles
from src.models import DomainExpertConfig, ReviewConfig, SettingsConfig
from src.models.enums import ReviewType


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1}},
        manuscript_audit={"profile_activation": "domain_matched", "max_profiles_per_run": 3},
    )


def test_audit_profile_selection_uses_structured_qualitative_metadata() -> None:
    review = ReviewConfig(
        research_question="How do frontline clinicians experience digital vaccine record workflows?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "frontline clinicians",
            "intervention": "digital vaccine record workflows",
            "comparison": "usual documentation",
            "outcome": "workflow experience",
        },
        keywords=["digital vaccine record", "workflow"],
        domain="public health operations",
        scope="Experience and workflow review.",
        domain_expert=DomainExpertConfig(
            methodological_focus=["interview-based evidence synthesis"],
            outcome_focus=["clinician experience"],
        ),
        inclusion_criteria=[
            "Primary empirical studies using qualitative interviews or focus groups.",
            "Studies describing clinician workflow experience.",
        ],
        exclusion_criteria=["Opinion pieces."],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["pubmed", "scopus", "openalex"],
    )

    selection = select_audit_profiles(review, _settings())

    assert "general_systematic_review" in selection.selected_profiles
    assert "qualitative_methods" in selection.selected_profiles


def test_manuscript_excerpt_balances_later_core_sections() -> None:
    manuscript = "\n\n".join(
        [
            "# Title",
            "## Abstract\n" + ("abstract text " * 160),
            "## Introduction\n" + ("intro text " * 300),
            "## Methods\n" + ("methods text " * 300),
            "## Results\n" + ("results text " * 300),
            "## Discussion\nPrincipal findings and limitations.\n" + ("discussion text " * 120),
            "## Conclusion\nKey conclusion.\n" + ("conclusion text " * 80),
        ]
    )

    excerpt = _build_manuscript_excerpt(manuscript, char_budget=2600)

    assert "## Discussion" in excerpt
    assert "## Conclusion" in excerpt
    assert "Principal findings and limitations." in excerpt


def test_long_manuscript_adds_critical_section_audit_pass() -> None:
    long_manuscript = "\n\n".join(
        [
            "# Title",
            "## Abstract\n" + ("abstract text " * 300),
            "## Introduction\n" + ("intro text " * 600),
            "## Methods\n" + ("methods detail " * 1200),
            "## Results\n" + ("results detail " * 1400),
            "## Discussion\n" + ("discussion detail " * 1000),
            "## Conclusion\n" + ("conclusion detail " * 400),
            "## References\n" + ("[1] ref\n" * 50),
        ]
    )

    passes = _build_audit_pass_plan(long_manuscript, char_budget=2600)

    assert [item.label for item in passes] == ["balanced_overview", "critical_sections"]
    assert "## Methods" in passes[1].manuscript_excerpt
    assert "## Results" in passes[1].manuscript_excerpt
