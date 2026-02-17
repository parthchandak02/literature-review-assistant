"""Crossref connector."""

from __future__ import annotations

import os
from datetime import date
from urllib.parse import quote

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi


class CrossrefConnector:
    name = "crossref"
    source_category = SourceCategory.DATABASE
    base_url = "https://api.crossref.org/works"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.contact_email = os.getenv("CROSSREF_EMAIL") or "unknown@example.com"

    @staticmethod
    def _to_candidate(item: dict) -> CandidatePaper:
        title = ""
        titles = item.get("title") or []
        if titles:
            title = str(titles[0])
        authors = []
        for author in item.get("author", []):
            given = str(author.get("given") or "").strip()
            family = str(author.get("family") or "").strip()
            full = " ".join(part for part in [given, family] if part)
            if full:
                authors.append(full)
        year = None
        issued = item.get("issued", {}).get("date-parts", [])
        if issued and issued[0]:
            y = issued[0][0]
            if isinstance(y, int):
                year = y
        return CandidatePaper(
            title=title or "Untitled",
            authors=authors or ["Unknown"],
            year=year,
            source_database="crossref",
            doi=item.get("DOI"),
            abstract=item.get("abstract"),
            url=item.get("URL"),
            source_category=SourceCategory.DATABASE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        filter_parts: list[str] = ["type:journal-article"]
        if date_start:
            filter_parts.append(f"from-pub-date:{date_start}-01-01")
        if date_end:
            filter_parts.append(f"until-pub-date:{date_end}-12-31")
        params = {
            "query.bibliographic": query,
            "rows": str(max_results),
            "filter": ",".join(filter_parts),
            "mailto": self.contact_email,
            "select": "DOI,title,author,issued,URL,abstract",
        }
        headers = {
            "User-Agent": f"research-agent-v2/0.1 (mailto:{quote(self.contact_email)})",
        }

        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(
            headers=headers, connector=tcp_connector_with_certifi()
        ) as session:
            async with session.get(self.base_url, params=params, timeout=30) as response:
                if response.status == 200:
                    payload = await response.json()
                    for item in payload.get("message", {}).get("items", []):
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
