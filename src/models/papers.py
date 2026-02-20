"""Paper and search result models."""

from __future__ import annotations

import re
import uuid
from typing import List, Optional

from nameparser import HumanName
from pydantic import BaseModel, Field
from wordfreq import zipf_frequency

from src.models.enums import SourceCategory

# -----------------------------------------------------------------------
# Label-derivation constants (single source of truth).
# All consumers (visualization, citation generation) MUST use
# compute_display_label() rather than reimplementing this logic.
#
# Design principle: ZERO topic-specific knowledge is hardcoded here.
# Domain-agnostic filtering uses two industry-standard techniques:
#   1. nameparser.HumanName  -- structured surname extraction (JabRef/Zotero standard)
#   2. wordfreq.zipf_frequency -- corpus-frequency threshold (no hardcoded word lists)
# -----------------------------------------------------------------------

# Zipf scale: log10(occurrences per billion words).
# Words at or above this threshold are common English and skipped as label candidates.
# Calibration: "conversational" ~4.5, "education" ~5.1, "integration" ~4.8 are filtered.
# Rare proper nouns ("Kocaballi", "Rathika") score near 0.0 and pass through.
_ZIPF_COMMON_THRESHOLD: float = 3.5

# Minimal safety net for rare paper-structure abbreviations that have low Zipf
# scores yet are meaningless as labels. "fig" scores ~2.8, below the threshold.
# This list must stay topic-agnostic: only universal bibliographic shorthand.
_UNIVERSAL_PAPER_STRUCTURE: frozenset[str] = frozenset({
    "fig", "et", "al", "ibid", "viz", "cf",
})

# Placeholder strings that nameparser parses as a valid surname but carry no
# information about the actual author. nameparser cannot detect these itself.
_GENERIC_AUTHOR_PLACEHOLDERS: frozenset[str] = frozenset({
    "unknown", "none", "na", "author", "anonymous", "anon",
})


def _is_camelcase_compound(token: str) -> bool:
    """Return True if token is a stripped hyphenated compound word artifact.

    These arise when re.sub strips hyphens from multi-component words:
      "AI-Based"  -> "AIBased"  (two uppercase groups: AI + Based)
      "LLM-based" -> "LLMbased" (LLM + based)
    Simple capitalised names like "Smith" or "Ahmed" return False.
    This check is domain-agnostic: it detects the artifact pattern, not the topic.
    """
    uppercase_runs = re.findall(r"[A-Z][a-z]*", token)
    return len(uppercase_runs) >= 2 and any(c.isupper() for c in token[1:])


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

    Domain-agnostic: no topic-specific words are hardcoded.
    Uses nameparser for structured surname extraction and wordfreq for
    corpus-frequency-based filtering of common English words.

    Priority order:
      1. First-author surname via nameparser.HumanName (handles Dr./Prof./van/de/Jr./III).
      2. First rare word from the title (Zipf < _ZIPF_COMMON_THRESHOLD, >= 4 alpha chars).
      3. Truncated title (first 22 chars) if it yields rare enough alpha content.
      4. "Paper_<paper_id[:6]>" as last resort.

    Returns only the name token (no year). Callers append the year in their
    preferred format, e.g. "Smith (2024)" for figures or "Smith2024" for citekeys.
    """
    # --- Step 1: Extract surname via nameparser ---
    author_token = ""
    if paper.authors:
        parsed = HumanName(str(paper.authors[0]))
        surname = re.sub(r"[^a-zA-Z]", "", parsed.last or "")
        if (
            len(surname) >= 2
            and surname.lower() not in _GENERIC_AUTHOR_PLACEHOLDERS
            and not _is_camelcase_compound(surname)
        ):
            author_token = surname

    # --- Step 2: Title word scan via wordfreq (domain-agnostic) ---
    # Strip non-content prefixes like "[PDF]" or "[EPUB]" before scanning.
    title_for_scan = re.sub(r"^\[([A-Z]+)\]\s*", "", paper.title or "")

    if not author_token and title_for_scan:
        for word in title_for_scan.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if len(candidate) < 4:
                continue
            if _is_camelcase_compound(candidate):
                continue
            low = candidate.lower()
            if zipf_frequency(low, "en") >= _ZIPF_COMMON_THRESHOLD:
                continue
            if low in _UNIVERSAL_PAPER_STRUCTURE:
                continue
            author_token = candidate
            break

    # --- Step 3: Truncated title fallback ---
    if not author_token:
        if title_for_scan:
            truncated = title_for_scan[:22].strip()
            alpha = re.sub(r"[^a-zA-Z]", "", truncated)
            if len(alpha) >= 3 and zipf_frequency(alpha.lower(), "en") < _ZIPF_COMMON_THRESHOLD:
                return truncated + (".." if len(title_for_scan) > 22 else "")
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
