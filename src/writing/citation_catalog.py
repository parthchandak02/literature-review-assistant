"""Citation catalog construction, citekey derivation, and citation registration."""

from __future__ import annotations

import logging
import re
import unicodedata

from src.db.repositories import CitationRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    StructuredSectionDraft,
)

logger = logging.getLogger(__name__)

_GENERIC_AUTHOR_TOKENS = frozenset({"unknown", "none", "na", "author", "anonymous", "anon"})

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

_METHODOLOGY_REFS: list[tuple[str, str, str, list[str], int, str, str]] = [
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


def _clean_author_token(raw: str) -> str:
    """Extract a clean alphabetic token from an author string.

    Returns an empty string if the author value is a generic placeholder
    (e.g. 'Unknown', 'None', 'N/A') or a single-letter initial that would
    produce an ugly citekey.
    """
    token = re.sub(r"[^a-zA-Z]", "", str(raw).split()[0] if str(raw).split() else "")
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

    if paper.display_label:
        from_label = _sanitize_citekey_token(f"{paper.display_label}{year_str}")
        if from_label:
            return from_label[:20]

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


def _extract_valid_citekeys(citation_catalog: str) -> set[str]:
    keys: set[str] = set()
    for line in citation_catalog.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            keys.add(stripped[1 : stripped.index("]")].strip())
    return keys


def _extract_included_study_citekeys(citation_catalog: str) -> set[str]:
    """Extract citekeys from the INCLUDED STUDIES portion of the catalog only."""
    keys: set[str] = set()
    in_included_block = False
    for line in citation_catalog.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if "INCLUDED STUDIES" in upper or "CITATION COVERAGE" in upper:
            in_included_block = True
            continue
        if in_included_block and ("METHODOLOGY" in upper or "BACKGROUND" in upper):
            in_included_block = False
            continue
        if in_included_block and stripped.startswith("[") and "]" in stripped:
            keys.add(stripped[1 : stripped.index("]")].strip())
    return keys


def _compute_section_citation_budget(
    section: str,
    citation_catalog: str,
    valid_citekeys: set[str],
) -> set[str]:
    """Return the set of citekeys that a section MUST cite.

    - results: all included study citekeys (every study must appear)
    - discussion, methods, introduction, abstract, conclusion: no mandatory budget
    """
    if section != "results":
        return set()
    included_keys = _extract_included_study_citekeys(citation_catalog)
    return included_keys & valid_citekeys


def _citation_coverage_issues(
    section: str,
    draft: StructuredSectionDraft,
    must_cite: set[str],
) -> tuple[list[str], set[str]]:
    """Check which must-cite keys are missing from the draft.

    Returns (issue_descriptions, missing_keys).
    """
    if not must_cite:
        return [], set()
    cited_in_draft = set(draft.cited_keys or [])
    for block in draft.blocks:
        cited_in_draft.update(block.citations or [])
    cited_in_draft.update(
        re.findall(
            r"\[([A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?)\]",
            " ".join(b.text for b in draft.blocks),
        )
    )
    missing = must_cite - cited_in_draft
    if not missing:
        return [], set()
    issues = [f"missing_required_citations:{len(missing)}"]
    return issues, missing


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
    query_keyword_limit: int = 6,
    topic_token_keyword_limit: int = 10,
    request_timeout_seconds: int = 20,
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

    query_keyword_limit = max(1, int(query_keyword_limit))
    topic_token_keyword_limit = max(1, int(topic_token_keyword_limit))
    request_timeout_seconds = max(5, int(request_timeout_seconds))
    kw_query = " ".join(keywords[:query_keyword_limit]) if keywords else research_question[:120]
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
            "limit": str(max_results * 3),
        }
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi(), headers=headers) as session:
            async with session.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=request_timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    logger.debug("Background SR search: Semantic Scholar returned %d", resp.status)
                    return []
                data = await resp.json()

        papers_raw = data.get("data", [])

        _topic_tokens = {
            tok.lower()
            for kw in keywords[:topic_token_keyword_limit]
            for tok in kw.replace("-", " ").split()
            if len(tok) > 3
        }
        if not _topic_tokens:
            _topic_tokens = {tok.lower() for tok in research_question.split() if len(tok) > 3}

        _min_token_matches = 2 if len(_topic_tokens) >= 4 else 1

        def _is_topic_relevant(paper: dict) -> bool:
            title_lower = (paper.get("title") or "").lower()
            matched = sum(1 for tok in _topic_tokens if tok in title_lower)
            return matched >= _min_token_matches

        papers_relevant = [p for p in papers_raw if _is_topic_relevant(p)]
        _filtered_out = [p for p in papers_raw if not _is_topic_relevant(p)]
        if _filtered_out:
            logger.info(
                "Background SR relevance filter excluded %d of %d candidates: %s",
                len(_filtered_out),
                len(papers_raw),
                "; ".join((p.get("title") or "?")[:60] for p in _filtered_out[:5]),
            )
        if not papers_relevant:
            logger.info(
                "Background SR topic filter matched 0 of %d papers; returning empty to avoid off-topic citations.",
                len(papers_raw),
            )
            return []

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
