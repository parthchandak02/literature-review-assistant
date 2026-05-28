"""Full-text retrieval bounded context for systematic review papers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.fulltext.retrieval import (
    FullTextResult,
    fetch_full_text,
    resolve_landing_page,
)


@dataclass(frozen=True)
class FullTextResolveRequest:
    doi: str | None = None
    url: str | None = None
    pmid: str | None = None
    diagnostics: list[str] | None = None
    tier_flags: dict[str, bool] | None = None


class FullTextResolver:
    """Deep module: tiered full-text resolution behind a small interface."""

    async def resolve(
        self,
        *,
        doi: str | None = None,
        url: str | None = None,
        pmid: str | None = None,
        diagnostics: list[str] | None = None,
        **tier_kwargs: Any,
    ) -> FullTextResult:
        return await fetch_full_text(
            doi=doi,
            url=url,
            pmid=pmid,
            diagnostics=diagnostics,
            **tier_kwargs,
        )


__all__ = [
    "FullTextResult",
    "FullTextResolveRequest",
    "FullTextResolver",
    "fetch_full_text",
    "resolve_landing_page",
]
