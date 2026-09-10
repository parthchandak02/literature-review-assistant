"""Methodology profile resolved from review configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.config import QuestionFramework, ReviewConfig
from src.models.enums import ReviewType

RegistrationGate = Literal["prospero", "osf"]
ReportingGuideline = Literal["prisma_2020", "prisma_scr"]


class MethodologyProfile(BaseModel):
    """Resolved methodology contract for a review run."""

    review_type: ReviewType
    question_framework: QuestionFramework
    registration_gate: RegistrationGate
    include_secondary_sources: bool
    critical_appraisal_required: bool
    allows_meta_analysis: bool
    allows_grade: bool
    reporting_guideline: ReportingGuideline
    manuscript_audit_profile: str = Field(
        description="Primary manuscript-audit profile identifier for this review type.",
    )


_SYSTEMATIC_DEFAULTS: dict[str, object] = {
    "question_framework": "pico",
    "registration_gate": "prospero",
    "include_secondary_sources": False,
    "critical_appraisal_required": True,
    "allows_meta_analysis": True,
    "allows_grade": True,
    "reporting_guideline": "prisma_2020",
    "manuscript_audit_profile": "general_systematic_review",
}

_SCOPING_DEFAULTS: dict[str, object] = {
    "question_framework": "pcc",
    "registration_gate": "osf",
    "include_secondary_sources": True,
    "critical_appraisal_required": False,
    "allows_meta_analysis": False,
    "allows_grade": False,
    "reporting_guideline": "prisma_scr",
    "manuscript_audit_profile": "scoping_review",
}


def _default_question_framework(review_type: ReviewType) -> QuestionFramework:
    if review_type == ReviewType.SCOPING:
        return "pcc"
    return "pico"


def resolve_profile(review_config: ReviewConfig) -> MethodologyProfile:
    """Resolve methodology settings from a validated review configuration."""
    defaults = _SCOPING_DEFAULTS if review_config.review_type == ReviewType.SCOPING else _SYSTEMATIC_DEFAULTS
    question_framework = review_config.question_framework or _default_question_framework(review_config.review_type)
    return MethodologyProfile(
        review_type=review_config.review_type,
        question_framework=question_framework,
        registration_gate=defaults["registration_gate"],  # type: ignore[arg-type]
        include_secondary_sources=defaults["include_secondary_sources"],  # type: ignore[arg-type]
        critical_appraisal_required=defaults["critical_appraisal_required"],  # type: ignore[arg-type]
        allows_meta_analysis=defaults["allows_meta_analysis"],  # type: ignore[arg-type]
        allows_grade=defaults["allows_grade"],  # type: ignore[arg-type]
        reporting_guideline=defaults["reporting_guideline"],  # type: ignore[arg-type]
        manuscript_audit_profile=str(defaults["manuscript_audit_profile"]),
    )
