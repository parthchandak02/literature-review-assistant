"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    EvidenceLinkRecord,
    ReviewConfig,
    SettingsConfig,
)
from src.writing.section_writer import SectionWriter
from src.writing.style_extractor import StylePatterns, extract_style_patterns

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

logger = logging.getLogger(__name__)


_GENERIC_AUTHOR_TOKENS = frozenset({"unknown", "none", "na", "author", "anonymous", "anon"})

# Fixed methodology references that every systematic review should be able to cite.
# These are registered alongside the included study citations so the writing LLM
# can cite PRISMA 2020, GRADE, and risk-of-bias tools when appropriate.
_METHODOLOGY_REFS: list[tuple[str, str, str, list[str], int, str, str]] = [
    # (citekey, doi, title, authors, year, journal, url)
    (
        "Page2021",
        "10.1136/bmj.n71",
        "PRISMA 2020 explanation and elaboration: updated guidance and exemplars for reporting systematic reviews",
        [
            "Page MJ",
            "Moher D",
            "Bossuyt PM",
            "Boutron I",
            "Hoffmann TC",
            "Mulrow CD",
            "Shamseer L",
            "Tetzlaff JM",
            "Akl EA",
            "McKenzie JE",
        ],
        2021,
        "BMJ",
        "https://doi.org/10.1136/bmj.n71",
    ),
    (
        "Sterne2019",
        "10.1136/bmj.l4898",
        "RoB 2: a revised tool for assessing risk of bias in randomised trials",
        [
            "Sterne JAC",
            "Savovic J",
            "Page MJ",
            "Elbers RG",
            "Blencowe NS",
            "Boutron I",
            "Cates CJ",
            "Cheng HY",
            "Corbett MS",
        ],
        2019,
        "BMJ",
        "https://doi.org/10.1136/bmj.l4898",
    ),
    (
        "Sterne2016",
        "10.1136/bmj.i4919",
        "ROBINS-I: a tool for assessing risk of bias in non-randomised studies of interventions",
        ["Sterne JA", "Hernan MA", "Reeves BC", "Savovic J", "Berkman ND", "Viswanathan M", "Henry D", "Altman DG"],
        2016,
        "BMJ",
        "https://doi.org/10.1136/bmj.i4919",
    ),
    (
        "Guyatt2011",
        "10.1136/bmj.d5647",
        "GRADE guidelines: 1. Introduction-GRADE evidence profiles and summary of findings tables",
        [
            "Guyatt G",
            "Oxman AD",
            "Akl EA",
            "Kunz R",
            "Vist G",
            "Brozek J",
            "Norris S",
            "Falck-Ytter Y",
            "Glasziou P",
            "DeBeer H",
        ],
        2011,
        "J Clin Epidemiol",
        "https://doi.org/10.1136/bmj.d5647",
    ),
    (
        "Cohen1960",
        "10.1177/001316446002000104",
        "A coefficient of agreement for nominal scales",
        ["Cohen J"],
        1960,
        "Educ Psychol Meas",
        "https://doi.org/10.1177/001316446002000104",
    ),
]

# Title words that are too generic to serve as a useful citekey base.
_GENERIC_TITLE_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "with",
        "this",
        "that",
        "fig",
        "figure",
        "table",
        "appendix",
        "section",
        "chapter",
        "methods",
        "method",
        "results",
        "result",
        "discussion",
        "conclusion",
        "conclusions",
        "introduction",
        "abstract",
        "study",
        "studies",
        "review",
        "systematic",
        "literature",
        "analysis",
        "analysing",
        "investigating",
        "usability",
        "examining",
        "exploring",
        "evaluating",
        "evaluation",
        "assessment",
        "towards",
        "toward",
        "role",
        "applying",
        "application",
        "understanding",
        "comparing",
        "developing",
        "improving",
        "educational",
        "learning",
        "teaching",
        "impact",
        "effect",
        "effects",
        "use",
        "using",
        "based",
        "new",
        "novel",
    }
)

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


def _citation_entries_from_papers(papers: list[CandidatePaper]) -> list[tuple[str, CandidatePaper]]:
    """Build (citekey, paper) pairs with unique, human-readable citekeys."""
    seen: set[str] = set()
    result: list[tuple[str, CandidatePaper]] = []
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


def build_citation_catalog_from_papers(papers: list[CandidatePaper]) -> str:
    """Build a simple citation catalog string from included papers for prompts."""
    entries = _citation_entries_from_papers(papers)
    lines = [f"[{citekey}] {p.title} ({p.year or 'n.d.'})" for citekey, p in entries]
    return "\n".join(lines) if lines else "(No papers yet)"


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_CITEKEY_RE = re.compile(r"\[([A-Za-z0-9_:-]+)\]")


