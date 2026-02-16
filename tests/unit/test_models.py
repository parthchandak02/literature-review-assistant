from src.models import CandidatePaper, ReviewConfig, ReviewType, ScreeningDecision, ScreeningDecisionType, ReviewerType


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
