"""Clarivate Web of Science connector.

Uses the Web of Science Starter API (free tier, 300 req/day):
  https://api.clarivate.com/apis/wos-starter/v1/documents

Authentication: X-ApiKey header using WOS_API_KEY environment variable.

Query syntax (subset supported by Starter API):
  TS=(topic term)          -- title, abstract, author keywords, keywords plus
  TI=(title term)          -- title only
  PY=(YYYY-YYYY)           -- publication year range

Rate limit: ~2 req/sec conservative to avoid 429s. Starter API is free and
limited; results are capped at max_results per call.

Known limitations:
  - Starter API does not return full text or cited references.
  - Abstract may be missing for some records.
  - Maximum 50 records per page (API page size limit).
  - 300 requests/day free tier -- quota exhaustion causes 429, which is raised
    as RuntimeError so the coordinator marks the connector as "failed" (not
    silent 0-result success).
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

_BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents"
_PAGE_SIZE = 50
_RATE_SLEEP = 0.5  # 2 req/sec -- conservative for free Starter API tier
_MAX_RETRIES = 3  # max retries per page on 429 or 5xx
_RETRY_BASE_SLEEP = 5  # seconds; doubles each retry (5, 10, 20)


def _retryable_status_message(status: int, body: str, retries: int) -> str:
    """Build a precise fatal message for retryable status exhaustion."""
    clipped = body[:200]
    if status == 429:
        return (
            f"WoS API: status 429 after {retries} retries -- likely rate limit or quota exhaustion "
            f"(WoS Starter API: 300 req/day). Response: {clipped}"
        )
    if status == 512:
        return (
            f"WoS API: status 512 after {retries} retries -- provider internal server fault "
            f"(Clarivate side, not a query/schema issue). Response: {clipped}"
        )
    if 500 <= status < 600:
        return (
            f"WoS API: status {status} after {retries} retries -- persistent server-side failure "
            f"(not necessarily quota exhaustion). Response: {clipped}"
        )
    return f"WoS API: status {status} after {retries} retries. Response: {clipped}"


class WebOfScienceConnector:
    """Search Clarivate Web of Science via the Starter API.

    Authentication: set WOS_API_KEY environment variable.
    Queries should use WoS syntax: TS=(), TI=(), PY=().
    """

    name = "web_of_science"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        api_key = os.getenv("WOS_API_KEY")
        if not api_key:
            raise ValueError("WOS_API_KEY is required for the Web of Science connector")
        self._api_key = api_key.strip()

    @staticmethod
    def _parse_year(record: dict[str, Any]) -> int | None:
        py = record.get("source", {}).get("publishYear")
        if py:
            try:
                return int(str(py)[:4])
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _parse_authors(record: dict[str, Any]) -> list[str]:
        names = record.get("names", {}).get("authors", [])
        if isinstance(names, list):
            return [a.get("displayName", "") for a in names if a.get("displayName")]
        return ["Unknown"]

    @staticmethod
    def _to_candidate(record: dict[str, Any]) -> CandidatePaper:
        title = str(record.get("title", "Untitled") or "Untitled").strip()
        # DOI from identifiers list
        doi: str | None = None
        for ident in record.get("identifiers", []):
            if isinstance(ident, dict) and ident.get("type", "").upper() == "DOI":
                doi = str(ident.get("value", "")).strip() or None
                break
        abstract: str | None = None
        for ab in record.get("abstracts", []):
            if isinstance(ab, dict):
                text = ab.get("text")
                if text:
                    abstract = str(text).strip()
                    break
        year = WebOfScienceConnector._parse_year(record)
        authors = WebOfScienceConnector._parse_authors(record)
        source = record.get("source", {})
        journal = str(source.get("sourceTitle", "")).strip() or None
        uid = record.get("uid", "")
        url = f"https://www.webofscience.com/wos/woscc/full-record/{uid}" if uid else None
        return CandidatePaper(
            title=title,
            authors=authors,
            year=year,
            source_database="web_of_science",
            doi=doi,
            abstract=abstract,
            url=url,
            journal=journal,
            source_category=SourceCategory.DATABASE,
        )

    def _build_query(
        self,
        query: str,
        date_start: int | None,
        date_end: int | None,
    ) -> str:
        """Append year filter if not already embedded and dates are provided.

        WoS Starter API year syntax: PY=YYYY-YYYY (no parentheses around the range).
        """
        full_query = query
        if date_start and date_end and "PY=" not in query:
            full_query += f" AND PY={date_start}-{date_end}"
        elif date_start and "PY=" not in query:
            full_query += f" AND PY={date_start}-9999"
        return full_query

    @staticmethod
    def _primary_filter_mode(query: str) -> str:
        if "DT=Review" in query:
            return "query_exclusion"
        return "screening_only"

    async def search(
        self,
        query: str,
        max_results: int = 500,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        """Run a WoS search and return results up to max_results.

        Raises RuntimeError when the API returns a fatal error (401/403) or
        exhausts all retries on 429/5xx. 429 is usually quota/rate limiting;
        status 512 and other 5xx responses are classified as provider-side
        server faults. The SearchStrategyCoordinator catches this and marks the
        connector as "failed" in SSE instead of silently returning 0 results.
        """
        papers: list[CandidatePaper] = []
        headers = {
            "X-ApiKey": self._api_key,
            "Accept": "application/json",
        }
        full_query = self._build_query(query, date_start, date_end)
        page = 1
        total_records: int | None = None
        # Track the last fatal/quota error so we can raise after all pages attempted.
        _fatal_error: str | None = None

        async with aiohttp.ClientSession(
            connector=tcp_connector_with_certifi(),
            headers=headers,
        ) as session:
            while True:
                if total_records is not None and (page - 1) * _PAGE_SIZE >= total_records:
                    break
                if len(papers) >= max_results:
                    break

                params: dict[str, Any] = {
                    "q": full_query,
                    "limit": str(_PAGE_SIZE),
                    "page": str(page),
                    "db": "WOS",
                }

                data: dict[str, Any] | None = None
                for attempt in range(_MAX_RETRIES + 1):
                    try:
                        async with session.get(
                            _BASE_URL,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as resp:
                            if resp.status == 401:
                                _fatal_error = "WoS API: 401 Unauthorized -- check WOS_API_KEY"
                                logger.error(_fatal_error)
                                break
                            if resp.status == 403:
                                _fatal_error = (
                                    "WoS API: 403 Forbidden -- API key may lack access to WoS Core Collection"
                                )
                                logger.error(_fatal_error)
                                break
                            if resp.status in (429,) or 500 <= resp.status < 600:
                                body = await resp.text()
                                if attempt < _MAX_RETRIES:
                                    sleep_s = _RETRY_BASE_SLEEP * (2**attempt)
                                    logger.warning(
                                        "WoS API: status %d -- backing off %ds (attempt %d/%d): %s",
                                        resp.status,
                                        sleep_s,
                                        attempt + 1,
                                        _MAX_RETRIES,
                                        body[:200],
                                    )
                                    await asyncio.sleep(sleep_s)
                                    continue
                                else:
                                    _fatal_error = _retryable_status_message(resp.status, body, _MAX_RETRIES)
                                    logger.error(_fatal_error)
                                break
                            if resp.status != 200:
                                body = await resp.text()
                                _fatal_error = f"WoS API: unexpected status {resp.status} -- {body[:200]}"
                                logger.warning(_fatal_error)
                                break
                            data = await resp.json()
                            break
                    except (TimeoutError, aiohttp.ClientError) as exc:
                        if attempt < _MAX_RETRIES:
                            sleep_s = _RETRY_BASE_SLEEP * (2**attempt)
                            logger.warning(
                                "WoS API request failed (attempt %d/%d, retry in %ds): %s",
                                attempt + 1,
                                _MAX_RETRIES,
                                sleep_s,
                                exc,
                            )
                            await asyncio.sleep(sleep_s)
                        else:
                            _fatal_error = f"WoS API request failed after {_MAX_RETRIES} retries: {exc}"
                            logger.error(_fatal_error)
                        continue
                else:
                    # All retries exhausted without a successful response -- stop pagination
                    break

                if data is None:
                    # Non-retryable error (401/403/unexpected status) -- stop pagination
                    break

                hits = data.get("hits", {})
                if total_records is None:
                    total_records = hits.get("total", 0)
                    logger.info(
                        "WoS search: query=%r total=%d max=%d",
                        full_query[:120],
                        total_records,
                        max_results,
                    )

                records = hits.get("hits", [])
                if not records:
                    break

                for rec in records:
                    if len(papers) >= max_results:
                        break
                    try:
                        papers.append(self._to_candidate(rec))
                    except Exception as exc:
                        logger.debug("WoS: failed to parse record: %s", exc)

                page += 1
                await asyncio.sleep(_RATE_SLEEP)

        # If we got no papers and encountered a fatal/quota error, raise so the
        # coordinator marks this as "failed" instead of silent 0-result success.
        if not papers and _fatal_error:
            raise RuntimeError(_fatal_error)

        logger.info("WoS: retrieved %d papers", len(papers))
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name="web_of_science",
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=full_query,
            limits_applied=(
                f"max_results={max_results},"
                f"primary_study_filter={self._primary_filter_mode(full_query)}"
            ),
            records_retrieved=len(papers),
            papers=papers,
        )
