"""API-first scholarly ingestion hub with optional paid adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class ScholarlyIngestionHub:
    """Fetches candidate papers from OpenAlex, Crossref, and Semantic Scholar."""

    contact_email: str | None = None
    timeout_seconds: int = 20
    session: requests.Session = field(default_factory=requests.Session)

    def search_openalex(self, query: str, per_page: int = 25) -> list[dict[str, Any]]:
        params = {
            "search": query,
            "per-page": min(per_page, 200),
        }
        if self.contact_email:
            params["mailto"] = self.contact_email
        response = self.session.get(
            "https://api.openalex.org/works",
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("results", [])
        return [self._normalize_openalex(item) for item in items]

    def search_crossref(self, query: str, rows: int = 25) -> list[dict[str, Any]]:
        params = {"query": query, "rows": min(rows, 200)}
        if self.contact_email:
            params["mailto"] = self.contact_email
        response = self.session.get(
            "https://api.crossref.org/works",
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("message", {}).get("items", [])
        return [self._normalize_crossref(item) for item in items]

    def search_semantic_scholar(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": "title,abstract,url,externalIds,year,venue",
        }
        response = self.session.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        return [self._normalize_semantic_scholar(item) for item in items]

    def search_core_sources(
        self,
        query: str,
        per_source_limit: int = 25,
    ) -> dict[str, list[dict[str, Any]]]:
        """Searches the API-first baseline sources with graceful partial results."""

        results: dict[str, list[dict[str, Any]]] = {
            "openalex": [],
            "crossref": [],
            "semantic_scholar": [],
        }

        for name, call in (
            ("openalex", self.search_openalex),
            ("crossref", self.search_crossref),
            ("semantic_scholar", self.search_semantic_scholar),
        ):
            try:
                results[name] = call(query, per_source_limit)
            except Exception:
                results[name] = []

        return results

    @staticmethod
    def _normalize_openalex(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": item.get("title", ""),
            "abstract": item.get("abstract", ""),
            "url": item.get("primary_location", {}).get("landing_page_url"),
            "doi": item.get("doi"),
            "source": "openalex",
        }

    @staticmethod
    def _normalize_crossref(item: dict[str, Any]) -> dict[str, Any]:
        title = ""
        titles = item.get("title", [])
        if titles:
            title = titles[0]
        return {
            "title": title,
            "abstract": item.get("abstract", "") or "",
            "url": item.get("URL"),
            "doi": item.get("DOI"),
            "source": "crossref",
        }

    @staticmethod
    def _normalize_semantic_scholar(item: dict[str, Any]) -> dict[str, Any]:
        external_ids = item.get("externalIds", {})
        return {
            "title": item.get("title", ""),
            "abstract": item.get("abstract", "") or "",
            "url": item.get("url"),
            "doi": external_ids.get("DOI"),
            "source": "semantic_scholar",
        }
