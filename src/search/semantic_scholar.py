"""Semantic Scholar connector."""

from __future__ import annotations

import os
from datetime import date

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi


class SemanticScholarConnector:
    name = "semantic_scholar"
    source_category = SourceCategory.DATABASE
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

    @staticmethod
    def _to_candidate(item: dict) -> CandidatePaper:
        authors = [str(author.get("name")) for author in item.get("authors", []) if author.get("name")]
        external_ids = item.get("externalIds") or {}
        doi = external_ids.get("DOI")
        open_access = item.get("openAccessPdf") or {}
        url = open_access.get("url") or item.get("url")
        return CandidatePaper(
            title=str(item.get("title") or "Untitled"),
            authors=authors or ["Unknown"],
            year=int(item["year"]) if item.get("year") is not None else None,
            source_database="semantic_scholar",
            doi=doi,
            abstract=item.get("abstract"),
            url=url,
            source_category=SourceCategory.DATABASE,
        )

    # Semantic Scholar graph API caps a single page at 100 records.
    _PAGE_SIZE = 100

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        papers: list[CandidatePaper] = []
        offset = 0
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
            while len(papers) < max_results:
                page_limit = min(self._PAGE_SIZE, max_results - len(papers))
                params = {
                    "query": query,
                    "limit": str(page_limit),
                    "offset": str(offset),
                    "fields": "title,authors,year,abstract,url,externalIds,openAccessPdf",
                }
                async with session.get(
                    self.base_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        break
                    payload = await response.json()
                    page_data = payload.get("data", [])
                    if not page_data:
                        break
                    for item in page_data:
                        year = item.get("year")
                        if isinstance(year, int):
                            if date_start and year < date_start:
                                continue
                            if date_end and year > date_end:
                                continue
                        papers.append(self._to_candidate(item))
                    # Stop if the API signals no more results or we got a short page
                    total_available = payload.get("total", 0)
                    offset += len(page_data)
                    if offset >= total_available or len(page_data) < page_limit:
                        break

        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=query,
            limits_applied=f"max_results={max_results}",
            records_retrieved=len(papers),
            papers=papers,
        )
