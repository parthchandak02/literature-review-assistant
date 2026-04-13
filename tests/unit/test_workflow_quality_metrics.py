from src.models import CandidatePaper, ExtractionRecord, PrimaryStudyStatus, StudyDesign
from src.orchestration.workflow import _compute_extraction_quality_metrics


def _paper(paper_id: str) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author Example"],
        year=2024,
        source_database="openalex",
    )


def test_compute_extraction_quality_metrics_flags_weak_evidence() -> None:
    records = [
        ExtractionRecord(
            paper_id="p1",
            study_design=StudyDesign.MIXED_METHODS,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
            participant_count=120,
            intervention_description="Digital registry rollout",
            results_summary={"summary": "Coverage improved after deployment."},
            extraction_source="openalex_content",
        ),
        ExtractionRecord(
            paper_id="p2",
            study_design=StudyDesign.PRE_POST,
            primary_study_status=PrimaryStudyStatus.PRIMARY,
            participant_count=None,
            intervention_description="QR code reminder system",
            results_summary={"summary": ""},
            extraction_source="text",
        ),
    ]

    completeness_ratio, weak_evidence_rate, details = _compute_extraction_quality_metrics(
        records,
        [_paper("p1"), _paper("p2")],
    )

    assert completeness_ratio < 0.80
    assert weak_evidence_rate == 0.5
    assert "summary_ratio=0.50" in details
    assert "participant_ratio=0.50" in details
    assert "fulltext_ratio=0.50" in details
