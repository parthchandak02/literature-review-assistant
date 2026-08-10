"""Scopus web gateway client using institutional session cookies.

The official Elsevier Search API often lacks Search entitlement or returns
metadata without abstracts. The Scopus web UI uses authenticated gateway
endpoints that return richer records (title, DOI, abstract, authors, journal).

Each operator supplies their own browser session via SCOPUS_SESSION_COOKIE_FILE
(Netscape cookies.txt or a raw Cookie header saved to a local path outside the
repo). Sessions expire; refresh the cookie file after re-authenticating in Chrome.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import aiohttp

from src.config.env_context import get_env
from src.models import CandidatePaper, SearchResult, SourceCategory
from src.search.common import primary_filter_mode_from_query
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_GATEWAY_SEARCH_URL = "https://www.scopus.com/gateway/documents/search"
_PAGE_SIZE = 25
_RATE_SLEEP_SECONDS = 0.25
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<[^>]+>")


def load_scopus_session_cookie() -> str | None:
    """Return a Cookie header value from the operator's local session file."""
    cookie_file = (get_env("SCOPUS_SESSION_COOKIE_FILE") or "").strip()
    if not cookie_file:
        return None
    loaded = _load_cookie_file(cookie_file)
    if loaded:
        return loaded
    logger.warning(
        "SCOPUS_SESSION_COOKIE_FILE is set but no scopus.com/elsevier.com cookies were found: %s",
        cookie_file,
    )
    return None


def _load_cookie_file(path: str) -> str | None:
    cookie_path = Path(path).expanduser()
    if not cookie_path.is_file():
        logger.warning("SCOPUS_SESSION_COOKIE_FILE does not exist: %s", cookie_path)
        return None
    text = cookie_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    if "=" in text and "\t" not in text and not text.startswith("#"):
        # Raw Cookie header pasted into a file.
        return _filter_scopus_cookie_header(text)
    return _netscape_cookies_to_header(text)


def _netscape_cookies_to_header(text: str) -> str | None:
    pairs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if "scopus.com" not in domain and "elsevier.com" not in domain:
            continue
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs) if pairs else None


def _filter_scopus_cookie_header(header: str) -> str | None:
    pairs: list[str] = []
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name = part.split("=", 1)[0].strip()
        if name:
            pairs.append(part)
    return "; ".join(pairs) if pairs else None


def build_gateway_headers(cookie_header: str) -> dict[str, str]:
    return {
        "Cookie": cookie_header,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "x-source": "scopus-frontend",
        "Origin": "https://www.scopus.com",
        "Referer": "https://www.scopus.com/pages/search/publications",
        "User-Agent": _DEFAULT_USER_AGENT,
    }


def _strip_html(value: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", value))
    return re.sub(r"\s+", " ", text).strip()


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        return _first_text(value[0])
    if isinstance(value, str):
        cleaned = _strip_html(value) if "<" in value else value.strip()
        return cleaned or None
    return str(value).strip() or None


def _parse_authors(item: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in item.get("authors") or []:
        if not isinstance(author, dict):
            continue
        preferred = author.get("preferredName") or {}
        full = preferred.get("full") or preferred.get("last") or ""
        if full:
            authors.append(str(full))
    return authors or ["Unknown"]


def gateway_item_to_candidate(item: dict[str, Any]) -> CandidatePaper:
    source = item.get("source") or {}
    journal = source.get("title") or source.get("sourceTitleAbbreviation")
    abstract = _first_text(item.get("abstractText"))
    doi = item.get("doi")
    eid = item.get("eid")
    url = f"https://www.scopus.com/inward/record.uri?eid={eid}" if eid else None
    year = item.get("pubYear")
    try:
        year_int = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_int = None
    return CandidatePaper(
        title=str(item.get("title") or "Untitled"),
        authors=_parse_authors(item),
        year=year_int,
        source_database="scopus",
        doi=str(doi) if doi else None,
        abstract=abstract,
        url=url,
        journal=str(journal) if journal else None,
        source_category=SourceCategory.DATABASE,
    )


def _apply_date_filters(query: str, date_start: int | None, date_end: int | None) -> str:
    full_query = query
    if date_start and "PUBYEAR" not in query.upper():
        full_query += f" AND PUBYEAR > {date_start - 1}"
    if date_end and "PUBYEAR" not in query.upper():
        full_query += f" AND PUBYEAR < {date_end + 1}"
    return full_query


def _search_payload(query: str, offset: int, item_count: int) -> dict[str, Any]:
    return {
        "query": query,
        "documentClassification": "primary",
        "resultSet": {"offset": offset, "itemCount": item_count},
        "sortBy": [
            {"fieldName": "datesort", "order": "desc"},
            {"fieldName": "relevance", "order": "desc"},
        ],
    }


async def search_via_session_gateway(
    *,
    workflow_id: str,
    query: str,
    max_results: int,
    date_start: int | None = None,
    date_end: int | None = None,
    cookie_header: str | None = None,
) -> SearchResult:
    """Search Scopus through the authenticated web gateway."""
    cookie = cookie_header or load_scopus_session_cookie()
    if not cookie:
        raise RuntimeError(
            "Scopus session cookie is not configured. Set SCOPUS_SESSION_COOKIE_FILE "
            "to a local cookies file exported from your own institutional Scopus login."
        )

    full_query = _apply_date_filters(query, date_start, date_end)
    headers = build_gateway_headers(cookie)
    papers: list[CandidatePaper] = []
    offset = 0
    total_count: int | None = None

    async with aiohttp.ClientSession(
        connector=tcp_connector_with_certifi(),
        headers=headers,
    ) as session:
        while len(papers) < max_results:
            page_size = min(_PAGE_SIZE, max_results - len(papers))
            payload = _search_payload(full_query, offset, page_size)
            async with session.post(
                _GATEWAY_SEARCH_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status == 403:
                    raise RuntimeError(
                        "Scopus session gateway returned HTTP 403. "
                        "Re-export cookies from your browser after logging into institutional Scopus."
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Scopus session gateway returned HTTP {resp.status}: {body[:200]}"
                    )
                data = await resp.json(content_type=None)

            metadata = data.get("metadata") or {}
            if total_count is None:
                try:
                    total_count = int(metadata.get("totalCount") or 0)
                except (TypeError, ValueError):
                    total_count = 0
                logger.info(
                    "Scopus session gateway: %s total results (retrieving up to %s)",
                    total_count,
                    max_results,
                )

            items = data.get("items") or []
            if not items:
                break

            for item in items:
                if len(papers) >= max_results:
                    break
                if not isinstance(item, dict):
                    continue
                if not item.get("title") and not item.get("doi"):
                    # Lightweight eid-only pages are not useful for screening.
                    continue
                try:
                    papers.append(gateway_item_to_candidate(item))
                except Exception as exc:
                    logger.debug("Scopus session gateway: skipped malformed item: %s", exc)

            offset += len(items)
            if total_count is not None and offset >= total_count:
                break
            if len(items) < page_size:
                break

            await asyncio.sleep(_RATE_SLEEP_SECONDS)

    logger.info(
        "Scopus session gateway retrieved %d papers (query length=%d chars)",
        len(papers),
        len(full_query),
    )
    return SearchResult(
        workflow_id=workflow_id,
        database_name="scopus",
        source_category=SourceCategory.DATABASE,
        search_date=date.today().isoformat(),
        search_query=full_query,
        limits_applied=(
            f"max_results={max_results},transport=session_gateway,"
            f"primary_study_filter={primary_filter_mode_from_query(full_query)}"
        ),
        records_retrieved=len(papers),
        papers=papers,
    )
