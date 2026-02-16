"""Structured extraction service."""

from __future__ import annotations

from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, ExtractionRecord, StudyDesign


class ExtractionService:
    """Create typed extraction records from paper metadata/full text."""

    def __init__(self, repository: WorkflowRepository):
        self.repository = repository

    async def extract(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        text = full_text[:10000]
        record = ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            study_duration="unknown",
            setting="not_reported",
            participant_count=None,
            participant_demographics=None,
            intervention_description=paper.title[:500],
            comparator_description=None,
            outcomes=[
                {
                    "name": "primary_outcome",
                    "description": "Extracted from metadata/full-text context",
                }
            ],
            results_summary={
                "summary": text[:1200] if text else (paper.abstract or "No summary available"),
            },
            funding_source=None,
            conflicts_of_interest=None,
            source_spans={
                "full_text_excerpt": text[:500],
            },
        )
        await self.repository.save_extraction_record(workflow_id=workflow_id, record=record)
        return record
