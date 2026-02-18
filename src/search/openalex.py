"""OpenAlex connector using direct HTTP (api_key in URL per OpenAlex Feb 2026 requirement)."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, List
import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi


def _inverted_index_to_text(idx: dict[str, list[int]] | None) -> str | None:
    """Convert OpenAlex abstract_inverted_index to plaintext."""
    if not idx:
        return None
    pairs: list[tuple[int, str]] = []
    for word, positions in idx.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(p[1] for p in pairs)


class OpenAlexConnector:
    name = "openalex"
    source_category = SourceCategory.DATABASE
    base_url = "https://api.openalex.org/works"

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        api_key = os.getenv("OPENALEX_API_KEY")
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required for OpenAlex connector")
        self._api_key = api_key.strip()

    @staticmethod
    def _to_candidate(work: dict[str, Any]) -> CandidatePaper:
        authorships = work.get("authorships") or []
        authors: List[str] = []
        country: str | None = None
        for item in authorships:
            author = item.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(str(name))
            if country is None:
                countries = item.get("countries") or []
                if countries:
                    country = str(countries[0])
                else:
                    insts = item.get("institutions") or []
                    for inst in insts:
                        if isinstance(inst, dict) and inst.get("country_code"):
                            country = str(inst["country_code"])
                            break
        year = work.get("publication_year")
        abstract = work.get("abstract")
        if abstract is None:
            abstract = _inverted_index_to_text(work.get("abstract_inverted_index"))
        return CandidatePaper(
            title=str(work.get("display_name") or "Untitled"),
            authors=authors or ["Unknown"],
            year=int(year) if year is not None else None,
            source_database="openalex",
            doi=work.get("doi"),
            abstract=abstract,
            url=work.get("primary_location", {}).get("landing_page_url"),
            source_category=SourceCategory.DATABASE,
            openalex_id=work.get("id"),
            country=country,
        )

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult:
        params: dict[str, str] = {
            "search": query,
            "per_page": str(min(max_results, 200)),
            "api_key": self._api_key,
        }
        filter_parts: list[str] = ["type:article"]
        if date_start:
            filter_parts.append(f"from_publication_date:{date_start}-01-01")
        if date_end:
            filter_parts.append(f"to_publication_date:{date_end}-12-31")
        params["filter"] = ",".join(filter_parts)

        papers: list[CandidatePaper] = []
        async with aiohttp.ClientSession(
            connector=tcp_connector_with_certifi()
        ) as session:
            async with session.get(
                self.base_url, params=params, timeout=30
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"OpenAlex API error {response.status}: {body[:500]}"
                    )
                payload = await response.json()
                for work in payload.get("results", []):
                    papers.append(self._to_candidate(work))

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
