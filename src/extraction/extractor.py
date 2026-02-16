"""Structured extraction service."""

from __future__ import annotations

from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, ExtractionRecord, StudyDesign


class ExtractionService:
    """Create typed extraction records from paper metadata/full text."""

    def __init__(self, repository: WorkflowRepository):
        self.repository = repository

    @staticmethod
    def _normalized_summary(paper: CandidatePaper, full_text: str) -> str:
        text = full_text.strip()
        if text:
            return text[:1200]
        abstract = (paper.abstract or "").strip()
        if abstract:
            return abstract[:1200]
        return "No summary available."

    @staticmethod
    def _outcomes() -> list[dict[str, str]]:
        return [
            {
                "name": "primary_outcome",
                "description": "Learning performance or retention signal extracted from source context.",
            }
        ]

    async def extract(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        text = full_text[:10000]
        summary = self._normalized_summary(paper, text)
        record = ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            study_duration="unknown",
            setting="not_reported",
            participant_count=None,
            participant_demographics=None,
            intervention_description=paper.title[:500],
            comparator_description=None,
            outcomes=self._outcomes(),
            results_summary={
                "summary": summary,
                "source": "full_text" if text.strip() else "metadata",
            },
            funding_source=None,
            conflicts_of_interest=None,
            source_spans={
                "full_text_excerpt": text[:500] if text.strip() else "",
                "title": paper.title[:500],
            },
        )
        await self.repository.save_extraction_record(workflow_id=workflow_id, record=record)
        return record
