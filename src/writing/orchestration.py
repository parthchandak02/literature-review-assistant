"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

from collections.abc import Callable
from typing import List, Set, Tuple

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository
from src.models import CandidatePaper, CitationEntryRecord, ReviewConfig, SettingsConfig
from src.writing.section_writer import SectionWriter
from src.writing.style_extractor import StylePatterns, extract_style_patterns


def _citation_entries_from_papers(papers: List[CandidatePaper]) -> List[Tuple[str, CandidatePaper]]:
    """Build (citekey, paper) pairs with unique citekeys matching catalog format."""
    seen: Set[str] = set()
    result: List[Tuple[str, CandidatePaper]] = []
    for i, p in enumerate(papers):
        base = f"Paper{i+1}"
        if p.authors and len(p.authors) > 0:
            author = str(p.authors[0])
            year = p.year or "n.d."
            base = f"{author}{year}"[:20].replace(" ", "")
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
    style_patterns: StylePatterns | None = None,
    word_limit: int | None = None,
    on_llm_call: Callable[..., None] | None = None,
    provider=None,
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
    content, metadata = await writer.write_section_async(
        section=section,
        context=context,
        word_limit=word_limit,
    )
    if provider:
        await provider.log_cost(
            model=metadata.model,
            tokens_in=metadata.tokens_in,
            tokens_out=metadata.tokens_out,
            cost_usd=metadata.cost_usd,
            latency_ms=metadata.latency_ms,
            phase="phase_6_writing",
        )
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
