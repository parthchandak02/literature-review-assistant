"""Extraction models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.models.enums import StudyDesign


class OutcomeRecord(BaseModel):
    """Structured outcome measure extracted from a study.

    All fields are optional strings so that partial LLM extractions and
    heuristic fallbacks do not fail validation. Numeric fields (effect_size,
    se, ci_lower, ci_upper, variance) are kept as strings to preserve the
    exact text the LLM returned; callers convert to float as needed.
    """

    name: str = ""
    description: str = ""
    effect_size: str = ""
    se: str = ""
    n: str = ""
    ci_lower: str = ""
    ci_upper: str = ""
    p_value: str = ""
    title: str = ""
    variance: str = ""


class ExtractionRecord(BaseModel):
    paper_id: str
    study_design: StudyDesign
    study_duration: str | None = None
    setting: str | None = None
    participant_count: int | None = None
    participant_demographics: str | None = None
    intervention_description: str
    comparator_description: str | None = None
    outcomes: list[OutcomeRecord] = Field(default_factory=list)
    results_summary: dict[str, str] = Field(default_factory=dict)
    funding_source: str | None = None
    conflicts_of_interest: str | None = None
    source_spans: dict[str, str] = Field(default_factory=dict)
    extraction_confidence: float | None = Field(
        default=None,
        description="LLM self-reported confidence in the extraction (0.0-1.0).",
    )
    extraction_source: Optional[
        Literal[
            "text",  # abstract / title text only (baseline)
            "sciencedirect",  # full text from ScienceDirect Article Retrieval API
            "sciencedirect_pdf",  # PDF from ScienceDirect (requires SCOPUS_INSTTOKEN)
            "unpaywall_text",  # full text from Unpaywall (HTML/text response)
            "unpaywall_pdf",  # PDF obtained from Unpaywall (used for vision extraction)
            "core",  # full text from CORE (institutional repos)
            "core_pdf",  # PDF from CORE download API
            "europepmc",  # full text from Europe PMC fullTextXML
            "semanticscholar_pdf",  # PDF from Semantic Scholar openAccessPdf
            "arxiv_pdf",  # PDF from arXiv (papers from arXiv connector)
            "biorxiv_medrxiv_pdf",  # PDF from bioRxiv/medRxiv (DOIs 10.1101/...)
            "openalex_content",  # PDF from OpenAlex Content API (paid)
            "crossref_link",  # PDF from Crossref works API link array
            "pmc",  # full text from PubMed Central XML
            "pdf_vision",  # table data extracted via Gemini vision from PDF
            "hybrid",  # merge of text-LLM and PDF-vision outcomes
            "heuristic",  # rule-based extraction fallback
        ]
    ] = Field(
        default="text",
        description=(
            "How outcome data was obtained. 'text' = abstract only (baseline). "
            "Full-text tiers: 'sciencedirect', 'unpaywall_text', 'pmc'. "
            "Vision: 'unpaywall_pdf' -> 'pdf_vision'. "
            "Merged: 'hybrid'. Fallback: 'heuristic'."
        ),
    )
