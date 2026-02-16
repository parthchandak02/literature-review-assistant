"""Semantic Scholar connector."""

from __future__ import annotations

import os
from datetime import date

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory


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

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        params = {
            "query": query,
            "limit": str(max_results),
            "fields": "title,authors,year,abstract,url,externalIds,openAccessPdf",
        }
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url, params=params, headers=headers, timeout=30) as response:
                if response.status == 200:
                    payload = await response.json()
                    for item in payload.get("data", []):
                        year = item.get("year")
                        if isinstance(year, int):
                            if date_start and year < date_start:
                                continue
                            if date_end and year > date_end:
                                continue
                        papers.append(self._to_candidate(item))

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
