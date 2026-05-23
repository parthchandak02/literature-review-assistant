import pytest

from src.models import (
    CandidatePaper,
    DomainExpertConfig,
    ReviewConfig,
    ReviewerType,
    ReviewType,
    ScreeningDecision,
    ScreeningDecisionType,
)
from src.models.config import ScreeningConfig


def test_review_config_validation() -> None:
    config = ReviewConfig(
        research_question="rq",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "p",
            "intervention": "i",
            "comparison": "c",
            "outcome": "o",
        },
        keywords=["k1"],
        domain="d",
        scope="s",
        inclusion_criteria=["i1"],
        exclusion_criteria=["e1"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )
    assert config.review_type == ReviewType.SYSTEMATIC
    assert config.expert_topic() == "s"


def test_review_config_domain_brief_helpers() -> None:
    config = ReviewConfig(
        research_question="How do digital twins improve manufacturing quality?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "factory operators",
            "intervention": "digital twin systems",
            "comparison": "legacy monitoring",
            "outcome": "defect detection and downtime",
        },
        keywords=["digital twin", "manufacturing analytics"],
        domain="industrial engineering",
        scope="Industrial monitoring and production quality outcomes.",
        domain_expert=DomainExpertConfig(
            expert_role="Industrial engineering evidence reviewer",
            canonical_terms=["digital twin", "condition monitoring"],
            related_terms=["predictive maintenance"],
            excluded_terms=["clinical trial"],
            methodological_focus=["controlled industrial evaluations"],
            outcome_focus=["defect detection"],
        ),
        inclusion_criteria=["Empirical primary studies."],
        exclusion_criteria=["Opinion pieces."],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
    )
    assert "digital twin" in config.preferred_terminology()
    assert "predictive maintenance" in config.domain_signal_terms()
    assert "clinical trial" in config.discouraged_terminology()
    assert any("Industrial engineering evidence reviewer" in line for line in config.domain_brief_lines())


def test_review_config_database_bundle_resolution() -> None:
    config = ReviewConfig(
        research_question="rq",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "p",
            "intervention": "i",
            "comparison": "c",
            "outcome": "o",
        },
        keywords=["k1"],
        domain="d",
        scope="s",
        inclusion_criteria=["i1"],
        exclusion_criteria=["e1"],
        date_range_start=2015,
        date_range_end=2026,
        database_bundle="ai_agentic",
        target_databases=["openalex"],
    )
    resolved = config.resolved_target_databases()
    assert "openalex" in resolved
    assert "dblp" in resolved
    assert "arxiv" in resolved


def test_review_config_rejects_unknown_database() -> None:
    with pytest.raises(ValueError):
        ReviewConfig(
            research_question="rq",
            review_type=ReviewType.SYSTEMATIC,
            pico={
                "population": "p",
                "intervention": "i",
                "comparison": "c",
                "outcome": "o",
            },
            keywords=["k1"],
            domain="d",
            scope="s",
            inclusion_criteria=["i1"],
            exclusion_criteria=["e1"],
            date_range_start=2015,
            date_range_end=2026,
            target_databases=["google_scholar"],
        )


def test_review_config_accepts_research_entry() -> None:
    config = ReviewConfig(
        research_question="Can waste heat recovery improve urban respiratory health outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "Urban populations in high-traffic corridors",
            "intervention": "Automotive waste heat recovery",
            "comparison": "Baseline vehicles without recovery systems",
            "outcome": "Air pollution and respiratory health indicators",
        },
        keywords=["waste heat recovery", "vehicular emissions", "sdg 3.9.1"],
        domain="Automotive engineering and environmental health",
        scope="Hybrid engineering-health systematic review framing.",
        inclusion_criteria=["Primary empirical studies reporting emissions or health outcomes."],
        exclusion_criteria=["Narrative reviews and opinion pieces."],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex", "pubmed"],
        research_entry={
            "original_topic": "Waste heat generation in automobiles",
            "research_question": "Can automotive waste heat recovery reduce urban pollution-related health harms?",
            "health_impact": {
                "primary_concern": "Ambient air pollution from vehicle exhaust",
                "affected_populations": ["Urban residents"],
                "health_outcomes_targeted": ["Respiratory disease burden"],
                "who_indicator": "SDG 3.9.1",
                "estimated_impact_pathway": "Lower fuel burn -> reduced PM2.5/NOx -> lower exposure.",
            },
            "sdg_alignment": {
                "primary_sdg": {
                    "goal": 3,
                    "name": "Good Health and Well-Being",
                    "target": "3.9",
                    "sub_target": "3.9.1",
                },
                "secondary_sdgs": [
                    {
                        "goal": 7,
                        "name": "Affordable and Clean Energy",
                        "relevance": "Energy efficiency co-benefit",
                        "target": "7.3",
                    }
                ],
            },
            "research_metadata": {
                "domain": "Automotive engineering / environmental health",
                "methodology_suggested": "Quantitative synthesis",
                "data_sources": ["WHO Air Quality Database"],
                "keywords": ["waste heat recovery", "pm2.5"],
                "geographic_scope": "Global urban centers",
                "time_horizon": "2025-2030",
            },
        },
    )
    assert config.research_entry is not None
    assert config.research_entry.sdg_alignment.primary_sdg.goal == 3


def test_paper_and_screening_models() -> None:
    paper = CandidatePaper(
        title="t",
        authors=["a"],
        source_database="openalex",
    )
    decision = ScreeningDecision(
        paper_id=paper.paper_id,
        decision=ScreeningDecisionType.INCLUDE,
        reviewer_type=ReviewerType.REVIEWER_A,
        confidence=0.9,
    )
    assert decision.paper_id == paper.paper_id


def test_screening_config_new_defaults() -> None:
    cfg = ScreeningConfig()
    assert cfg.auto_exclude_empty_abstract is True
    assert cfg.max_llm_screen is None
    assert cfg.cap_overflow_enabled is True
    assert cfg.empty_abstract_rescue_sample_size >= 0
    assert cfg.cap_overflow_max_extra >= cfg.cap_overflow_slice_size
