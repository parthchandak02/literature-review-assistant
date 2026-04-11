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
