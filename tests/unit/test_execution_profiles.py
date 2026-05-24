from copy import deepcopy
from typing import Literal

from src.config.execution_profiles import apply_execution_profile
from src.models import ReviewConfig, ReviewType, SettingsConfig


def _base_review(profile: Literal["balanced", "throughput", "max_quality"] = "balanced") -> ReviewConfig:
    return ReviewConfig(
        research_question="Does modularization improve literature review throughput?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "software engineering teams",
            "intervention": "modular orchestration",
            "comparison": "monolith workflow",
            "outcome": "runtime and reliability",
        },
        keywords=["modularization", "workflow", "systematic review"],
        domain="software engineering",
        scope="pipeline architecture for systematic literature review automation",
        inclusion_criteria=["Empirical studies"],
        exclusion_criteria=["Opinion pieces"],
        date_range_start=2015,
        date_range_end=2026,
        target_databases=["openalex"],
        execution_profile=profile,
    )


def _base_settings() -> SettingsConfig:
    return SettingsConfig(
        agents={
            "search_query_writer": {"model": "google:test-model"},
            "reviewer_a": {"model": "google:test-model"},
        }
    )


def test_throughput_profile_prioritizes_speed() -> None:
    review = _base_review("throughput")
    settings = _base_settings()
    apply_execution_profile(review, settings)

    assert settings.screening.calibrate_threshold is False
    assert settings.rag.use_hyde is False
    assert settings.screening.screening_concurrency >= 8
    assert settings.writing.writing_concurrency >= 4
    assert settings.rag.final_k <= 6


def test_max_quality_profile_prioritizes_recall_and_grounding() -> None:
    review = _base_review("max_quality")
    settings = _base_settings()
    settings.screening.max_llm_screen = 150
    apply_execution_profile(review, settings)

    assert settings.screening.calibrate_threshold is True
    assert settings.screening.max_llm_screen is None
    assert settings.rag.use_hyde is True
    assert settings.rag.rerank is True
    assert settings.rag.candidate_k >= 28
    assert settings.rag.final_k >= 10


def test_balanced_profile_is_noop() -> None:
    review = _base_review("balanced")
    settings = _base_settings()
    before = deepcopy(settings.model_dump())
    apply_execution_profile(review, settings)
    after = settings.model_dump()

    assert after == before
