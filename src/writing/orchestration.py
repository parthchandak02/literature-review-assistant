"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import logging
import re
import unicodedata
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
from src.writing.humanizer_guardrails import apply_deterministic_guardrails
from src.writing.section_writer import SectionWriter

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
        "10.1016/j.jclinepi.2010.04.026",
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
        "https://doi.org/10.1016/j.jclinepi.2010.04.026",
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
_ABSTRACT_FIELDS = ("Background", "Objectives", "Methods", "Results", "Conclusion", "Keywords")
_SECTION_NAMES = frozenset({"introduction", "methods", "results", "discussion", "conclusion", "abstract"})


def _enforce_word_limit(text: str, max_words: int) -> str:
    """Trim text to at most max_words words, cutting at a sentence boundary.

    Splits on sentence-ending punctuation so the result is never mid-sentence.
    Falls back to word-level trim only if no earlier sentence boundary exists.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    # Sentence boundary pattern: period/bang/question followed by whitespace or end.
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    trimmed = " ".join(words[:max_words])
    # Walk backwards from max_words to find a sentence boundary within the trimmed text.
    sentences = sentence_end.split(trimmed)
    if len(sentences) > 1:
        # Drop the trailing incomplete sentence.
        candidate = " ".join(sentences[:-1]).rstrip()
        if candidate:
            logger.debug(
                "Abstract truncated from %d to %d words to meet IEEE limit of %d.",
                len(words),
                len(candidate.split()),
                max_words,
            )
            return candidate
    # No sentence boundary found -- fall back to hard word trim with ellipsis stripped.
    logger.debug(
        "Abstract hard-trimmed from %d to %d words (no sentence boundary found).",
        len(words),
        max_words,
    )
    return trimmed


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
    # Keep manuscript prose ASCII-only for IEEE export robustness.
    sanitized = re.sub(r"[^\x20-\x7E]", " ", sanitized)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    if sanitized != content:
        logger.debug("prose sanitizer replaced snake_case identifiers in section draft")
    return sanitized


def _sanitize_section_headings(section: str, content: str) -> str:
    """Normalize malformed heading lines before section persistence."""
    out_lines: list[str] = []
    last_heading = ""
    section_name = section.strip().lower()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("### ") or stripped.startswith("#### "):
            prefix = "####" if stripped.startswith("#### ") else "###"
            title = stripped[len(prefix) + 1 :].strip()
            # Remove trailing citation list from heading text.
            title = re.sub(r"\s*\[[^\]]+\]\s*$", "", title).strip()
            # Drop known malformed title fragments.
            if title.lower() in _SECTION_NAMES:
                continue
            if title.lower().endswith((" and", " of", " for", " to", " with")):
                continue
            title = re.sub(r"\s{2,}", " ", title).strip(" -:")
            if not title:
                continue
            if title.lower() == last_heading.lower():
                continue
            line = f"{prefix} {title}"
            last_heading = title
        out_lines.append(line)
    return "\n".join(out_lines).strip()


def _strip_unsupported_methods_claims(content: str) -> str:
    """Remove unsupported operational claims that are not in grounding data."""
    cleaned = re.sub(
        r"\b(search strategy|search strategies)\s+(?:was|were)\s+developed\s+in\s+consultation\s+with\s+a\s+medical\s+librarian\b\.?",
        "",
        content,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _ensure_structured_abstract(content: str, research_question: str) -> str:
    """Ensure abstract contains all required structured fields.

    If fields are missing, append deterministic fallback lines so downstream
    markdown/latex extraction always has a complete abstract shape.
    """
    text = content.strip()
    if not text:
        text = "Evidence synthesis was generated from included studies."

    _present = {f: bool(re.search(rf"\*\*{re.escape(f)}:\*\*", text, flags=re.IGNORECASE)) for f in _ABSTRACT_FIELDS}
    if all(_present.values()):
        return text

    defaults = {
        "Background": "This topic has important clinical and implementation implications.",
        "Objectives": f"This systematic review addressed {research_question}.",
        "Methods": (
            "Bibliographic databases were searched according to protocol, with "
            "eligibility screening and risk-of-bias assessment."
        ),
        "Results": "Key findings are reported in the manuscript body and synthesis sections.",
        "Conclusion": "The available evidence is synthesized with certainty and limitations considered.",
        "Keywords": "systematic review, evidence synthesis, implementation, outcomes, methodology",
    }
    _missing_lines = [f"**{field}:** {defaults[field]}" for field in _ABSTRACT_FIELDS if not _present[field]]
    return (text + "\n\n" + "\n".join(_missing_lines)).strip()


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


def _sanitize_citekey_token(raw: str) -> str:
    """Normalize citekey fragments to ASCII-safe token format."""
    normalized = "".join(c for c in unicodedata.normalize("NFD", str(raw or "")) if unicodedata.category(c) != "Mn")
    token = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_")
    token = re.sub(r"_+", "_", token)
    if token.startswith("Paper_") or not token:
        return ""
    if token and token[0].isdigit():
        token = f"Ref_{token}"
    return token


def _make_citekey_base(paper: CandidatePaper, index: int) -> str:
    """Derive a human-readable citekey base from a paper's metadata.

    Uses CandidatePaper.display_label (the canonical DB-stored token) when
    available. Falls back to local derivation for papers from older DBs.
    """
    year_str = str(paper.year) if paper.year else "nd"

    # Preferred path: use the canonical label stored in the DB.
    if paper.display_label:
        from_label = _sanitize_citekey_token(f"{paper.display_label}{year_str}")
        if from_label:
            return from_label[:20]

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
        return f"Ref{index + 1}"

    return _sanitize_citekey_token(f"{author_token}{year_str}")[:20] or f"Ref{index + 1}"


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
            source_type="methodology",
        )
        try:
            await repo.register_citation(record)
            existing.add(citekey)
        except Exception as exc:
            logger.debug("Could not register methodology citation %s: %s", citekey, exc)
    return registered


async def register_background_sr_citations(
    repo: CitationRepository,
    research_question: str,
    keywords: list[str],
    max_results: int = 8,
) -> list[str]:
    """Discover and register background systematic reviews on the same topic.

    Queries Semantic Scholar for highly-cited Review-type papers matching the
    research question keywords, then registers them as citable background references.
    This ensures the Discussion section can cite prior systematic reviews when
    comparing findings, which is required by PRISMA 2020 item 27.

    Returns a list of registered citekeys (may be empty if search fails).
    """
    import os

    import aiohttp

    from src.utils.ssl_context import tcp_connector_with_certifi

    kw_query = " ".join(keywords[:6]) if keywords else research_question[:120]
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    headers: dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key

    registered: list[str] = []
    try:
        params = {
            "query": kw_query,
            "fields": "title,authors,year,externalIds,citationCount,publicationTypes,venue",
            "publicationTypes": "Review",
            "limit": str(max_results * 3),  # over-fetch to allow filtering
        }
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi(), headers=headers) as session:
            async with session.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.debug("Background SR search: Semantic Scholar returned %d", resp.status)
                    return []
                data = await resp.json()

        papers_raw = data.get("data", [])

        # Topic relevance filter: require at least one keyword token to appear
        # in the paper title (case-insensitive). This prevents highly-cited but
        # off-topic reviews from being registered as background SR citations.
        _topic_tokens = {tok.lower() for kw in keywords[:10] for tok in kw.replace("-", " ").split() if len(tok) > 3}
        if not _topic_tokens:
            _topic_tokens = {tok.lower() for tok in research_question.split() if len(tok) > 3}

        def _is_topic_relevant(paper: dict) -> bool:
            title_lower = (paper.get("title") or "").lower()
            return any(tok in title_lower for tok in _topic_tokens)

        papers_relevant = [p for p in papers_raw if _is_topic_relevant(p)]
        # Fall back to unfiltered set if no papers survive the filter (very rare).
        if not papers_relevant:
            papers_relevant = papers_raw
            logger.debug("Background SR topic filter matched 0 papers; falling back to unfiltered set.")

        # Sort by citation count descending; take top max_results
        papers_sorted = sorted(
            papers_relevant,
            key=lambda p: p.get("citationCount") or 0,
            reverse=True,
        )[:max_results]

        existing = set(await repo.get_citekeys())
        for p in papers_sorted:
            title = (p.get("title") or "").strip()
            year = p.get("year")
            if not title or not year:
                continue
            authors_raw = p.get("authors") or []
            authors = [a.get("name", "") for a in authors_raw if a.get("name")]
            doi = (p.get("externalIds") or {}).get("DOI")
            venue = p.get("venue") or ""
            # Build a citekey from first author surname + year.
            # Normalize to ASCII so accented characters (e.g. Perez, not Pérez)
            # do not produce citekeys that regex patterns fail to match.
            first_surname = ""
            if authors:
                name_parts = authors[0].split()
                raw_surname = name_parts[-1] if name_parts else "Author"
                first_surname = "".join(
                    c for c in unicodedata.normalize("NFD", raw_surname) if unicodedata.category(c) != "Mn"
                )
            base_key = f"{first_surname}{year}SR" if first_surname else f"SR{year}"
            citekey = base_key
            suffix = 2
            while citekey in existing:
                citekey = f"{base_key}{suffix}"
                suffix += 1
            sr_url = (p.get("url") or p.get("externalIds", {}).get("URL")) or None
            record = CitationEntryRecord(
                citekey=citekey,
                doi=doi,
                url=str(sr_url) if sr_url else None,
                title=title,
                authors=authors,
                year=year,
                journal=venue or None,
                bibtex=None,
                resolved=True,
                source_type="background_sr",
            )
            try:
                await repo.register_citation(record)
                existing.add(citekey)
                registered.append(citekey)
                logger.info(
                    "Registered background SR: %s (%d citations) -> citekey=%s",
                    title[:60],
                    p.get("citationCount") or 0,
                    citekey,
                )
            except Exception as exc:
                logger.debug("Could not register background SR %s: %s", citekey, exc)

    except Exception as exc:
        logger.warning("Background SR discovery failed: %s", exc)

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
            url=p.url,
            title=p.title or "(No title)",
            authors=p.authors or [],
            year=p.year,
            journal=p.journal,
            bibtex=None,
            resolved=True,
            source_type="included",
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
    word_limit: int | None = None,
    on_llm_call: Callable[..., None] | None = None,
    provider=None,
    grounding: WritingGroundingData | None = None,
    rag_context: str = "",
    prior_sections_context: str = "",
) -> str:
    """Write a section, validate with citation ledger, return content.

    Orchestrates: SectionWriter -> CitationLedger.validate_section.
    The grounding parameter injects real pipeline data into the section
    context so the LLM cannot hallucinate counts or statistics.
    The rag_context parameter appends semantically retrieved chunks from
    the paper embedding store so the LLM has targeted evidence for the section.
    The prior_sections_context parameter injects already-written sections
    (e.g. Results) so that Discussion/Conclusion can build on them rather
    than repeating the same statistics verbatim.
    """
    from src.writing.prompts.sections import get_section_context

    # Build context from grounding data if provided; otherwise use the passed context
    effective_context = get_section_context(section, grounding=grounding) if grounding is not None else context

    # Inject prior-sections context block BEFORE RAG chunks so the LLM
    # sees the narrative spine of already-written sections first.
    if prior_sections_context:
        effective_context = effective_context + "\n\n" + prior_sections_context

    # Append RAG-retrieved evidence chunks when available
    if rag_context:
        effective_context = (
            effective_context
            + "\n\nRAG PRIORITY RULE: For section-specific factual claims, prioritize the retrieved evidence chunks below. "
            + "When a retrieved chunk conflicts with the FACTUAL DATA BLOCK, the FACTUAL DATA BLOCK takes precedence.\n"
            + "\n## Relevant Evidence Chunks (retrieved by semantic search)\n"
            + rag_context
        )

    if provider is not None:
        await provider.reserve_call_slot("writing")
    writer = SectionWriter(
        review=review,
        settings=settings,
        citation_catalog=citation_catalog,
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
    content = _sanitize_section_headings(section, content)
    if section == "methods":
        content = _strip_unsupported_methods_claims(content)

    if section == "abstract":
        content = _ensure_structured_abstract(content, review.research_question)

    # Hard-enforce word limit after generation. The LLM treats the prompt word
    # limit as advisory and will occasionally exceed it (abstract ran to 264 for
    # the IEEE 250-word cap). Trim at the last sentence boundary that keeps the
    # section within the configured limit.
    if word_limit and section == "abstract":
        content = _enforce_word_limit(content, word_limit)

    # Deterministic pre-humanizer guardrails remove repetitive boilerplate while
    # preserving citations and numeric tokens.
    content = apply_deterministic_guardrails(content)

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


def build_background_sr_catalog(
    background_sr_rows: list[tuple[str, str, int | None]],
) -> str:
    """Return citation catalog block for discovered background systematic reviews."""
    lines = []
    for citekey, title, year in background_sr_rows:
        year_str = str(year) if year else "n.d."
        lines.append(f"[{citekey}] {title} ({year_str})")
    return "\n".join(lines)


def prepare_writing_context(
    included_papers: list[CandidatePaper],
    settings: SettingsConfig,
    background_sr_rows: list[tuple[str, str, int | None]] | None = None,
) -> str:
    """Build the citation catalog for the writing phase.

    The catalog includes both included-study citekeys and fixed methodology
    references (PRISMA 2020, GRADE, RoB tools) so the writing LLM can cite
    them in the Methods section.

    Returns the catalog string; style extraction was removed because
    extract_style_patterns always returns empty patterns that are never
    injected into prompts.
    """
    _ = settings  # reserved for future per-agent catalog filtering
    included_catalog = build_citation_catalog_from_papers(included_papers)
    methodology_catalog = build_methodology_catalog()
    background_sr_catalog = build_background_sr_catalog(background_sr_rows or [])
    # Methodology refs appended after included studies; separator makes it clear
    catalog_parts = [included_catalog]
    if background_sr_catalog:
        catalog_parts.append("# Background systematic reviews (for Discussion comparison):")
        catalog_parts.append(background_sr_catalog)
    if methodology_catalog:
        catalog_parts.append("# Methodology references (cite when describing study design, PRISMA, GRADE, RoB):")
        catalog_parts.append(methodology_catalog)
    return "\n".join(catalog_parts)
