"""Europe PMC connector."""

from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

_EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _parse_year(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 4:
        return None
    try:
        return int(text[:4])
    except ValueError:
        return None


def _split_authors(author_string: str | None) -> list[str]:
    if not author_string:
        return []
    if "|" in author_string:
        return [a.strip() for a in author_string.split("|") if a.strip()]
    if "," in author_string:
        return [a.strip() for a in author_string.split(",") if a.strip()]
    return [author_string.strip()] if author_string.strip() else []


class EuropePmcConnector:
    name = "europepmc"
    source_category = SourceCategory.DATABASE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    @staticmethod
    def _to_candidate(item: dict[str, Any]) -> CandidatePaper | None:
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        year = _parse_year(item.get("pubYear"))
        doi = item.get("doi")
        pmid = item.get("pmid")
        pmcid = item.get("pmcid")
        url = item.get("fullTextUrlList", {}).get("fullTextUrl")
        resolved_url: str | None = None
        if isinstance(url, list) and url:
            first = url[0]
            if isinstance(first, dict):
                resolved_url = str(first.get("url") or "").strip() or None
        if resolved_url is None and pmid:
            resolved_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if resolved_url is None and pmcid:
            resolved_url = f"https://europepmc.org/article/PMC/{pmcid}"
        journal = item.get("journalTitle")
        abstract = item.get("abstractText")
        return CandidatePaper(
            title=title,
            authors=_split_authors(item.get("authorString")) or ["Unknown"],
            year=year,
            source_database="europepmc",
            doi=str(doi) if doi else None,
            pmid=str(pmid) if pmid else None,
            abstract=str(abstract) if abstract else None,
            url=resolved_url,
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
        params = {
            "query": query,
            "format": "json",
            "resultType": "lite",
            "pageSize": str(min(max_results, 1000)),
        }
        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
            async with session.get(
                _EUROPEPMC_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:240]
                    raise RuntimeError(f"Europe PMC API returned HTTP {resp.status}: {body}")
                payload = await resp.json(content_type=None)
        for item in (payload.get("resultList") or {}).get("result") or []:
            if not isinstance(item, dict):
                continue
            year = _parse_year(item.get("pubYear"))
            if date_start and year and year < date_start:
                continue
            if date_end and year and year > date_end:
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
            limits_applied=f"max_results={min(max_results, 1000)}",
            records_retrieved=len(papers),
            papers=papers,
        )
