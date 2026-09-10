from src.models import PCCConfig, PICOConfig, ReviewConfig, resolve_profile
from src.models.enums import ReviewType
from src.models.methodology_profile import MethodologyProfile


def _systematic_config() -> ReviewConfig:
    return ReviewConfig(
        research_question="What is the effect of X on Y?",
        review_type=ReviewType.SYSTEMATIC,
        pico=PICOConfig(
            population="adults",
            intervention="X",
            comparison="usual care",
            outcome="Y",
        ),
        keywords=["intervention"],
        domain="health",
        scope="community settings",
        inclusion_criteria=["empirical studies"],
        exclusion_criteria=["reviews"],
        date_range_start=2010,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _scoping_config() -> ReviewConfig:
    return ReviewConfig(
        research_question="What evidence exists on X for Y?",
        review_type=ReviewType.SCOPING,
        question_framework="pcc",
        pcc=PCCConfig(
            population="adults",
            concept="X",
            context="community settings",
        ),
        pico=PICOConfig(
            population="adults",
            intervention="X",
            comparison="community settings",
            outcome="evidence characteristics and gaps",
        ),
        keywords=["mapping"],
        domain="health",
        scope="maps available evidence",
        inclusion_criteria=["empirical studies"],
        exclusion_criteria=["editorials"],
        date_range_start=2010,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def test_resolve_profile_systematic_defaults() -> None:
    profile = resolve_profile(_systematic_config())
    assert isinstance(profile, MethodologyProfile)
    assert profile.review_type == ReviewType.SYSTEMATIC
    assert profile.question_framework == "pico"
    assert profile.registration_gate == "prospero"
    assert profile.include_secondary_sources is False
    assert profile.critical_appraisal_required is True
    assert profile.allows_meta_analysis is True
    assert profile.allows_grade is True
    assert profile.reporting_guideline == "prisma_2020"
    assert profile.manuscript_audit_profile == "general_systematic_review"


def test_resolve_profile_scoping_defaults() -> None:
    profile = resolve_profile(_scoping_config())
    assert profile.review_type == ReviewType.SCOPING
    assert profile.question_framework == "pcc"
    assert profile.registration_gate == "osf"
    assert profile.include_secondary_sources is True
    assert profile.critical_appraisal_required is False
    assert profile.allows_meta_analysis is False
    assert profile.allows_grade is False
    assert profile.reporting_guideline == "prisma_scr"
