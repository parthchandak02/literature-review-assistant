import pytest

from src.models import PCCConfig, PICOConfig, ReviewConfig
from src.models.enums import ReviewType


def _base_kwargs() -> dict:
    return {
        "research_question": "What evidence exists on topic X?",
        "pico": PICOConfig(
            population="adults",
            intervention="topic X",
            comparison="community",
            outcome="evidence characteristics and gaps",
        ),
        "keywords": ["topic"],
        "domain": "health",
        "scope": "community evidence mapping",
        "inclusion_criteria": ["empirical studies"],
        "exclusion_criteria": ["editorials"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "target_databases": ["openalex"],
    }


def test_systematic_defaults_question_framework_to_pico() -> None:
    cfg = ReviewConfig(review_type=ReviewType.SYSTEMATIC, **_base_kwargs())
    assert cfg.question_framework == "pico"
    assert cfg.pcc is None


def test_scoping_requires_populated_pcc() -> None:
    with pytest.raises(ValueError, match="populated pcc"):
        ReviewConfig(review_type=ReviewType.SCOPING, **_base_kwargs())


def test_scoping_rejects_empty_pcc_fields() -> None:
    with pytest.raises(ValueError, match="pcc.concept"):
        ReviewConfig(
            review_type=ReviewType.SCOPING,
            pcc=PCCConfig(population="adults", concept="", context="community"),
            **_base_kwargs(),
        )


def test_scoping_accepts_valid_pcc_and_defaults_framework() -> None:
    cfg = ReviewConfig(
        review_type=ReviewType.SCOPING,
        pcc=PCCConfig(population="adults", concept="topic X", context="community"),
        **_base_kwargs(),
    )
    assert cfg.question_framework == "pcc"
    assert cfg.pcc is not None
    assert cfg.pcc.concept == "topic X"
