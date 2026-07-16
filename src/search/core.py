"""CORE connector for open-access scholarly metadata search."""

from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp

from src.config.env_context import get_env
from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

_CORE_SEARCH_URL = "https://api.core.ac.uk/v3/search/outputs"


def _core_authors(item: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in item.get("authors") or []:
        if isinstance(author, dict):
            name = str(author.get("name") or "").strip()
            if name:
                authors.append(name)
                continue
        elif author:
            authors.append(str(author).strip())
    return [a for a in authors if a]


class CoreConnector:
    name = "core"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.api_key = (get_env("CORE_API_KEY") or "").strip()

    @staticmethod
    def _to_candidate(item: dict[str, Any]) -> CandidatePaper | None:
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        year_raw = item.get("yearPublished") or item.get("year")
        year: int | None = None
        if year_raw is not None:
            try:
                year = int(str(year_raw)[:4])
            except ValueError:
                year = None
        doi = item.get("doi")
        links = item.get("downloadUrl") or item.get("sourceFulltextUrls") or item.get("urls")
        url: str | None = None
        if isinstance(links, list) and links:
            url = str(links[0])
        elif isinstance(links, str):
            url = links
        abstract = item.get("abstract") or item.get("description")
        journal = item.get("journal") or item.get("publisher")
        return CandidatePaper(
            title=title,
            authors=_core_authors(item) or ["Unknown"],
            year=year,
            source_database="core",
            doi=str(doi) if doi else None,
            abstract=str(abstract) if abstract else None,
            url=str(url) if url else None,
            journal=str(journal) if journal else None,
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
            "limit": str(min(max_results, 100)),
            "offset": "0",
        }
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        papers: list[CandidatePaper] = []
        limits_note = f"max_results={min(max_results, 100)}"
        if not self.api_key:
            limits_note += ",auth=anonymous"
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi(), headers=headers) as session:
            async with session.get(_CORE_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 401 and not self.api_key:
                    return SearchResult(
                        workflow_id=self.workflow_id,
                        database_name=self.name,
                        source_category=self.source_category,
                        search_date=date.today().isoformat(),
                        search_query=query,
                        limits_applied=f"{limits_note},missing_api_key",
                        records_retrieved=0,
                        papers=[],
                    )
                if resp.status != 200:
                    body = (await resp.text())[:240]
                    raise RuntimeError(f"CORE API returned HTTP {resp.status}: {body}")
                payload = await resp.json(content_type=None)
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            candidate = self._to_candidate(item)
            if candidate is not None:
                papers.append(candidate)
        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=query,
            limits_applied=limits_note,
            records_retrieved=len(papers),
            papers=papers,
        )
