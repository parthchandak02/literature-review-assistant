"""PubMed connector using Biopython Entrez."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Any

from Bio import Entrez

from src.models import CandidatePaper, SearchResult, SourceCategory


class PubMedConnector:
    name = "pubmed"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        Entrez.email = os.getenv("PUBMED_EMAIL") or os.getenv("NCBI_EMAIL") or "unknown@example.com"
        api_key = os.getenv("PUBMED_API_KEY")
        if api_key:
            Entrez.api_key = api_key

    @staticmethod
    def _extract_year(record: Any) -> int | None:
        pub_date = str(PubMedConnector._field(record, "PubDate") or "")
        for token in pub_date.split():
            if token.isdigit() and len(token) == 4:
                return int(token)
        return None

    @staticmethod
    def _field(record: Any, key: str) -> Any:
        if hasattr(record, "get"):
            return record.get(key)
        try:
            return record[key]
        except Exception:
            return None

    def _sync_search(
        self,
        query: str,
        max_results: int,
        date_start: int | None,
        date_end: int | None,
    ) -> list[CandidatePaper]:
        terms: list[str] = [query]
        if date_start and date_end:
            terms.append(f'("{date_start}"[Date - Publication] : "{date_end}"[Date - Publication])')
        full_term = " AND ".join(terms)

        with Entrez.esearch(db="pubmed", term=full_term, retmax=max_results) as handle:
            search_record = Entrez.read(handle)
        ids = search_record.get("IdList", [])
        if not ids:
            return []

        with Entrez.esummary(db="pubmed", id=",".join(ids), retmode="xml") as handle:
            summary = Entrez.read(handle)

        papers: list[CandidatePaper] = []
        for doc in summary:
            title = str(self._field(doc, "Title") or "Untitled")
            author_list = self._field(doc, "AuthorList") or []
            authors = [str(author) for author in author_list if str(author).strip()]
            doi = None
            article_ids = self._field(doc, "ArticleIds") or []
            for aid in article_ids:
                id_type = getattr(aid, "attributes", {}).get("IdType")
                if id_type == "doi":
                    doi = str(aid)
                    break
            year = self._extract_year(doc)
            papers.append(
                CandidatePaper(
                    title=title,
                    authors=authors or ["Unknown"],
                    year=year,
                    source_database="pubmed",
                    doi=doi,
                    abstract=None,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{self._field(doc, 'Id')}/",
                    source_category=SourceCategory.DATABASE,
                )
            )
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
