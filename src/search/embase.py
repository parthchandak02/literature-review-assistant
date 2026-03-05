"""Elsevier Embase connector.

Uses the Elsevier Embase API (https://api.elsevier.com/content/search/embase)
with field-code queries and date filtering.

Authentication: requires an Elsevier institutional API key (EMBASE_API_KEY env
var) plus an institutional token (ELSEVIER_INSTTOKEN env var) for full-record
access. Contact your library for API credentials.

API reference:
  https://api.elsevier.com/documentation/EmbaseAPI.wadl
  https://dev.elsevier.com/documentation/EmbaseAPI.wadl

Rate limits: Elsevier limits Embase API to 6 req/sec across all connectors.
We sleep 0.2s between pages to stay safely below that ceiling.

Note: Embase and Scopus share ~60% content overlap. Both should be searched
because Embase has superior pharmacology/nursing coverage while Scopus excels
in engineering/computer science. Do NOT substitute one for the other.

If EMBASE_API_KEY is not set, the connector raises ValueError on init so the
workflow can log the missing-credential failure and continue with other sources.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import date
from typing import Any

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elsevier.com/content/search/embase"
_PAGE_SIZE = 25  # safe page size; Embase API max is 25 without elevated access
_RATE_SLEEP = 0.2  # 5 req/sec; safely under Elsevier 6 req/sec ceiling

# Maximum retries for 429 (rate-limited) and 5xx (server error) responses.
_MAX_RETRIES = 3
_RETRY_BASE_SLEEP = 5.0


class EmbaseConnector:
    """Search Elsevier Embase using the official Search API.

    Authentication: EMBASE_API_KEY env var (required).
    Optional: ELSEVIER_INSTTOKEN env var for elevated access.
    """

    name = "embase"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        api_key = os.getenv("EMBASE_API_KEY")
        if not api_key:
            raise ValueError(
                "EMBASE_API_KEY environment variable is required for the Embase connector. "
                "Obtain an API key from your institution's Elsevier subscription. "
                "Set EMBASE_API_KEY in your .env file and restart the server."
            )
        self._api_key = api_key.strip()
        self._insttoken = (os.getenv("ELSEVIER_INSTTOKEN") or "").strip() or None

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }
        if self._insttoken:
            headers["X-ELS-Insttoken"] = self._insttoken
        return headers

    @staticmethod
    def _parse_authors(entry: dict[str, Any]) -> list[str]:
        """Extract author display names from an Embase entry."""
        authors: list[str] = []
        # Embase JSON: "author" is a list of dicts with "$" or "given-name"/"surname"
        for author in entry.get("author", []):
            if isinstance(author, dict):
                given = (author.get("given-name") or author.get("ce:given-name") or "").strip()
                surname = (author.get("surname") or author.get("ce:surname") or "").strip()
                initials = (author.get("initials") or "").strip()
                if surname:
                    name = f"{surname} {given or initials}".strip()
                    authors.append(name)
                elif author.get("$"):
                    authors.append(str(author["$"]).strip())
        return authors if authors else ["Unknown"]

    @staticmethod
    def _parse_keywords(entry: dict[str, Any]) -> list[str] | None:
        """Extract author/index keywords from an Embase entry."""
        kw_block = entry.get("authkeywords") or entry.get("keywords")
        if not kw_block:
            return None
        if isinstance(kw_block, str):
            return [k.strip() for k in kw_block.split("|") if k.strip()]
        if isinstance(kw_block, list):
            return [str(k).strip() for k in kw_block if str(k).strip()]
        return None

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        query: str,
        start: int,
        date_start: int | None,
        date_end: int | None,
    ) -> dict[str, Any]:
        """Fetch one page of Embase results with retry on 429 / 5xx."""
        params: dict[str, Any] = {
            "query": query,
            "start": start,
            "count": _PAGE_SIZE,
            "view": "COMPLETE",
            "field": "dc:title,prism:doi,dc:description,prism:coverDate,author,prism:publicationName,authkeywords",
        }
        if date_start is not None:
            params["date"] = f"{date_start}-{date_end or date.today().year}"

        for attempt in range(_MAX_RETRIES):
            async with session.get(_BASE_URL, headers=self._build_headers(), params=params) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status == 429 or resp.status >= 500:
                    wait = _RETRY_BASE_SLEEP * (2**attempt)
                    logger.warning(
                        "EmbaseConnector: HTTP %d on page start=%d (attempt %d/%d); retrying in %.0fs",
                        resp.status,
                        start,
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                # 4xx other than 429: log and return empty
                body = await resp.text()
                logger.warning(
                    "EmbaseConnector: HTTP %d on page start=%d: %s",
                    resp.status,
                    start,
                    body[:200],
                )
                return {}
        logger.error("EmbaseConnector: max retries exceeded at start=%d; returning empty page", start)
        return {}

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        """Execute an Embase search and return a typed SearchResult.

        Args:
            query: Embase search string (supports Emtree thesaurus, field codes:
                   'title-abs-key()', 'TITLE-ABS-KEY()', etc.)
            max_results: Maximum number of records to return.
            date_start: Filter to records published from this year (inclusive).
            date_end: Filter to records published up to this year (inclusive).

        Returns:
            SearchResult with all retrieved papers.
        """
        papers: list[CandidatePaper] = []
        seen_dois: set[str] = set()
        total_available = 0
        fetched = 0

        tcp_conn = tcp_connector_with_certifi()
        async with aiohttp.ClientSession(connector=tcp_conn) as session:
            # First page -- reveals total result count
            data = await self._fetch_page(session, query, 0, date_start, date_end)
            results_block = data.get("search-results") or {}
            total_available = int(results_block.get("opensearch:totalResults", 0))
            entries: list[dict[str, Any]] = results_block.get("entry", [])

            if not entries or total_available == 0:
                logger.info("EmbaseConnector: 0 results for query.")
                return SearchResult(
                    workflow_id=self.workflow_id,
                    database_name="Embase",
                    source_category=SourceCategory.DATABASE,
                    search_date=date.today().isoformat(),
                    search_query=query,
                    limits_applied=f"date_start={date_start}, max_results={max_results}",
                    records_retrieved=0,
                    papers=[],
                )

            def _parse_entries(entries: list[dict[str, Any]]) -> None:
                for entry in entries:
                    if len(papers) >= max_results:
                        return
                    title = (entry.get("dc:title") or "").strip()
                    if not title:
                        continue
                    doi_raw = (entry.get("prism:doi") or "").strip()
                    doi: str | None = doi_raw if doi_raw else None
                    if doi and doi in seen_dois:
                        continue
                    if doi:
                        seen_dois.add(doi)

                    authors = self._parse_authors(entry)
                    abstract = (entry.get("dc:description") or "").strip() or None
                    cover_date = entry.get("prism:coverDate") or ""
                    year: int | None = None
                    if cover_date and len(cover_date) >= 4:
                        try:
                            year = int(cover_date[:4])
                        except ValueError:
                            pass
                    url = f"https://doi.org/{doi}" if doi else None
                    keywords = self._parse_keywords(entry)

                    papers.append(
                        CandidatePaper(
                            paper_id=str(uuid.uuid4())[:12],
                            title=title,
                            authors=authors,
                            year=year,
                            source_database="Embase",
                            doi=doi,
                            abstract=abstract,
                            url=url,
                            keywords=keywords,
                            source_category=SourceCategory.DATABASE,
                        )
                    )

            _parse_entries(entries)
            fetched += len(entries)

            # Paginate until max_results or total available is exhausted
            while fetched < total_available and len(papers) < max_results:
                await asyncio.sleep(_RATE_SLEEP)
                page_data = await self._fetch_page(session, query, fetched, date_start, date_end)
                page_results = page_data.get("search-results") or {}
                page_entries: list[dict[str, Any]] = page_results.get("entry", [])
                if not page_entries:
                    break
                _parse_entries(page_entries)
                fetched += len(page_entries)

        logger.info(
            "EmbaseConnector: retrieved %d/%d records (max=%d, total_available=%d)",
            len(papers),
            fetched,
            max_results,
            total_available,
        )
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name="Embase",
            source_category=SourceCategory.DATABASE,
            search_date=date.today().isoformat(),
            search_query=query,
            limits_applied=f"date_start={date_start}, max_results={max_results}",
            records_retrieved=len(papers),
            papers=papers,
        )
