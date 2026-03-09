"""Claim and citation lineage models."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    paper_id: str | None = None
    claim_text: str
    section: str
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceLinkRecord(BaseModel):
    claim_id: str
    citation_id: str
    evidence_span: str
    evidence_score: float = Field(ge=0.0, le=1.0)


class CitationEntryRecord(BaseModel):
    """A single bibliographic entry to be registered in the citations table.

    source_type distinguishes the origin of the citation:
    - 'included': a primary study that was screened in and extracted
    - 'methodology': a fixed methodology reference (PRISMA, GRADE, RoB tools, etc.)
    - 'background_sr': a related systematic review discovered via auxiliary search
    """

    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    citekey: str
    doi: str | None = None
    url: str | None = None
    title: str
    authors: list[str]
    year: int | None = None
    journal: str | None = None
    bibtex: str | None = None
    resolved: bool = False
    source_type: str = "included"
