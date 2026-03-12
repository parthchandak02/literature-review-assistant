"""Primary-vs-secondary study status mapping helpers."""

from __future__ import annotations

from src.models.enums import ExclusionReason, PrimaryStudyStatus, StudyDesign

_PRIMARY_DESIGNS: frozenset[StudyDesign] = frozenset(
    {
        StudyDesign.RCT,
        StudyDesign.NON_RANDOMIZED,
        StudyDesign.QUASI_EXPERIMENTAL,
        StudyDesign.COHORT,
        StudyDesign.CASE_CONTROL,
        StudyDesign.PRE_POST,
        StudyDesign.QUALITATIVE,
        StudyDesign.MIXED_METHODS,
        StudyDesign.CROSS_SECTIONAL,
        StudyDesign.USABILITY_STUDY,
    }
)


def primary_status_from_study_design(study_design: StudyDesign) -> PrimaryStudyStatus:
    """Map StudyDesign to canonical primary-study status."""
    if study_design in _PRIMARY_DESIGNS:
        return PrimaryStudyStatus.PRIMARY
    if study_design == StudyDesign.NARRATIVE_REVIEW:
        return PrimaryStudyStatus.SECONDARY_REVIEW
    if study_design == StudyDesign.PROTOCOL:
        return PrimaryStudyStatus.PROTOCOL_ONLY
    if study_design in {
        StudyDesign.CONFERENCE_ABSTRACT,
        StudyDesign.DEVELOPMENT_STUDY,
        StudyDesign.OTHER,
    }:
        return PrimaryStudyStatus.NON_EMPIRICAL
    return PrimaryStudyStatus.UNKNOWN


def primary_status_from_exclusion_reason(exclusion_reason: ExclusionReason | None) -> PrimaryStudyStatus:
    """Map screening exclusion reasons to primary-study status when available."""
    if exclusion_reason is None:
        return PrimaryStudyStatus.UNKNOWN
    if exclusion_reason == ExclusionReason.PROTOCOL_ONLY:
        return PrimaryStudyStatus.PROTOCOL_ONLY
    if exclusion_reason == ExclusionReason.WRONG_STUDY_DESIGN:
        return PrimaryStudyStatus.SECONDARY_REVIEW
    if exclusion_reason == ExclusionReason.INSUFFICIENT_DATA:
        return PrimaryStudyStatus.NON_EMPIRICAL
    return PrimaryStudyStatus.UNKNOWN


def resolve_primary_status(
    study_design: StudyDesign | None,
    exclusion_reason: ExclusionReason | None = None,
) -> PrimaryStudyStatus:
    """Resolve canonical status from extraction design and screening fallback."""
    if study_design is not None:
        by_design = primary_status_from_study_design(study_design)
        if by_design != PrimaryStudyStatus.UNKNOWN:
            return by_design
    return primary_status_from_exclusion_reason(exclusion_reason)

