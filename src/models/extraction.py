"""Extraction models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.models.enums import StudyDesign


class ExtractionRecord(BaseModel):
    paper_id: str
    study_design: StudyDesign
    study_duration: str | None = None
    setting: str | None = None
    participant_count: int | None = None
    participant_demographics: str | None = None
    intervention_description: str
    comparator_description: str | None = None
    outcomes: list[dict[str, str]] = Field(default_factory=list)
    results_summary: dict[str, str] = Field(default_factory=dict)
    funding_source: str | None = None
    conflicts_of_interest: str | None = None
    source_spans: dict[str, str] = Field(default_factory=dict)
    extraction_confidence: float | None = Field(
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
