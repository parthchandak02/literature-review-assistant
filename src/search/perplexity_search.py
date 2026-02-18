"""Perplexity web-search connector for auxiliary discovery."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from urllib.parse import urlparse

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

# URL domain -> (database_name, source_category) for PRISMA attribution.
# Order matters: more specific domains first (e.g. pmc.ncbi before ncbi).
# Sources: PubMed/PMC, arXiv, IEEE, Semantic Scholar, OpenAlex, Crossref (DOI + publishers).
_URL_TO_SOURCE: list[tuple[list[str], tuple[str, SourceCategory]]] = [
    (["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"], ("pubmed", SourceCategory.DATABASE)),
    (["arxiv.org"], ("arxiv", SourceCategory.DATABASE)),
    (["ieeexplore.ieee.org", "ieee.org"], ("ieee_xplore", SourceCategory.DATABASE)),
    (["semanticscholar.org"], ("semantic_scholar", SourceCategory.DATABASE)),
    (["openalex.org"], ("openalex", SourceCategory.DATABASE)),
    (["doi.org", "dx.doi.org"], ("crossref", SourceCategory.DATABASE)),
    (
        [
            "frontiersin.org",
            "link.springer.com",
            "springer.com",
            "nature.com",
            "sciencedirect.com",
            "tandfonline.com",
            "wiley.com",
            "acm.org",
            "dl.acm.org",
            "plos.org",
            "mdpi.com",
            "hindawi.com",
            "iop.org",
            "iopscience.iop.org",
            "iacis.org",
            "srcpublishers.com",
            "dialoguessr.com",
        ],
        ("crossref", SourceCategory.DATABASE),
    ),
]

PERPLEXITY_WEB = "perplexity_web"


def _infer_source_from_url(url: str | None) -> tuple[str, SourceCategory]:
    """Infer database_name and source_category from result URL for PRISMA attribution."""
    if not url or not url.strip():
        return PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or parsed.path or "").lower().strip()
        if not host:
            return PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        for domains, (db_name, category) in _URL_TO_SOURCE:
            for d in domains:
                if host == d or host.endswith("." + d):
                    return db_name, category
    except Exception:
        pass
    return PERPLEXITY_WEB, SourceCategory.OTHER_SOURCE


class PerplexitySearchConnector:
    name = "perplexity_search"
    source_category = SourceCategory.OTHER_SOURCE
    base_url = "https://api.perplexity.ai/search"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.api_key = os.getenv("PERPLEXITY_SEARCH_API_KEY")

    def _to_candidate(self, item: dict) -> CandidatePaper:
        snippet = str(item.get("snippet") or "")
        url = item.get("url")
        source_database, source_category = _infer_source_from_url(url)
        return CandidatePaper(
            title=str(item.get("title") or "Untitled"),
            authors=["Unknown"],
            year=None,
            source_database=source_database,
            doi=None,
            abstract=snippet[:4000] if snippet else None,
            url=url,
            source_category=source_category,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> list[SearchResult]:
        _ = (date_start, date_end)
        if not self.api_key:
            return [
                SearchResult(
                    workflow_id=self.workflow_id,
                    database_name=self.name,
                    source_category=self.source_category,
                    search_date=date.today().isoformat(),
                    search_query=query,
                    limits_applied="missing_api_key",
                    records_retrieved=0,
                    papers=[],
                )
            ]

        payload = {
            "query": query,
            "max_results": min(max_results, 20),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(
            headers=headers, connector=tcp_connector_with_certifi()
        ) as session:
            async with session.post(self.base_url, json=payload, timeout=30) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"Perplexity search failed: status={response.status}, body={body[:250]}")
                data = await response.json()
                for item in data.get("results", []):
                    papers.append(self._to_candidate(item))

        # Group papers by (source_database, source_category) for PRISMA attribution
        groups: dict[tuple[str, SourceCategory], list[CandidatePaper]] = defaultdict(list)
        for p in papers:
            key = (p.source_database, p.source_category)
            groups[key].append(p)

        search_date = date.today().isoformat()
        limits = f"max_results={min(max_results, 20)}"
        results: list[SearchResult] = []
        for (db_name, cat), group_papers in groups.items():
            results.append(
                SearchResult(
                    workflow_id=self.workflow_id,
                    database_name=db_name,
                    source_category=cat,
                    search_date=search_date,
                    search_query=query,
                    limits_applied=limits,
                    records_retrieved=len(group_papers),
                    papers=group_papers,
                )
            )
        return results
