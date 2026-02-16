"""CASP assessor for qualitative studies."""

from __future__ import annotations

from pydantic import BaseModel

from src.models import ExtractionRecord


class CaspAssessment(BaseModel):
    paper_id: str
    design_appropriate: bool
    recruitment_strategy: bool
    data_collection_rigorous: bool
    reflexivity_considered: bool
    ethics_considered: bool
    analysis_rigorous: bool
    findings_clear: bool
    value_of_research: bool
    overall_summary: str


class CaspAssessor:
    """Produce typed CASP-style outputs."""

    def assess(self, record: ExtractionRecord) -> CaspAssessment:
        summary = (record.results_summary.get("summary") or "").lower()
        has_methods = any(token in summary for token in ["interview", "focus group", "thematic"])
        return CaspAssessment(
            paper_id=record.paper_id,
            design_appropriate=has_methods,
            recruitment_strategy=True,
            data_collection_rigorous=has_methods,
            reflexivity_considered=False,
            ethics_considered=True,
            analysis_rigorous=has_methods,
            findings_clear=True,
            value_of_research=True,
            overall_summary="CASP heuristic pass with conservative defaults.",
        )
