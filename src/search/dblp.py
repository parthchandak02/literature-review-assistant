"""DBLP connector for computer science bibliography search."""

from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

_BASE_URL = "https://dblp.org/search/publ/api"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_authors(info: dict[str, Any]) -> list[str]:
    author_blob = (info.get("authors") or {}).get("author")
    authors: list[str] = []
    for candidate in _as_list(author_blob):
        if isinstance(candidate, dict):
            text = str(candidate.get("text") or candidate.get("@text") or "").strip()
            if text:
                authors.append(text)
                continue
        if candidate:
            authors.append(str(candidate).strip())
    return [a for a in authors if a]


def _extract_year(info: dict[str, Any]) -> int | None:
    year_raw = info.get("year")
    if year_raw is None:
        return None
    try:
        return int(str(year_raw).strip()[:4])
    except ValueError:
        return None


class DblpConnector:
    name = "dblp"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    @staticmethod
    def _to_candidate(hit: dict[str, Any]) -> CandidatePaper | None:
        info = hit.get("info") or {}
        title = str(info.get("title") or "").strip()
        if not title:
            return None
        doi = info.get("doi")
        ee = info.get("ee")
        url: str | None = None
        if isinstance(ee, list) and ee:
            url = str(ee[0])
        elif isinstance(ee, str):
            url = ee
        return CandidatePaper(
            title=title,
            authors=_extract_authors(info) or ["Unknown"],
            year=_extract_year(info),
            source_database="dblp",
            doi=str(doi) if doi else None,
            abstract=None,
            url=url,
            journal=str(info.get("venue")) if info.get("venue") else None,
            source_category=SourceCategory.DATABASE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        _ = (date_start, date_end)
        params = {
            "q": query,
            "format": "json",
            "h": str(min(max_results, 1000)),
            "f": "0",
        }
        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
            async with session.get(_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"DBLP API returned HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        hits = (((payload.get("result") or {}).get("hits") or {}).get("hit")) or []
        for hit in _as_list(hits):
            if not isinstance(hit, dict):
                continue
            candidate = self._to_candidate(hit)
            if candidate is not None:
                papers.append(candidate)
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=query,
            limits_applied=f"max_results={min(max_results, 1000)}",
            records_retrieved=len(papers),
            papers=papers,
        )
