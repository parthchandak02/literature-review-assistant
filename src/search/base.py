"""Search connector protocol."""

from __future__ import annotations

from typing import Protocol

from src.models import SearchResult, SourceCategory


class SearchConnector(Protocol):
    name: str
    source_category: SourceCategory

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_start: int | None = None,
        date_end: int | None = None,
    ) -> SearchResult | list[SearchResult]:
        """Run a search and return one or more typed result groups."""
