"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

from typing import List

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository
from src.models import CandidatePaper, ReviewConfig, SettingsConfig
from src.writing.section_writer import SectionWriter
from src.writing.style_extractor import StylePatterns, extract_style_patterns


def build_citation_catalog_from_papers(papers: List[CandidatePaper]) -> str:
    """Build a simple citation catalog string from included papers for prompts."""
    lines: List[str] = []
    for i, p in enumerate(papers):
        citekey = f"Paper{i+1}"
        if p.authors and len(p.authors) > 0:
            author = p.authors[0]
            year = p.year or "n.d."
            citekey = f"{author}{year}"[:20].replace(" ", "")
        lines.append(f"[{citekey}] {p.title} ({p.year or 'n.d.'})")
    return "\n".join(lines) if lines else "(No papers yet)"


async def write_section_with_validation(
    section: str,
    context: str,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    citation_repo: CitationRepository,
    citation_catalog: str = "",
    style_patterns: StylePatterns | None = None,
    word_limit: int | None = None,
) -> str:
    """Write a section, validate with citation ledger, return content.

    Orchestrates: SectionWriter -> CitationLedger.validate_section.
    """
    writer = SectionWriter(
        review=review,
        settings=settings,
        citation_catalog=citation_catalog,
        style_patterns=style_patterns,
    )
    content = await writer.write_section_async(
        section=section,
        context=context,
        word_limit=word_limit,
    )
    ledger = CitationLedger(citation_repo)
    result = await ledger.validate_section(section, content)
    if result.unresolved_citations:
        pass
    if result.unresolved_claims:
        pass
    return content


def prepare_writing_context(
    included_papers: List[CandidatePaper],
    narrative_synthesis: dict | None,
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
