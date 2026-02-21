"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository
from src.models import CandidatePaper, CitationEntryRecord, ReviewConfig, SettingsConfig
from src.writing.section_writer import SectionWriter
from src.writing.style_extractor import StylePatterns, extract_style_patterns

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

logger = logging.getLogger(__name__)


_GENERIC_AUTHOR_TOKENS = frozenset({"unknown", "none", "na", "author", "anonymous", "anon"})

# Title words that are too generic to serve as a useful citekey base.
_GENERIC_TITLE_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "being", "with", "this", "that",
    "fig", "figure", "table", "appendix", "section", "chapter",
    "methods", "method", "results", "result", "discussion", "conclusion",
    "conclusions", "introduction", "abstract", "study", "studies",
    "review", "systematic", "literature", "analysis", "analysing",
    "investigating", "usability", "examining", "exploring", "evaluating",
    "evaluation", "assessment", "towards", "toward", "role", "applying",
    "application", "understanding", "comparing", "developing", "improving",
    "educational", "learning", "teaching", "impact", "effect", "effects",
    "use", "using", "based", "new", "novel",
})

# Matches lowercase_with_underscores that appear in prose (not inside brackets).
# We split text around [...] blocks first so citation keys are never touched.
_SNAKE_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\b")


def _sanitize_prose(content: str) -> str:
    """Replace any remaining snake_case identifiers in prose with spaced equivalents.

    Citation keys inside [...] brackets are explicitly preserved because they
    are split out before substitution and re-joined afterwards. This is a
    safety net; the LLM should not produce snake_case given correct prompting.
    """
    # Split on [...] blocks; odd-indexed chunks are inside brackets.
    parts = re.split(r"(\[[^\]]*\])", content)
    result = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # Inside a bracket -- preserve exactly as-is (citation key or figure ref)
            result.append(part)
        else:
            result.append(_SNAKE_RE.sub(lambda m: m.group(0).replace("_", " "), part))
    sanitized = "".join(result)
    if sanitized != content:
        logger.debug("prose sanitizer replaced snake_case identifiers in section draft")
    return sanitized


def _clean_author_token(raw: str) -> str:
    """Extract a clean alphabetic token from an author string.

    Returns an empty string if the author value is a generic placeholder
    (e.g. 'Unknown', 'None', 'N/A') or a single-letter initial that would
    produce an ugly citekey.
    """
    token = re.sub(r"[^a-zA-Z]", "", str(raw).split()[0] if str(raw).split() else "")
    # Require at least 2 chars to avoid single-letter initials like "R"
    if len(token) < 2 or token.lower() in _GENERIC_AUTHOR_TOKENS:
        return ""
    return token


def _make_citekey_base(paper: CandidatePaper, index: int) -> str:
    """Derive a human-readable citekey base from a paper's metadata.

    Uses CandidatePaper.display_label (the canonical DB-stored token) when
    available. Falls back to local derivation for papers from older DBs.
    """
    year_str = str(paper.year) if paper.year else "nd"

    # Preferred path: use the canonical label stored in the DB.
    if paper.display_label:
        return f"{paper.display_label}{year_str}"[:20]

    # Fallback for papers from older DBs without display_label.
    author_token = ""
    if paper.authors:
        author_token = _clean_author_token(str(paper.authors[0]))

    if not author_token and paper.title:
        for word in paper.title.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if len(candidate) >= 4 and candidate.lower() not in _GENERIC_TITLE_WORDS:
                author_token = candidate
                break

    if not author_token:
        return f"Paper{index + 1}"

    return f"{author_token}{year_str}"[:20]


def _citation_entries_from_papers(papers: List[CandidatePaper]) -> List[Tuple[str, CandidatePaper]]:
    """Build (citekey, paper) pairs with unique, human-readable citekeys."""
    seen: Set[str] = set()
    result: List[Tuple[str, CandidatePaper]] = []
    for i, p in enumerate(papers):
        base = _make_citekey_base(p, i)
        citekey = base
        idx = 1
        while citekey in seen:
            citekey = f"{base}_{idx}"
            idx += 1
        seen.add(citekey)
        result.append((citekey, p))
    return result


