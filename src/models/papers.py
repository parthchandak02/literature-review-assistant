"""Paper and search result models."""

from __future__ import annotations

import re
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.enums import SourceCategory

# -----------------------------------------------------------------------
# Label-derivation constants (single source of truth).
# All consumers (visualization, citation generation) MUST use
# compute_display_label() rather than reimplementing this logic.
# -----------------------------------------------------------------------

_LABEL_GENERIC_AUTHORS: frozenset[str] = frozenset({
    "unknown", "none", "na", "author", "anonymous", "anon",
})

_LABEL_GENERIC_TITLE_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "being", "with", "this", "that",
    "fig", "figure", "table", "appendix", "section", "chapter",
    "methods", "method", "results", "result", "discussion", "conclusion",
    "conclusions", "introduction", "abstract", "study", "studies",
    "review", "systematic", "literature", "analysis", "impact",
    "effect", "effects", "use", "using", "based", "new", "novel",
    "analysing", "investigating", "usability", "examining", "exploring",
    "evaluating", "evaluation", "assessment", "towards", "toward",
    "role", "applying", "application", "understanding", "comparing",
    "developing", "improving", "educational", "learning", "teaching",
})


class CandidatePaper(BaseModel):
    """A candidate paper retrieved from a literature database.

    display_label is the canonical short identifier computed once on save
    and stored in the DB. All downstream code (RoB figure, citekeys) reads
    this field instead of re-deriving it with local heuristics.
    """

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
    display_label: Optional[str] = None


def compute_display_label(paper: CandidatePaper) -> str:
    """Derive a concise human-readable token for a paper.

    Priority order:
      1. First-author last name (>= 2 alphabetic chars, not a generic placeholder)
      2. First non-generic, non-trivial word from the title (>= 4 alphabetic chars)
      3. Truncated title (first 22 chars + ".." if longer)
      4. "Paper_<paper_id[:6]>" as last resort

    Returns only the name token (no year). Callers append the year in their
    preferred format, e.g. "Smith (2024)" for figures or "Smith2024" for citekeys.
    """
    author_token = ""
    if paper.authors:
        raw = str(paper.authors[0]).split()[0] if str(paper.authors[0]).split() else ""
        token = re.sub(r"[^a-zA-Z]", "", raw)
        if len(token) >= 2 and token.lower() not in _LABEL_GENERIC_AUTHORS:
            author_token = token

    if not author_token and paper.title:
        for word in paper.title.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if len(candidate) >= 4 and candidate.lower() not in _LABEL_GENERIC_TITLE_WORDS:
                author_token = candidate
                break

    if not author_token:
        if paper.title:
            truncated = paper.title[:22].strip()
            if len(paper.title) > 22:
                truncated += ".."
            return truncated
        return f"Paper_{paper.paper_id[:6]}"

    return author_token


class SearchResult(BaseModel):
    workflow_id: str
    database_name: str
    source_category: SourceCategory
    search_date: str
    search_query: str
    limits_applied: Optional[str] = None
    records_retrieved: int
    papers: List[CandidatePaper]
