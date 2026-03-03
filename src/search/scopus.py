"""Elsevier Scopus connector.

Uses the Scopus Search API (https://api.elsevier.com/content/search/scopus)
with TITLE-ABS-KEY field-code queries and PUBYEAR date filtering.

Rate limit: 6 req/sec (Elsevier official). We sleep 0.2s between pages to
stay safely under that ceiling. Pagination uses start + count params;
maximum 25 records per page (Scopus API page-size limit without TDM token).

Known limitation: the Scopus Search API does not return dc:description
(abstract) for most key tiers -- even with view=STANDARD. As a result,
Scopus papers have abstract=None after the search phase. The standalone
enrich_scopus_abstracts() function attempts to backfill abstracts via the
ScienceDirect Abstract API (/content/abstract/doi/{doi}) for papers that
have a DOI. Callers should invoke it after dedup.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elsevier.com/content/search/scopus"
_PAGE_SIZE = 25  # safe page size without institutional TDM token
_RATE_SLEEP = 0.2  # 5 req/sec -- safely under the 6 req/sec official limit


class ScopusConnector:
    """Search Elsevier Scopus using the official Search API.

    Authentication: API key only (no insttoken required for search).
    Full-text retrieval requires an insttoken, but title/abstract/DOI
    metadata is freely available with an API key.
    """

    name = "scopus"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        api_key = os.getenv("SCOPUS_API_KEY")
        if not api_key:
            raise ValueError("SCOPUS_API_KEY is required for the Scopus connector")
        self._api_key = api_key.strip()

    @staticmethod
    def _parse_authors(entry: dict[str, Any]) -> list[str]:
        """Extract author names from a Scopus search entry."""
        authors: list[str] = []
        author_block = entry.get("author", [])
        if isinstance(author_block, list):
            for a in author_block:
                name = a.get("authname") or a.get("ce:indexed-name") or ""
                if name:
                    authors.append(str(name))
        elif isinstance(author_block, dict):
            name = author_block.get("authname") or author_block.get("ce:indexed-name") or ""
            if name:
                authors.append(str(name))
        # Fall back to dc:creator (first author only)
        if not authors:
            creator = entry.get("dc:creator", "")
            if creator:
                authors.append(str(creator))
        return authors or ["Unknown"]

    @staticmethod
    def _parse_year(entry: dict[str, Any]) -> int | None:
        """Parse publication year from coverDate (YYYY-MM-DD) or coverDisplayDate."""
        cover_date = entry.get("prism:coverDate", "")
        if cover_date and len(cover_date) >= 4:
            try:
                return int(cover_date[:4])
            except ValueError:
                pass
        display = entry.get("prism:coverDisplayDate", "")
        if display:
            for token in display.split():
                if token.isdigit() and len(token) == 4:
                    try:
                        return int(token)
                    except ValueError:
                        pass
        return None

    @staticmethod
    def _to_candidate(entry: dict[str, Any]) -> CandidatePaper:
        title = str(entry.get("dc:title") or "Untitled")
        doi = entry.get("prism:doi") or None
        abstract = entry.get("dc:description") or None
        url = entry.get("prism:url") or None
        journal = entry.get("prism:publicationName") or None
        year = ScopusConnector._parse_year(entry)
        authors = ScopusConnector._parse_authors(entry)
        return CandidatePaper(
            title=title,
            authors=authors,
            year=year,
            source_database="scopus",
            doi=str(doi) if doi else None,
            abstract=str(abstract) if abstract else None,
            url=str(url) if url else None,
            journal=str(journal) if journal else None,
            source_category=SourceCategory.DATABASE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 500,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        """Run a Scopus search and return all results up to max_results."""
        papers: list[CandidatePaper] = []
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }

        # Build full query with date filters if not already embedded
        full_query = query
        if date_start and "PUBYEAR" not in query:
            full_query += f" AND PUBYEAR > {date_start - 1}"
        if date_end and "PUBYEAR" not in query:
            full_query += f" AND PUBYEAR < {date_end + 1}"

        start = 0
        total_results: int | None = None

        async with aiohttp.ClientSession(
            connector=tcp_connector_with_certifi(),
            headers=headers,
        ) as session:
            while True:
                if total_results is not None and start >= total_results:
                    break
                if len(papers) >= max_results:
                    break

                params = {
                    "query": full_query,
                    "count": str(_PAGE_SIZE),
                    "start": str(start),
                    "field": "dc:title,prism:doi,prism:coverDate,prism:coverDisplayDate,"
                    "prism:publicationName,dc:description,dc:creator,author,"
                    "prism:url,dc:identifier",
                }

                try:
                    async with session.get(
                        _BASE_URL,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 429:
                            logger.warning("Scopus rate limit hit -- sleeping 2s")
                            await asyncio.sleep(2.0)
                            continue
                        if resp.status != 200:
                            body = await resp.text()
                            logger.warning("Scopus returned HTTP %d: %s", resp.status, body[:200])
                            break
                        payload = await resp.json(content_type=None)
                except Exception as exc:
                    logger.warning("Scopus request failed (start=%d): %s", start, exc)
                    break

                sr = payload.get("search-results", {})

                if total_results is None:
                    try:
                        total_results = int(sr.get("opensearch:totalResults", 0))
                        logger.info(
                            "Scopus: %d total results for query (retrieving up to %d)",
                            total_results,
                            max_results,
                        )
                    except (ValueError, TypeError):
                        total_results = 0

                entries = sr.get("entry", [])
                if not entries:
                    break

                # Scopus returns {"error": "Result set was empty"} as a single entry
                if isinstance(entries, list) and len(entries) == 1:
                    if "error" in entries[0]:
                        logger.info("Scopus: empty result set")
                        break

                for entry in entries:
                    if len(papers) >= max_results:
                        break
                    try:
                        papers.append(self._to_candidate(entry))
                    except Exception as exc:
                        logger.debug("Scopus: skipped malformed entry: %s", exc)

                start += len(entries)
                # Respect rate limit between pages
                await asyncio.sleep(_RATE_SLEEP)

        logger.info(
            "Scopus connector retrieved %d papers (query length=%d chars)",
            len(papers),
            len(full_query),
        )
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=full_query,
            limits_applied=f"max_results={max_results}",
            records_retrieved=len(papers),
            papers=papers,
        )


_ABSTRACT_API_BASE = "https://api.elsevier.com/content/abstract/doi"
_ABSTRACT_RATE_SLEEP = 0.2  # 5 req/sec -- safely under 6 req/sec ceiling
_ABSTRACT_BATCH_SIZE = 50  # enrich up to 50 papers per call to avoid long blocking


async def enrich_scopus_abstracts(
    papers: list[CandidatePaper],
    api_key: str | None = None,
    batch_size: int = _ABSTRACT_BATCH_SIZE,
) -> int:
    """Back-fill abstract=None for Scopus papers using the Abstract Retrieval API.

    The Scopus Search API does not return dc:description (abstract) for standard
    API keys. This function calls /content/abstract/doi/{doi} for each Scopus
    paper that has a DOI and abstract=None, updating the paper object in place.

    Args:
        papers: List of CandidatePaper objects (all databases, not just Scopus).
        api_key: Elsevier API key. Falls back to SCOPUS_API_KEY env var.
        batch_size: Maximum papers to enrich per invocation (cost/latency control).

    Returns:
        Number of abstracts successfully retrieved.
    """
    key = api_key or os.getenv("SCOPUS_API_KEY", "")
    if not key:
        logger.warning("enrich_scopus_abstracts: no SCOPUS_API_KEY, skipping")
        return 0

    candidates = [p for p in papers if p.source_database == "scopus" and not p.abstract and p.doi]
    if not candidates:
        return 0

    to_enrich = candidates[:batch_size]
    logger.info(
        "enrich_scopus_abstracts: enriching %d/%d Scopus papers with DOIs",
        len(to_enrich),
        len(candidates),
    )

    enriched = 0
    headers = {
        "X-ELS-APIKey": key,
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession(
        connector=tcp_connector_with_certifi(),
        headers=headers,
    ) as session:
        for paper in to_enrich:
            try:
                url = f"{_ABSTRACT_API_BASE}/{paper.doi}"
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "enrich_scopus_abstracts: HTTP %d for DOI %s",
                            resp.status,
                            paper.doi,
                        )
                        await asyncio.sleep(_ABSTRACT_RATE_SLEEP)
                        continue
                    payload = await resp.json(content_type=None)

                resp_obj = payload.get("abstracts-retrieval-response", {})
                coredata = resp_obj.get("coredata", {}) or {}
                abstract_text = coredata.get("dc:description") or ""
                if abstract_text and len(abstract_text) > 20:
                    paper.abstract = str(abstract_text).strip()
                    enriched += 1
                    logger.debug(
                        "enrich_scopus_abstracts: got abstract for DOI %s (%d chars)",
                        paper.doi,
                        len(paper.abstract),
                    )
            except Exception as exc:
                logger.debug(
                    "enrich_scopus_abstracts: error for DOI %s: %s",
                    paper.doi,
                    exc,
                )
            await asyncio.sleep(_ABSTRACT_RATE_SLEEP)

    logger.info(
        "enrich_scopus_abstracts: enriched %d/%d papers",
        enriched,
        len(to_enrich),
    )
    return enriched
