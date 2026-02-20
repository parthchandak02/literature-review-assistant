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
    # Honorific prefixes that appear as first-word tokens
    "dr", "prof", "mr", "ms", "mrs", "mx", "sir",
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
    # Domain-specific words common as title openers in AI/education research
    "conversational", "tutor", "tutors", "chatbot", "chatbots",
    "integration", "pedagogical", "effectiveness", "agent", "agents",
    "intelligent", "adaptive", "virtual", "digital", "interactive",
    "personalized", "automated", "generative", "framework", "approach",
    "survey", "overview", "scoping", "narrative", "mixed",
    # Additional adjectives/verbs that appear as de-hyphenated artifacts or
    # generic descriptor words picked up from AI/education titles
    "human", "humancentered", "centered", "enhanced", "enhance",
    "enhancing", "different", "simple", "nursing", "academic",
    "student", "students", "teacher", "teachers", "classroom",
    "engagement", "performance", "outcomes", "experience", "feedback",
    # Question/connector words that slip through short-word filters
    "what", "how", "why", "when", "where", "which", "who", "whom",
    "actually", "does", "can", "could", "would", "should",
    # Common education/research domain words
    "education", "training", "course", "courses", "curriculum",
    "technology", "system", "systems", "tool", "tools", "platform",
    "data", "model", "models", "approach", "approaches",
})


def _is_camelcase_compound(token: str) -> bool:
    """Return True if token looks like a stripped hyphenated compound word.

    Examples that should be skipped: AIPowered, LLMbased, AIBased,
    AIdriven, Humancentered (contains multiple uppercase runs).
    Simple capitalised words like 'Smith' or 'Ahmed' return False.
    """
    uppercase_runs = re.findall(r"[A-Z][a-z]*", token)
    # Two or more capitalised groups AND at least one uppercase after position 0
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

    Priority order:
      1. First-author surname: try first word then last word of authors[0],
         filtering generic placeholders, honorifics, and camelCase artifacts.
      2. First non-generic, non-compound word from the title (>= 4 alphabetic chars).
      3. Truncated title (first 22 chars) only when it yields enough alpha chars
         and is not itself a generic word -- otherwise falls to step 4.
      4. "Paper_<paper_id[:6]>" as last resort.

    Returns only the name token (no year). Callers append the year in their
    preferred format, e.g. "Smith (2024)" for figures or "Smith2024" for citekeys.
    """
    author_token = ""
    if paper.authors:
        first_author = str(paper.authors[0])
        words = first_author.split()
        # Try first word, then last word (handles "First Last" and "Last, First")
        candidates = [words[0]] if words else []
        if len(words) > 1:
            candidates.append(words[-1])
        for raw in candidates:
            token = re.sub(r"[^a-zA-Z]", "", raw)
            if (
                len(token) >= 2
                and token.lower() not in _LABEL_GENERIC_AUTHORS
                and not _is_camelcase_compound(token)
            ):
                author_token = token
                break

    # Strip common non-content prefixes ("[PDF]", "[EPUB]", etc.) before
    # scanning title words so they do not end up in the fallback label.
    title_for_scan = re.sub(r"^\[([A-Z]+)\]\s*", "", paper.title or "")

    if not author_token and title_for_scan:
        for word in title_for_scan.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if (
                len(candidate) >= 4
                and candidate.lower() not in _LABEL_GENERIC_TITLE_WORDS
                and not _is_camelcase_compound(candidate)
            ):
                author_token = candidate
                break

    if not author_token:
        if title_for_scan:
            truncated = title_for_scan[:22].strip()
            # Only use the truncated title if it carries enough real alpha content
            # and is not itself a single generic word.
            alpha_chars = re.sub(r"[^a-zA-Z]", "", truncated)
            if (
                len(alpha_chars) >= 3
                and alpha_chars.lower() not in _LABEL_GENERIC_TITLE_WORDS
            ):
                if len(title_for_scan) > 22:
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
