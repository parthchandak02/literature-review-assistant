from __future__ import annotations

import pytest

from src.models import ExtractionRecord, StudyDesign
from src.quality.casp import CaspAssessor
from src.quality.mmat import MmatAssessor


def _qual_record() -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="casp-1",
        study_design=StudyDesign.QUALITATIVE,
        intervention_description="Learner interviews about AI tutor use",
        outcomes=[],
        results_summary={"summary": "Qualitative themes were reported."},
    )


def _mmat_record() -> ExtractionRecord:
    return ExtractionRecord(
        paper_id="mmat-1",
        study_design=StudyDesign.MIXED_METHODS,
        intervention_description="Mixed-methods evaluation of tutoring support",
        outcomes=[],
        results_summary={"summary": "Survey and interview data were combined."},
    )


@pytest.mark.asyncio
async def test_casp_heuristic_sets_fallback_used() -> None:
    assessment = await CaspAssessor().assess(_qual_record())
    assert assessment.assessment_source == "heuristic"
    assert assessment.fallback_used is True


@pytest.mark.asyncio
async def test_mmat_heuristic_sets_fallback_used() -> None:
    assessment = await MmatAssessor().assess(_mmat_record())
    assert assessment.assessment_source == "heuristic"
    assert assessment.fallback_used is True
