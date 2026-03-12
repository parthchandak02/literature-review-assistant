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
    def _extract_year_from_pubdate(pub_date: Any) -> int | None:
        """Extract a 4-digit year from a PubDate dict or string."""
        if isinstance(pub_date, dict):
            year_str = str(pub_date.get("Year") or pub_date.get("MedlineDate") or "")
        else:
            year_str = str(pub_date or "")
        for token in year_str.split():
            if token.isdigit() and len(token) == 4:
                return int(token)
        return None

    @staticmethod
    def _parse_abstract(abstract_node: Any) -> str | None:
        """Join structured or plain abstract text into a single string."""
        if abstract_node is None:
            return None
        text_node = abstract_node.get("AbstractText") if isinstance(abstract_node, dict) else abstract_node
        if text_node is None:
            return None
        if isinstance(text_node, list):
            # Structured abstract: list of labelled sections
            parts: list[str] = []
            for section in text_node:
                label = getattr(section, "attributes", {}).get("Label", "") if hasattr(section, "attributes") else ""
                content = str(section).strip()
                if label:
                    parts.append(f"{label}: {content}")
                elif content:
                    parts.append(content)
            return " ".join(parts) if parts else None
        return str(text_node).strip() or None

    def _parse_efetch_record(self, article: Any) -> CandidatePaper | None:
        """Convert one PubmedArticle dict from efetch XML into a CandidatePaper."""
        try:
            medline = article.get("MedlineCitation", {})
            art = medline.get("Article", {})

            title = str(art.get("ArticleTitle") or "Untitled").strip()

            # Authors
            authors: list[str] = []
            for au in art.get("AuthorList") or []:
                last = str(au.get("LastName") or "").strip()
                fore = str(au.get("ForeName") or au.get("Initials") or "").strip()
                name = f"{last}, {fore}" if fore else last
                if name.strip(",").strip():
                    authors.append(name)

            # Year from journal pub date
            journal_issue = art.get("Journal", {}).get("JournalIssue", {})
            pub_date = journal_issue.get("PubDate", {})
            year = self._extract_year_from_pubdate(pub_date)

            # Abstract
            abstract = self._parse_abstract(art.get("Abstract"))

            # DOI and PubMed ID from PubmedData
            doi: str | None = None
            pmid: str | None = None
            pubmed_data = article.get("PubmedData", {})
            for aid in pubmed_data.get("ArticleIdList") or []:
                id_type = getattr(aid, "attributes", {}).get("IdType", "") if hasattr(aid, "attributes") else ""
                val = str(aid).strip()
                if id_type == "doi" and not doi:
                    doi = val
                elif id_type == "pubmed" and not pmid:
                    pmid = val

            # Fallback PMID from MedlineCitation
            if not pmid:
                pmid = str(medline.get("PMID") or "").strip() or None

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "https://pubmed.ncbi.nlm.nih.gov/"

            return CandidatePaper(
                title=title,
                authors=authors or ["Unknown"],
                year=year,
                source_database="pubmed",
                doi=doi,
                abstract=abstract,
                url=url,
                source_category=SourceCategory.DATABASE,
            )
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

        # efetch with rettype="xml" returns full PubmedArticleSet including AbstractText,
        # AuthorList with LastName/ForeName, DOI, and PubDate -- replacing esummary which
        # has no abstract field.
        with Entrez.efetch(db="pubmed", id=",".join(ids), rettype="xml", retmode="xml") as handle:
            records = Entrez.read(handle)

        papers: list[CandidatePaper] = []
        for article in records.get("PubmedArticle", []):
            paper = self._parse_efetch_record(article)
            if paper is not None:
                papers.append(paper)
        return papers

    @staticmethod
    def _primary_filter_mode(query: str) -> str:
        q = query.lower()
        if '"systematic review"[publication type]' in q or '"meta-analysis"[publication type]' in q:
            return "query_exclusion"
        return "screening_only"

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
            limits_applied=(
                f"max_results={max_results},"
                f"primary_study_filter={self._primary_filter_mode(query)}"
            ),
            records_retrieved=len(papers),
            papers=papers,
        )