async def extract_and_register_claims(
    section: str,
    content: str,
    citation_repo: CitationRepository,
) -> int:
    """Extract cited sentences from written content and register claim->evidence links.

    For each sentence that contains one or more [citekey] references:
    1. Register the sentence as a ClaimRecord in the claims table.
    2. Look up citation_id for each citekey in the citations table.
    3. Create an EvidenceLinkRecord linking the claim to each resolved citation.

    Returns the number of claims registered. Already-registered citekeys that do
    not appear in the citations table are silently skipped (prevents FK violations
    from hallucinated keys that the repair step may not have caught).
    """
    citekey_to_id = await citation_repo.get_citation_map()
    if not citekey_to_id:
        return 0

    # Split content into candidate sentences; fall back to line split for short texts.
    sentences = _SENTENCE_SPLIT_RE.split(content)
    if len(sentences) <= 1:
        sentences = [line.strip() for line in content.splitlines() if line.strip()]

    claims_registered = 0
    for sentence in sentences:
        keys = _CITEKEY_RE.findall(sentence)
        if not keys:
            continue
        resolved_keys = [(k, citekey_to_id[k]) for k in keys if k in citekey_to_id]
        if not resolved_keys:
            continue

        claim = ClaimRecord(
            claim_text=sentence[:2000],
            section=section,
            confidence=1.0,
        )
        try:
            await citation_repo.register_claim(claim)
        except Exception as exc:
            logger.debug("Skipping duplicate or invalid claim for section '%s': %s", section, exc)
            continue

        for citekey, citation_id in resolved_keys:
            link = EvidenceLinkRecord(
                claim_id=claim.claim_id,
                citation_id=citation_id,
                evidence_span=citekey,
                evidence_score=1.0,
            )
            try:
                await citation_repo.link_evidence(link)
            except Exception as exc:
                logger.debug("Failed to link evidence %s -> %s: %s", claim.claim_id, citation_id, exc)

        claims_registered += 1

    return claims_registered


async def register_methodology_citations(repo: CitationRepository) -> list[str]:
    """Register fixed methodology references (PRISMA 2020, GRADE, RoB tools, etc.).

    These citekeys are added to the valid_citekeys list so the writing LLM can
    cite methodology papers alongside the included study references.
    Returns list of newly registered (or already-existing) methodology citekeys.
    """
    existing = set(await repo.get_citekeys())
    registered: list[str] = []
    for citekey, doi, title, authors, year, journal, _url in _METHODOLOGY_REFS:
        registered.append(citekey)
        if citekey in existing:
            continue
        record = CitationEntryRecord(
            citekey=citekey,
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            bibtex=None,
            resolved=True,
        )
        try:
            await repo.register_citation(record)
            existing.add(citekey)
        except Exception as exc:
            logger.debug("Could not register methodology citation %s: %s", citekey, exc)
    return registered


async def register_citations_from_papers(repo: CitationRepository, papers: list[CandidatePaper]) -> None:
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
    grounding: WritingGroundingData | None = None,
    rag_context: str = "",
) -> str:
    """Write a section, validate with citation ledger, return content.

    Orchestrates: SectionWriter -> CitationLedger.validate_section.
    The grounding parameter injects real pipeline data into the section
    context so the LLM cannot hallucinate counts or statistics.
    The rag_context parameter appends semantically retrieved chunks from
    the paper embedding store so the LLM has targeted evidence for the section.
    """
    from src.writing.prompts.sections import get_section_context

    # Build context from grounding data if provided; otherwise use the passed context
    effective_context = get_section_context(section, grounding=grounding) if grounding is not None else context

    # Append RAG-retrieved evidence chunks when available
    if rag_context:
        effective_context = (
            effective_context + "\n\n## Relevant Evidence Chunks (retrieved by semantic search)\n" + rag_context
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
                cache_read_tokens=metadata.cache_read_tokens,
                cache_write_tokens=metadata.cache_write_tokens,
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

    # Register each cited sentence as a claim and link it to evidence so the
    # citation lineage gate can verify full claim->evidence->citation coverage.
    try:
        n_claims = await extract_and_register_claims(section, content, citation_repo)
        if n_claims:
            logger.debug("Registered %d claim-evidence links for section '%s'", n_claims, section)
    except Exception as exc:
        logger.warning("Claim extraction failed for section '%s': %s", section, exc)

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


def build_methodology_catalog() -> str:
    """Return a citation catalog string for the fixed methodology references.

    Appended to the included-study catalog so the writing LLM can cite
    PRISMA 2020, GRADE, and risk-of-bias tools in the Methods section.
    """
    lines = [
        f"[{citekey}] {title} ({year})" for citekey, _doi, title, _authors, year, _journal, _url in _METHODOLOGY_REFS
    ]
    return "\n".join(lines)


def prepare_writing_context(
    included_papers: list[CandidatePaper],
    narrative_synthesis: dict | None,
    settings: SettingsConfig,
) -> tuple[StylePatterns, str]:
    """Prepare style patterns and citation catalog for writing phase.

    The catalog includes both included-study citekeys and fixed methodology
    references (PRISMA 2020, GRADE, RoB tools) so the writing LLM can cite
    them in the Methods section.
    """
    style_enabled = getattr(
        getattr(settings, "writing", None),
        "style_extraction",
        True,
    )
    paper_texts = [(p.abstract or "") + " " + (p.title or "") for p in included_papers]
    if style_enabled:
        patterns = extract_style_patterns(paper_texts)
    else:
        patterns = extract_style_patterns([])
    included_catalog = build_citation_catalog_from_papers(included_papers)
    methodology_catalog = build_methodology_catalog()
    # Methodology refs appended after included studies; separator makes it clear
    catalog_parts = [included_catalog]
    if methodology_catalog:
        catalog_parts.append("# Methodology references (cite when describing study design, PRISMA, GRADE, RoB):")
        catalog_parts.append(methodology_catalog)
    catalog = "\n".join(catalog_parts)
    _ = narrative_synthesis
    return patterns, catalog
