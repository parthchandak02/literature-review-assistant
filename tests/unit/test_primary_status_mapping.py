from __future__ import annotations

from src.extraction.primary_status import (
    primary_status_from_exclusion_reason,
    primary_status_from_study_design,
    resolve_primary_status,
)
from src.models import ExclusionReason, PrimaryStudyStatus, StudyDesign


def test_primary_status_from_study_design_primary() -> None:
    assert primary_status_from_study_design(StudyDesign.RCT) == PrimaryStudyStatus.PRIMARY
    assert primary_status_from_study_design(StudyDesign.CROSS_SECTIONAL) == PrimaryStudyStatus.PRIMARY


def test_primary_status_from_study_design_non_primary() -> None:
    assert primary_status_from_study_design(StudyDesign.NARRATIVE_REVIEW) == PrimaryStudyStatus.SECONDARY_REVIEW
    assert primary_status_from_study_design(StudyDesign.PROTOCOL) == PrimaryStudyStatus.PROTOCOL_ONLY
    assert primary_status_from_study_design(StudyDesign.DEVELOPMENT_STUDY) == PrimaryStudyStatus.NON_EMPIRICAL


def test_primary_status_from_exclusion_reason() -> None:
    assert primary_status_from_exclusion_reason(ExclusionReason.PROTOCOL_ONLY) == PrimaryStudyStatus.PROTOCOL_ONLY
    assert primary_status_from_exclusion_reason(ExclusionReason.WRONG_STUDY_DESIGN) == PrimaryStudyStatus.SECONDARY_REVIEW
    assert primary_status_from_exclusion_reason(ExclusionReason.INSUFFICIENT_DATA) == PrimaryStudyStatus.NON_EMPIRICAL


def test_resolve_primary_status_prefers_study_design() -> None:
    resolved = resolve_primary_status(
        study_design=StudyDesign.RCT,
        exclusion_reason=ExclusionReason.WRONG_STUDY_DESIGN,
    )
    assert resolved == PrimaryStudyStatus.PRIMARY


def test_resolve_primary_status_uses_screening_fallback_when_design_missing() -> None:
    resolved = resolve_primary_status(
        study_design=None,
        exclusion_reason=ExclusionReason.PROTOCOL_ONLY,
    )
    assert resolved == PrimaryStudyStatus.PROTOCOL_ONLY

