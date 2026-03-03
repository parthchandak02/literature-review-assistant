#!/usr/bin/env python3
"""Validate Scopus API key by testing Search and Abstract Retrieval APIs.

Usage:
    uv run python scripts/validate_scopus_key.py
    SCOPUS_API_KEY=xxx uv run python scripts/validate_scopus_key.py

Loads SCOPUS_API_KEY from .env or environment. Reports HTTP status,
X-RateLimit-Remaining if present, and sample result counts.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load .env from project root
_load_env = load_dotenv(Path(__file__).resolve().parent.parent / ".env")

console = Console()

_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
_ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi"
_SAMPLE_DOI = "10.1016/j.jacc.2020.01.012"


async def _test_search(api_key: str) -> dict:
    """Test Scopus Search API. Returns status, headers, and result summary."""
    import aiohttp

    from src.utils.ssl_context import tcp_connector_with_certifi

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    params = {
        "query": "TITLE-ABS-KEY(medicine)",
        "count": "5",
        "start": "0",
    }
    async with aiohttp.ClientSession(
        connector=tcp_connector_with_certifi(),
        headers=headers,
    ) as session:
        async with session.get(_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.text()
            rate_remaining = resp.headers.get("X-RateLimit-Remaining")
            rate_reset = resp.headers.get("X-RateLimit-Reset")
            try:
                import json
                data = json.loads(body)
                sr = data.get("search-results", {})
                total = int(sr.get("opensearch:totalResults", 0))
                entries = sr.get("entry", [])
                if isinstance(entries, list) and len(entries) == 1 and "error" in entries[0]:
                    total = 0
                    entries = []
            except Exception:
                total = 0
                entries = []
            return {
                "status": resp.status,
                "rate_remaining": rate_remaining,
                "rate_reset": rate_reset,
                "total_results": total,
                "returned_count": len(entries),
                "body_preview": body[:200] if body else "",
            }


async def _test_abstract(api_key: str, doi: str = _SAMPLE_DOI) -> dict:
    """Test Abstract Retrieval API. Returns status, headers, and success flag."""
    import aiohttp

    from src.utils.ssl_context import tcp_connector_with_certifi

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    url = f"{_ABSTRACT_URL}/{doi}"
    async with aiohttp.ClientSession(
        connector=tcp_connector_with_certifi(),
        headers=headers,
    ) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            body = await resp.text()
            rate_remaining = resp.headers.get("X-RateLimit-Remaining")
            rate_reset = resp.headers.get("X-RateLimit-Reset")
            has_abstract = False
            try:
                import json
                data = json.loads(body)
                resp_obj = data.get("abstracts-retrieval-response", {})
                coredata = resp_obj.get("coredata", {}) or {}
                abstract = coredata.get("dc:description") or ""
                has_abstract = bool(abstract and len(abstract) > 20)
            except Exception:
                pass
            return {
                "status": resp.status,
                "rate_remaining": rate_remaining,
                "rate_reset": rate_reset,
                "has_abstract": has_abstract,
                "body_preview": body[:200] if body else "",
            }


async def main() -> int:
    api_key = os.getenv("SCOPUS_API_KEY", "").strip()
    if not api_key:
        console.print("[red]Error:[/] SCOPUS_API_KEY not set. Add it to .env or pass via environment.")
        return 1

    console.print("[bold]Validating Scopus API key...[/bold]\n")

    search_result = await _test_search(api_key)
    abstract_result = await _test_abstract(api_key)

    table = Table(title="Scopus API Validation Results")
    table.add_column("API", style="cyan")
    table.add_column("HTTP Status", style="green")
    table.add_column("Rate Limit Remaining", style="yellow")
    table.add_column("Details", style="white")
    table.add_row(
        "Scopus Search",
        str(search_result["status"]),
        search_result.get("rate_remaining") or "N/A",
        f"Total: {search_result['total_results']}, returned: {search_result['returned_count']}",
    )
    table.add_row(
        "Abstract Retrieval",
        str(abstract_result["status"]),
        abstract_result.get("rate_remaining") or "N/A",
        f"Abstract found: {abstract_result['has_abstract']}",
    )
    console.print(table)

    success = True
    if search_result["status"] != 200:
        console.print(f"[red]Search API failed: HTTP {search_result['status']}[/red]")
        if search_result.get("body_preview"):
            console.print(f"[dim]{search_result['body_preview']}[/dim]")
        success = False
    elif search_result["total_results"] == 0 and search_result["returned_count"] == 0:
        console.print("[yellow]Search returned 0 results (query may be too narrow or key has limited access)[/yellow]")

    if abstract_result["status"] != 200:
        console.print(f"[red]Abstract API failed: HTTP {abstract_result['status']}[/red]")
        if abstract_result.get("body_preview"):
            console.print(f"[dim]{abstract_result['body_preview']}[/dim]")
        success = False

    if success:
        console.print("\n[green]Key validation PASSED.[/green]")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
