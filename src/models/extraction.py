"""Extraction models."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.models.enums import StudyDesign


class ExtractionRecord(BaseModel):
    paper_id: str
    study_design: StudyDesign
    study_duration: Optional[str] = None
    setting: Optional[str] = None
    participant_count: Optional[int] = None
    participant_demographics: Optional[str] = None
    intervention_description: str
    comparator_description: Optional[str] = None
    outcomes: List[Dict[str, str]] = Field(default_factory=list)
    results_summary: Dict[str, str] = Field(default_factory=dict)
    funding_source: Optional[str] = None
    conflicts_of_interest: Optional[str] = None
    source_spans: Dict[str, str] = Field(default_factory=dict)
    extraction_confidence: Optional[float] = Field(
        default=None,
        description="LLM self-reported confidence in the extraction (0.0-1.0).",
    )
    extraction_source: Optional[Literal[
        "text",           # abstract / title text only (baseline)
        "sciencedirect",  # full text from ScienceDirect Article Retrieval API
        "unpaywall_text", # full text from Unpaywall (HTML/text response)
        "pmc",            # full text from PubMed Central XML
        "unpaywall_pdf",  # PDF obtained from Unpaywall (used for vision extraction)
        "pdf_vision",     # table data extracted via Gemini vision from PDF
        "hybrid",         # merge of text-LLM and PDF-vision outcomes
        "heuristic",      # rule-based extraction fallback
    ]] = Field(
        default="text",
        description=(
            "How outcome data was obtained. 'text' = abstract only (baseline). "
            "Full-text tiers: 'sciencedirect', 'unpaywall_text', 'pmc'. "
            "Vision: 'unpaywall_pdf' -> 'pdf_vision'. "
            "Merged: 'hybrid'. Fallback: 'heuristic'."
        ),
    )
