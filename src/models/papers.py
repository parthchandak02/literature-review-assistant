"""Paper and search result models."""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.enums import SourceCategory


class CandidatePaper(BaseModel):
    paper_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    title: str
    authors: List[str]
    year: Optional[int] = None
    source_database: str
    doi: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    keywords: Optional[List[str]] = None
    source_category: SourceCategory = SourceCategory.DATABASE
    openalex_id: Optional[str] = None
    country: Optional[str] = None


class SearchResult(BaseModel):
    workflow_id: str
    database_name: str
    source_category: SourceCategory
    search_date: str
    search_query: str
    limits_applied: Optional[str] = None
    records_retrieved: int
    papers: List[CandidatePaper]
