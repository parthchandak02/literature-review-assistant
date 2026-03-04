#!/usr/bin/env python3
"""Live smoke-test for all configured search connectors.

Loads API keys from .env and config from config/review.yaml, builds
the exact query each connector will use in a real run (via
build_database_query), fires a small search (max 5 results), and
reports HTTP status, record count, and a sample title.

Usage:
    uv run python scripts/test_search_connectors.py
    uv run python scripts/test_search_connectors.py --db scopus pubmed

Options:
    --db DB [DB ...]   Only test the specified databases.
    --max INT          Max results to fetch per connector (default 5).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load .env from project root before importing any src modules.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.config.loader import load_configs                        # noqa: E402
from src.models import ReviewConfig                               # noqa: E402

console = Console()

_CONNECTOR_NAMES = [
    "scopus",
    "web_of_science",
    "pubmed",
    "openalex",
    "semantic_scholar",
    "ieee_xplore",
    "crossref",
]


def _build_connector(name: str, workflow_id: str):
    """Instantiate connector by name. Returns None if key is missing."""
    try:
        if name == "scopus":
            from src.search.scopus import ScopusConnector
            return ScopusConnector(workflow_id)
        if name == "web_of_science":
            from src.search.web_of_science import WebOfScienceConnector
            return WebOfScienceConnector(workflow_id)
        if name == "pubmed":
            from src.search.pubmed import PubMedConnector
            return PubMedConnector(workflow_id)
        if name == "openalex":
            from src.search.openalex import OpenAlexConnector
            return OpenAlexConnector(workflow_id)
        if name == "semantic_scholar":
            from src.search.semantic_scholar import SemanticScholarConnector
            return SemanticScholarConnector(workflow_id)
        if name == "ieee_xplore":
            from src.search.ieee_xplore import IEEEXploreConnector
            return IEEEXploreConnector(workflow_id)
        if name == "crossref":
            from src.search.crossref import CrossrefConnector
            return CrossrefConnector(workflow_id)
    except ValueError as exc:
        return str(exc)  # key missing
    except Exception as exc:
        return f"INIT ERROR: {exc}"
    return None


async def _probe_connector(connector, query: str, max_results: int, date_start: int, date_end: int) -> dict:
    """Run a small search and return a result summary dict."""
    try:
        result = await connector.search(
            query=query,
            max_results=max_results,
            date_start=date_start,
            date_end=date_end,
        )
        papers = result.papers
        sample_title = papers[0].title[:80] if papers else None
        return {
            "status": "OK",
            "count": result.records_retrieved,
            "returned": len(papers),
            "sample": sample_title,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "count": 0,
            "returned": 0,
            "sample": None,
            "error": str(exc)[:120],
        }


async def main(target_dbs: list[str], max_results: int) -> int:
    review, _ = load_configs(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
    )

    console.print(f"\n[bold]Search Connector Smoke Test[/bold]")
    console.print(f"Review: [cyan]{review.research_question[:80]}...[/cyan]\n")

    dbs_to_test = target_dbs or _CONNECTOR_NAMES
    workflow_id = "smoke_test"

    def _get_query(config: ReviewConfig, db: str) -> str:
        """Build query for a given database. Prefers search_overrides, then fallback."""
        if config.search_overrides and db in config.search_overrides:
            return config.search_overrides[db]
        kws = config.keywords or []
        kw_part1 = " OR ".join(f'"{k}"' for k in kws[:8]) if kws else f'"{config.pico.intervention[:60]}"'
        kw_part2 = " OR ".join(f'"{k}"' for k in kws[8:16]) if len(kws) > 8 else kw_part1
        if db == "pubmed":
            return f"({kw_part1}) AND ({config.pico.population}[Title/Abstract])"
        if db == "scopus":
            date_s = config.date_range_start or 2009
            date_e = config.date_range_end or 2027
            return f"TITLE-ABS-KEY({kw_part1}) AND TITLE-ABS-KEY({kw_part2}) AND PUBYEAR > {date_s - 1} AND PUBYEAR < {date_e + 1}"
        if db == "web_of_science":
            date_s = config.date_range_start or 2010
            date_e = config.date_range_end or 2026
            # Each term needs own TS= prefix -- NOT TS=("a" OR "b")
            wos_kws = config.keywords or []
            wos_part1 = " OR ".join(f'TS="{k}"' for k in wos_kws[:8]) if wos_kws else f'TS="{config.pico.intervention[:60]}"'
            wos_part2 = " OR ".join(f'TS="{k}"' for k in wos_kws[8:16]) if len(wos_kws) > 8 else wos_part1
            return f"({wos_part1}) AND ({wos_part2}) AND PY={date_s}-{date_e}"
        if db == "ieee_xplore":
            return f"({kw_part1}) AND ({kw_part2})"
        if db in ("semantic_scholar", "perplexity_search"):
            return " ".join(kws[:8])
        return f"({kw_part1})"

    rows: list[tuple[str, str, str, str, str]] = []

    for db in dbs_to_test:
        console.print(f"  Testing [yellow]{db}[/yellow]...", end="")
        connector = _build_connector(db, workflow_id)
        if connector is None:
            console.print(" [dim]skipped (no connector)[/dim]")
            rows.append((db, "SKIP", "no connector impl", "-", ""))
            continue
        if isinstance(connector, str):
            # Init error or missing key
            console.print(f" [red]FAIL[/red] - {connector}")
            rows.append((db, "NO KEY", connector[:60], "-", ""))
            continue

        query = _get_query(review, db)
        result = await _probe_connector(
            connector, query, max_results,
            review.date_range_start or 2010,
            review.date_range_end or 2026,
        )
        status_str = f"[green]{result['status']}[/green]" if result["status"] == "OK" else f"[red]{result['status']}[/red]"
        console.print(f" {status_str} ({result['returned']} / ~{result['count']} records)")
        if result["error"]:
            console.print(f"    [red]Error:[/red] {result['error']}")
        rows.append((
            db,
            result["status"],
            str(result["count"]),
            str(result["returned"]),
            result["sample"] or result.get("error") or "",
        ))

    # Summary table
    console.print()
    table = Table(title="Connector Test Results")
    table.add_column("Database", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Total hits", justify="right")
    table.add_column("Returned", justify="right")
    table.add_column("Sample / Error", style="dim", max_width=60)

    for db, status, total, returned, sample in rows:
        style = "green" if status == "OK" else ("yellow" if status == "SKIP" else "red")
        table.add_row(db, f"[{style}]{status}[/{style}]", total, returned, sample)

    console.print(table)

    console.print("\n[bold]Queries used:[/bold]")
    for db in dbs_to_test:
        q = _get_query(review, db)
        console.print(f"  [cyan]{db}:[/cyan]")
        console.print(f"    {q[:200]}")
        console.print()

    failed = [r for r in rows if r[1] not in ("OK", "SKIP")]
    if failed:
        console.print(f"[red]{len(failed)} connector(s) failed.[/red]")
        return 1
    console.print("[green]All connectors OK.[/green]")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live smoke-test search connectors")
    parser.add_argument(
        "--db",
        nargs="+",
        metavar="DB",
        default=[],
        help="Databases to test (default: all)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=5,
        metavar="INT",
        help="Max results per connector (default 5)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.db, args.max)))