def build_citation_catalog_from_papers(papers: List[CandidatePaper]) -> str:
    """Build a simple citation catalog string from included papers for prompts."""
    entries = _citation_entries_from_papers(papers)
    lines = [f"[{citekey}] {p.title} ({p.year or 'n.d.'})" for citekey, p in entries]
    return "\n".join(lines) if lines else "(No papers yet)"


async def register_citations_from_papers(repo: CitationRepository, papers: List[CandidatePaper]) -> None:
    """Pre-register citations for included papers so validate_section passes.
    Skips citekeys already in DB (idempotent for resume)."""
    existing = set(await repo.get_citekeys())
    entries = _citation_entries_from_papers(papers)
    for citekey, p in entries:
        if citekey in existing:
            continue
        record = CitationEntryRecord(
            citekey=citekey,
            doi=p.doi,
            title=p.title or "(No title)",
            authors=p.authors or [],
            year=p.year,
            journal=None,
            bibtex=None,
            resolved=True,
        )
        await repo.register_citation(record)
        existing.add(citekey)


async def write_section_with_validation(
    section: str,
    context: str,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    citation_repo: CitationRepository,
    citation_catalog: str = "",
    style_patterns: Optional[StylePatterns] = None,
    word_limit: Optional[int] = None,
    on_llm_call: Optional[Callable[..., None]] = None,
    provider=None,
    grounding: Optional["WritingGroundingData"] = None,
) -> str:
    """Write a section, validate with citation ledger, return content.

    Orchestrates: SectionWriter -> CitationLedger.validate_section.
    The grounding parameter injects real pipeline data into the section
    context so the LLM cannot hallucinate counts or statistics.
    """
    from src.writing.prompts.sections import get_section_context

    # Build context from grounding data if provided; otherwise use the passed context
    effective_context = (
        get_section_context(section, grounding=grounding)
        if grounding is not None
        else context
    )

    writer = SectionWriter(
        review=review,
        settings=settings,
        citation_catalog=citation_catalog,
        style_patterns=style_patterns,
    )
    content, metadata = await writer.write_section_async(
        section=section,
        context=effective_context,
        word_limit=word_limit,
    )
    if provider and metadata.cost_usd is not None:
        try:
            await provider.log_cost(
                model=metadata.model,
                tokens_in=metadata.tokens_in,
                tokens_out=metadata.tokens_out,
                cost_usd=metadata.cost_usd,
                latency_ms=metadata.latency_ms,
                phase="phase_6_writing",
            )
        except Exception as _log_exc:
            logger.warning("Failed to persist writing cost for section '%s': %s", section, _log_exc)
    if on_llm_call:
        word_count = len(content.split())
        on_llm_call(
            source="writing",
            status="success",
            details=section,
            records=None,
            call_type="llm_writing",
            raw_response=content,
            latency_ms=metadata.latency_ms,
            model=metadata.model,
            paper_id=None,
            phase="phase_6_writing",
            tokens_in=metadata.tokens_in,
            tokens_out=metadata.tokens_out,
            cost_usd=metadata.cost_usd,
            section_name=section,
            word_count=word_count,
        )
    # Safety-net: replace any leftover snake_case in prose before saving.
    content = _sanitize_prose(content)

    ledger = CitationLedger(citation_repo)
    result = await ledger.validate_section(section, content)
    if result.unresolved_citations:
        logger.warning(
            "Section '%s' contains %d unresolved citation key(s): %s",
            section,
            len(result.unresolved_citations),
            ", ".join(result.unresolved_citations[:10]),
        )
    if result.unresolved_claims:
        logger.warning(
            "Section '%s' has %d claim(s) without linked evidence.",
            section,
            len(result.unresolved_claims),
        )
    return content


def prepare_writing_context(
    included_papers: List[CandidatePaper],
    narrative_synthesis: Optional[dict],
    settings: SettingsConfig,
) -> tuple[StylePatterns, str]:
    """Prepare style patterns and citation catalog for writing phase."""
    style_enabled = getattr(
        getattr(settings, "writing", None),
        "style_extraction",
        True,
    )
    paper_texts = [
        (p.abstract or "") + " " + (p.title or "")
        for p in included_papers
    ]
    if style_enabled:
        patterns = extract_style_patterns(paper_texts)
    else:
        patterns = extract_style_patterns([])
    catalog = build_citation_catalog_from_papers(included_papers)
    _ = narrative_synthesis
    return patterns, catalog
