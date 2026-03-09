"""Live smoke test for the OpenAlex connector quality filters.

Runs two searches side-by-side:
  1. Unfiltered (type:article only) -- baseline result count
  2. Quality-filtered (is_core:true + journal type + is_retracted:false) -- what we actually use

Then shows journal names for the top results from the filtered search and performs
a sample DOI venue lookup to demonstrate that endpoint.

Usage:
    uv run python scripts/test_openalex_quality.py
    uv run python scripts/test_openalex_quality.py --query "exercise intervention sleep quality adults"
    uv run python scripts/test_openalex_quality.py --max 30
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.ssl_context import tcp_connector_with_certifi  # noqa: E402

console = Console()

_BASE_URL = "https://api.openalex.org/works"
_SELECT = "id,display_name,doi,publication_year,primary_location,cited_by_count,is_retracted"

_DEFAULT_QUERY = "systematic review intervention effectiveness outcome population"


async def _fetch(session: aiohttp.ClientSession, params: dict) -> dict:
    async with session.get(_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status != 200:
            body = await r.text()
            console.print(f"[red]OpenAlex API error {r.status}: {body[:300]}[/red]")
            return {}
        return await r.json()


async def run(query: str, max_results: int, api_key: str) -> None:
    date_filter = "from_publication_date:2010-01-01,to_publication_date:2026-12-31"

    baseline_filter = f"type:article,{date_filter}"
    quality_filter = (
        f"type:article,"
        f"primary_location.source.type:journal,"
        f"primary_location.source.is_core:true,"
        f"is_retracted:false,"
        f"{date_filter}"
    )

    async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
        console.rule("[bold cyan]OpenAlex Quality Filter Smoke Test[/bold cyan]")
        console.print(f"Query: [italic]{query}[/italic]\n")

        # -- Baseline count (no quality filter) --
        base_params = {
            "search": query,
            "filter": baseline_filter,
            "per_page": "1",
            "api_key": api_key,
        }
        base_data = await _fetch(session, base_params)
        base_total = (base_data.get("meta") or {}).get("count", 0)

        # -- Quality-filtered count --
        qual_params = {
            "search": query,
            "filter": quality_filter,
            "per_page": "1",
            "api_key": api_key,
        }
        qual_data = await _fetch(session, qual_params)
        qual_total = (qual_data.get("meta") or {}).get("count", 0)

        console.print(f"Baseline (type:article only):       [bold]{base_total:,}[/bold] total results")
        console.print(f"Quality-filtered (is_core:true):    [bold green]{qual_total:,}[/bold green] total results")
        if base_total > 0:
            pct = qual_total / base_total * 100
            console.print(f"Retention rate:                     [bold]{pct:.1f}%[/bold] of baseline\n")

        # -- Fetch top results with journal details --
        top_params = {
            "search": query,
            "filter": quality_filter,
            "per_page": str(min(max_results, 200)),
            "select": _SELECT,
            "sort": "cited_by_count:desc",
            "api_key": api_key,
        }
        top_data = await _fetch(session, top_params)
        results = top_data.get("results", [])

        if not results:
            console.print("[yellow]No results returned.[/yellow]")
            return

        # Build results table
        table = Table(
            title=f"Top {len(results)} Results (sorted by citations, quality-filtered)",
            show_lines=True,
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Year", width=5)
        table.add_column("Citations", justify="right", width=8)
        table.add_column("Journal", style="cyan", width=35)
        table.add_column("Title", width=55)

        sample_doi: str | None = None
        for i, work in enumerate(results, 1):
            year = str(work.get("publication_year") or "-")
            cites = str(work.get("cited_by_count") or 0)
            title = str(work.get("display_name") or "Untitled")[:80]
            source = (work.get("primary_location") or {}).get("source") or {}
            journal_name = source.get("display_name") or "[dim]unknown[/dim]"
            doi = work.get("doi") or ""
            if sample_doi is None and doi:
                sample_doi = doi
            table.add_row(str(i), year, cites, journal_name, title)

        console.print(table)

        # -- Unique journals summary --
        journal_counts: dict[str, int] = {}
        for work in results:
            source = (work.get("primary_location") or {}).get("source") or {}
            j = source.get("display_name") or "Unknown"
            journal_counts[j] = journal_counts.get(j, 0) + 1

        j_table = Table(title="Unique Journals in Result Set", show_lines=False)
        j_table.add_column("Journal", style="cyan")
        j_table.add_column("Papers", justify="right")
        for j, count in sorted(journal_counts.items(), key=lambda x: -x[1]):
            j_table.add_row(j, str(count))
        console.print(j_table)

        # -- DOI venue lookup demo --
        if sample_doi:
            console.rule("[bold]DOI Venue Lookup Demo[/bold]")
            clean = sample_doi.lstrip("https://doi.org/").lstrip("http://doi.org/")
            doi_url = f"{_BASE_URL}/https://doi.org/{clean}"
            doi_params = {
                "select": "primary_location,cited_by_count",
                "api_key": api_key,
            }
            console.print(f"Looking up DOI: [italic]{clean}[/italic]")
            async with session.get(doi_url, params=doi_params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    doi_data = await r.json()
                    loc = doi_data.get("primary_location") or {}
                    src = loc.get("source") or {}
                    v_table = Table(title="Venue Metadata from DOI Lookup", show_lines=False)
                    v_table.add_column("Field", style="bold")
                    v_table.add_column("Value")
                    v_table.add_row("Journal name", src.get("display_name") or "-")
                    v_table.add_row("Type", src.get("type") or "-")
                    v_table.add_row("is_core", str(src.get("is_core")))
                    v_table.add_row("is_in_doaj", str(src.get("is_in_doaj")))
                    v_table.add_row("is_oa", str(src.get("is_oa")))
                    v_table.add_row("ISSN-L", src.get("issn_l") or "-")
                    v_table.add_row("Publisher", src.get("host_organization_name") or "-")
                    v_table.add_row("Version", loc.get("version") or "-")
                    v_table.add_row("Citations", str(doi_data.get("cited_by_count") or 0))
                    console.print(v_table)
                else:
                    console.print(f"[yellow]DOI lookup returned {r.status}[/yellow]")
        else:
            console.print("[dim]No DOI found in result set for demo lookup.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test OpenAlex quality filters")
    parser.add_argument(
        "--query",
        default=_DEFAULT_QUERY,
        help="Search query to test",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20,
        dest="max_results",
        help="Max results to fetch for the detail table (default: 20)",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENALEX_API_KEY", "").strip()
    if not api_key:
        console.print("[red]OPENALEX_API_KEY not set. Add it to .env or export it.[/red]")
        sys.exit(1)

    asyncio.run(run(args.query, args.max_results, api_key))


if __name__ == "__main__":
    main()
