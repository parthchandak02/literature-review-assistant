"""Perplexity web-search connector for auxiliary discovery."""

from __future__ import annotations

import os
from datetime import date

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory


class PerplexitySearchConnector:
    name = "perplexity_search"
    source_category = SourceCategory.OTHER_SOURCE
    base_url = "https://api.perplexity.ai/search"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.api_key = os.getenv("PERPLEXITY_SEARCH_API_KEY")

    @staticmethod
    def _to_candidate(item: dict) -> CandidatePaper:
        snippet = str(item.get("snippet") or "")
        return CandidatePaper(
            title=str(item.get("title") or "Untitled"),
            authors=["Unknown"],
            year=None,
            source_database="perplexity_search",
            doi=None,
            abstract=snippet[:4000] if snippet else None,
            url=item.get("url"),
            source_category=SourceCategory.OTHER_SOURCE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        _ = (date_start, date_end)
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

        payload = {
            "query": query,
            "max_results": min(max_results, 20),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(self.base_url, json=payload, timeout=30) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"Perplexity search failed: status={response.status}, body={body[:250]}")
                data = await response.json()
                for item in data.get("results", []):
                    papers.append(self._to_candidate(item))

        return SearchResult(
            workflow_id=self.workflow_id,
            database_name=self.name,
            source_category=self.source_category,
            search_date=date.today().isoformat(),
            search_query=query,
            limits_applied=f"max_results={min(max_results, 20)}",
            records_retrieved=len(papers),
            papers=papers,
        )
