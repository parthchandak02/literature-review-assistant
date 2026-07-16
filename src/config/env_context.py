"""Per-task API key overrides via contextvars (Phase 0.3A).

Concurrent web runs must not mutate ``os.environ`` at request time. Overrides are
resolved from ``RunRequest`` fields and applied only inside the asyncio task that
executes the workflow.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.web.shared import RunRequest

_env_overrides: ContextVar[dict[str, str] | None] = ContextVar("env_overrides", default=None)


def _resolve_from_context(key: str) -> str | None:
    overrides = _env_overrides.get()
    if not overrides:
        return None
    if key in overrides and overrides[key]:
        return overrides[key]
    if key == "GOOGLE_API_KEY" and overrides.get("GEMINI_API_KEY"):
        return overrides["GEMINI_API_KEY"]
    if key == "NCBI_EMAIL" and overrides.get("PUBMED_EMAIL"):
        return overrides["PUBMED_EMAIL"]
    return None


def get_env(key: str, default: str | None = None) -> str | None:
    """Return an env var, preferring per-task overrides over process environment."""
    ctx_val = _resolve_from_context(key)
    if ctx_val is not None:
        return ctx_val
    val = os.environ.get(key)
    if val:
        return val
    if key == "GOOGLE_API_KEY":
        return os.environ.get("GEMINI_API_KEY", default)
    if key == "NCBI_EMAIL":
        return os.environ.get("PUBMED_EMAIL", default)
    return default


def resolve_env_overrides(req: RunRequest) -> dict[str, str]:
    """Build env override mapping from a run request without touching os.environ."""
    overrides: dict[str, str] = {}
    if req.gemini_api_key:
        overrides["GEMINI_API_KEY"] = req.gemini_api_key
    if req.deepseek_api_key:
        overrides["DEEPSEEK_API_KEY"] = req.deepseek_api_key
    if req.openrouter_api_key:
        overrides["OPENROUTER_API_KEY"] = req.openrouter_api_key
    if req.openai_api_key:
        overrides["OPENAI_API_KEY"] = req.openai_api_key
    if req.anthropic_api_key:
        overrides["ANTHROPIC_API_KEY"] = req.anthropic_api_key
    if req.groq_api_key:
        overrides["GROQ_API_KEY"] = req.groq_api_key
    if req.mistral_api_key:
        overrides["MISTRAL_API_KEY"] = req.mistral_api_key
    if req.cohere_api_key:
        overrides["CO_API_KEY"] = req.cohere_api_key
    if req.openalex_api_key:
        overrides["OPENALEX_API_KEY"] = req.openalex_api_key
    if req.ieee_api_key:
        overrides["IEEE_API_KEY"] = req.ieee_api_key
    if req.pubmed_email:
        overrides["PUBMED_EMAIL"] = req.pubmed_email
        overrides["NCBI_EMAIL"] = req.pubmed_email
    if req.pubmed_api_key:
        overrides["PUBMED_API_KEY"] = req.pubmed_api_key
    if req.perplexity_api_key:
        overrides["PERPLEXITY_SEARCH_API_KEY"] = req.perplexity_api_key
    if req.semantic_scholar_api_key:
        overrides["SEMANTIC_SCHOLAR_API_KEY"] = req.semantic_scholar_api_key
    if req.crossref_email:
        overrides["CROSSREF_EMAIL"] = req.crossref_email
    if req.wos_api_key:
        overrides["WOS_API_KEY"] = req.wos_api_key
    if req.scopus_api_key:
        overrides["SCOPUS_API_KEY"] = req.scopus_api_key
    return overrides


def missing_required_env_keys(settings, overrides: dict[str, str]) -> list[str]:
    """Return required env keys absent from overrides and process environment."""
    from src.config.loader import get_required_env_keys

    required = get_required_env_keys(settings)
    missing: list[str] = []
    for key in required:
        if overrides.get(key):
            continue
        if os.environ.get(key):
            continue
        missing.append(key)
    return missing


@contextmanager
def env_override_context(overrides: dict[str, str]) -> Iterator[None]:
    token: Token[dict[str, str] | None] = _env_overrides.set(overrides)
    try:
        yield
    finally:
        _env_overrides.reset(token)


@asynccontextmanager
async def async_env_override_context(overrides: dict[str, str]) -> AsyncIterator[None]:
    token: Token[dict[str, str] | None] = _env_overrides.set(overrides)
    try:
        yield
    finally:
        _env_overrides.reset(token)
