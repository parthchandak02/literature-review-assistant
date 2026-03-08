"""Forward citation chasing via Semantic Scholar and OpenAlex APIs.

Implements PRISMA 2020 snowball search (citation chasing) for included papers.
After inclusion decisions are finalized, this module fetches papers that cite
each included study (forward citation chasing). Found papers are returned as
CandidatePaper objects with source="citation_chasing" for PRISMA attribution.
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import quote

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_S2_CITATION_URL = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
_OA_CITES_URL = "https://api.openalex.org/works"


class CitationChaser:
    """Find papers that cite an included study (forward citation chasing).

    Uses Semantic Scholar as primary source and OpenAlex as supplementary.
    Papers already in the pipeline (by DOI or title) are deduplicated.
    """

    def __init__(
        self,
        workflow_id: str,
        max_per_paper: int = 25,
        timeout_seconds: int = 20,
    ):
        self.workflow_id = workflow_id
        self.max_per_paper = max_per_paper
        self.timeout_seconds = timeout_seconds
        self.s2_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

    async def chase_citations(
        self,
        included_papers: list[CandidatePaper],
        known_doi_set: set[str],
        concurrency: int = 5,
    ) -> list[CandidatePaper]:
        """Return new candidate papers citing any of the included papers.

        Parameters
        ----------
        included_papers:
            Papers that passed full-text inclusion.
        known_doi_set:
            Set of DOIs already in the pipeline (to avoid re-adding duplicates).
            Pass an empty set if no deduplication is needed.
        concurrency:
            Maximum number of included papers chased simultaneously.

        Returns
        -------
        list[CandidatePaper]
            New papers not already in the pipeline, tagged with
            source_database="citation_chasing" and source_category=OTHER_SOURCE.
        """
        seen_dois: set[str] = set(doi.lower().strip() for doi in known_doi_set if doi)
        # Snapshot of known DOIs for each task -- tasks run in parallel so each
        # gets the initial set; cross-paper dedup is performed after gather.
        initial_seen = set(seen_dois)
        sem = asyncio.Semaphore(concurrency)

        async def _chase_with_sem(paper: CandidatePaper) -> list[CandidatePaper]:
            async with sem:
                try:
                    return await self._chase_one(paper, set(initial_seen))
                except Exception as exc:
                    logger.warning(
                        "Citation chasing failed for %s: %s",
                        paper.paper_id[:12],
                        exc,
                    )
                    return []

        results_per_paper = await asyncio.gather(
            *[_chase_with_sem(p) for p in included_papers],
            return_exceptions=True,
        )

        # Merge all results with cross-paper deduplication
        found: list[CandidatePaper] = []
        for batch in results_per_paper:
            if isinstance(batch, BaseException):
                continue
            for p in batch:
                doi_key = p.doi.lower().strip() if p.doi else None
                if doi_key and doi_key in seen_dois:
                    continue
                found.append(p)
                if doi_key:
                    seen_dois.add(doi_key)

        return found

    async def chase_citations_to_search_results(
        self,
        included_papers: list[CandidatePaper],
        known_doi_set: set[str],
        concurrency: int = 5,
    ) -> list[SearchResult]:
        """Wrap chase_citations output as SearchResult objects for PRISMA counting."""
        from datetime import date

        all_papers = await self.chase_citations(included_papers, known_doi_set, concurrency=concurrency)
        if not all_papers:
            return []
        return [
            SearchResult(
                workflow_id=self.workflow_id,
                database_name="citation_chasing",
                source_category=SourceCategory.OTHER_SOURCE,
                search_date=date.today().isoformat(),
                search_query="forward_citation_chasing",
                limits_applied=f"max_per_paper={self.max_per_paper}",
                records_retrieved=len(all_papers),
                papers=all_papers,
            )
        ]

    async def _chase_one(
        self,
        paper: CandidatePaper,
        seen_dois: set[str],
    ) -> list[CandidatePaper]:
        """Chase citations for a single included paper.

        Runs Semantic Scholar and OpenAlex in parallel (each with a snapshot of
        seen_dois). Results are merged and deduplicated before returning.
        """
        # Run both sources concurrently; pass separate copies so internal dedup
        # within each source is independent and there is no cross-source race.
        s2_coro = self._chase_semantic_scholar(paper, set(seen_dois))
        oa_coro = self._chase_openalex(paper, set(seen_dois)) if paper.doi else None

        if oa_coro is not None:
            s2_raw, oa_raw = await asyncio.gather(s2_coro, oa_coro, return_exceptions=True)
        else:
            s2_raw = await s2_coro
            oa_raw = []

        s2_results: list[CandidatePaper] = [] if isinstance(s2_raw, BaseException) else s2_raw
        oa_results: list[CandidatePaper] = [] if isinstance(oa_raw, BaseException) else oa_raw

        # Merge with dedup -- S2 takes precedence, OA fills gaps
        merged_dois: set[str] = set()
        results: list[CandidatePaper] = []
        for p in s2_results + oa_results:
            doi_key = p.doi.lower().strip() if p.doi else None
            if doi_key and doi_key in merged_dois:
                continue
            results.append(p)
            if doi_key:
                merged_dois.add(doi_key)

        return results

    async def _chase_semantic_scholar(
        self,
        paper: CandidatePaper,
        seen_dois: set[str],
    ) -> list[CandidatePaper]:
        """Fetch citing papers from Semantic Scholar."""
        # Build paper identifier: prefer DOI, fall back to title search
        s2_id = f"DOI:{quote(paper.doi)}" if paper.doi else None
        if not s2_id:
            return []

        headers: dict[str, str] = {}
        if self.s2_api_key:
            headers["x-api-key"] = self.s2_api_key

        url = _S2_CITATION_URL.format(paper_id=s2_id)
        params = {
            "fields": "title,authors,year,externalIds,abstract,openAccessPdf",
            "limit": self.max_per_paper,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(
                headers=headers, timeout=timeout, connector=tcp_connector_with_certifi()
            ) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
        except Exception as exc:
            logger.debug("Semantic Scholar citation chase failed: %s", exc)
            return []

        papers: list[CandidatePaper] = []
        for item in data.get("data", []):
            citing = item.get("citingPaper") or {}
            doi = (citing.get("externalIds") or {}).get("DOI")
            if doi and doi.lower().strip() in seen_dois:
                continue
            title = str(citing.get("title") or "").strip()
            if not title:
                continue
            authors = [str(a.get("name") or "") for a in citing.get("authors") or [] if a.get("name")]
            year = citing.get("year")
            oa_pdf = (citing.get("openAccessPdf") or {}).get("url")
            candidate = CandidatePaper(
                title=title,
                authors=authors or ["Unknown"],
                year=int(year) if year else None,
                source_database="citation_chasing",
                doi=doi,
                abstract=citing.get("abstract"),
                url=oa_pdf,
                source_category=SourceCategory.OTHER_SOURCE,
            )
            papers.append(candidate)
            if doi:
                seen_dois.add(doi.lower().strip())
        return papers

    async def _chase_openalex(
        self,
        paper: CandidatePaper,
        seen_dois: set[str],
    ) -> list[CandidatePaper]:
        """Fetch citing papers from OpenAlex."""
        if not paper.doi:
            return []

        openalex_doi = f"https://doi.org/{paper.doi}"
        params = {
            "filter": f"cites:{openalex_doi}",
            "per-page": self.max_per_paper,
            "select": "title,authorships,publication_year,doi,abstract_inverted_index",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout, connector=tcp_connector_with_certifi()) as session:
                async with session.get(_OA_CITES_URL, params=params) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
        except Exception as exc:
            logger.debug("OpenAlex citation chase failed: %s", exc)
            return []

        papers: list[CandidatePaper] = []
        for item in data.get("results") or []:
            doi_raw = item.get("doi") or ""
            doi = doi_raw.replace("https://doi.org/", "").strip() or None
            if doi and doi.lower().strip() in seen_dois:
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            authors = [
                str(a.get("author", {}).get("display_name") or "")
                for a in item.get("authorships") or []
                if a.get("author", {}).get("display_name")
            ]
            year = item.get("publication_year")
            candidate = CandidatePaper(
                title=title,
                authors=authors or ["Unknown"],
                year=int(year) if year else None,
                source_database="citation_chasing",
                doi=doi,
                abstract=None,
                url=doi_raw if doi_raw.startswith("https://doi.org/") else None,
                source_category=SourceCategory.OTHER_SOURCE,
            )
            papers.append(candidate)
            if doi:
                seen_dois.add(doi.lower().strip())
        return papers
