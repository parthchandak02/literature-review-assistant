"""arXiv connector."""

from __future__ import annotations

import asyncio
from datetime import date

import arxiv

from src.models import CandidatePaper, SearchResult, SourceCategory


class ArxivConnector:
    name = "arxiv"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    @staticmethod
    def _result_to_paper(result: arxiv.Result) -> CandidatePaper:
        year = result.published.year if result.published else None
        doi = result.doi
        return CandidatePaper(
            title=result.title.strip(),
            authors=[author.name for author in result.authors] or ["Unknown"],
            year=year,
            source_database="arxiv",
            doi=doi,
            abstract=result.summary,
            url=result.entry_id,
            keywords=[c for c in result.categories],
            source_category=SourceCategory.DATABASE,
        )

    def _sync_search(
        self,
        query: str,
        max_results: int,
        date_start: int | None,
        date_end: int | None,
    ) -> list[CandidatePaper]:
        search_query = query
        if date_start and date_end:
            search_query = f"{query} AND submittedDate:[{date_start}0101 TO {date_end}1231]"
        client = arxiv.Client()
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        return [self._result_to_paper(r) for r in client.results(search)]

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
