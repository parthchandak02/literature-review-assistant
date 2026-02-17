"""IEEE Xplore connector."""

from __future__ import annotations

import os
from datetime import date

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi


class IEEEXploreConnector:
    name = "ieee_xplore"
    source_category = SourceCategory.DATABASE
    base_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.api_key = os.getenv("IEEE_API_KEY")

    @staticmethod
    def _to_candidate(article: dict) -> CandidatePaper:
        doi = article.get("doi")
        year = article.get("publication_year")
        authors = []
        author_block = article.get("authors", {})
        for author in author_block.get("authors", []):
            full_name = author.get("full_name")
            if full_name:
                authors.append(str(full_name))
        return CandidatePaper(
            title=str(article.get("title") or "Untitled"),
            authors=authors or ["Unknown"],
            year=int(year) if isinstance(year, int | str) and str(year).isdigit() else None,
            source_database="ieee_xplore",
            doi=doi,
            abstract=article.get("abstract"),
            url=article.get("html_url") or article.get("pdf_url"),
            source_category=SourceCategory.DATABASE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        if not self.api_key:
            return SearchResult(
                workflow_id=self.workflow_id,
                database_name=self.name,
                source_category=self.source_category,
                search_date=date.today().isoformat(),
                search_query=query,
                limits_applied="missing_api_key",
                records_retrieved=0,
                papers=[],
            )

        params = {
            "apikey": self.api_key,
            "querytext": query,
            "max_records": str(max_results),
            "start_record": "1",
        }
        if date_start:
            params["start_year"] = str(date_start)
        if date_end:
            params["end_year"] = str(date_end)

        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
            async with session.get(self.base_url, params=params, timeout=30) as response:
                if response.status == 200:
                    payload = await response.json()
                    for article in payload.get("articles", []):
                        papers.append(self._to_candidate(article))

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
