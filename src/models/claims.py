"""Claim and citation lineage models."""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class ClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    paper_id: Optional[str] = None
    claim_text: str
    section: str
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceLinkRecord(BaseModel):
    claim_id: str
    citation_id: str
    evidence_span: str
    evidence_score: float = Field(ge=0.0, le=1.0)


class CitationEntryRecord(BaseModel):
    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    citekey: str
    doi: Optional[str] = None
    title: str
    authors: List[str]
    year: Optional[int] = None
    journal: Optional[str] = None
    bibtex: Optional[str] = None
    resolved: bool = False
