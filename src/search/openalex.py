"""OpenAlex connector."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Any, List

from pyalex import Works, config as pyalex_config

from src.models import CandidatePaper, SearchResult, SourceCategory


class OpenAlexConnector:
    name = "openalex"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        api_key = os.getenv("OPENALEX_API_KEY")
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required for OpenAlex connector")
        pyalex_config.api_key = api_key

    @staticmethod
    def _to_candidate(work: dict[str, Any]) -> CandidatePaper:
        authorships = work.get("authorships") or []
        authors: List[str] = []
        for item in authorships:
            author = item.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(str(name))
        year = work.get("publication_year")
        return CandidatePaper(
            title=str(work.get("display_name") or "Untitled"),
            authors=authors or ["Unknown"],
            year=int(year) if year is not None else None,
            source_database="openalex",
            doi=work.get("doi"),
            abstract=work.get("abstract"),
            url=work.get("primary_location", {}).get("landing_page_url"),
            source_category=SourceCategory.DATABASE,
            openalex_id=work.get("id"),
        )

    def _sync_search(
        self,
        query: str,
        max_results: int,
        date_start: int | None,
        date_end: int | None,
    ) -> list[CandidatePaper]:
        works = Works().search(query)
        if date_start:
            works = works.filter(from_publication_date=f"{date_start}-01-01")
        if date_end:
            works = works.filter(to_publication_date=f"{date_end}-12-31")
        works = works.filter(type="article")
        results = works.get(per_page=max_results)
        papers: list[CandidatePaper] = []
        for work in results:
            papers.append(self._to_candidate(work))
        return papers

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        papers = await asyncio.to_thread(self._sync_search, query, max_results, date_start, date_end)
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
