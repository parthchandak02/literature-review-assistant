#!/usr/bin/env python3
"""Test full-text retrieval for included papers from a previous workflow.

Reports how many papers get full text from each tier vs abstract fallback.
Use this to assess full-text coverage before committing to a re-run.

Usage:
    uv run python scripts/test_fulltext_retrieval.py --run-dir <path-to-run>
    uv run python scripts/test_fulltext_retrieval.py --workflow-id wf-58bd9dd5

Example:
    uv run python scripts/test_fulltext_retrieval.py --workflow-id wf-0004 -v
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.table import Table

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback
from src.extraction.table_extraction import fetch_full_text

console = Console()

# All known sources from fetch_full_text tiers, in priority order.
_ALL_SOURCES: list[tuple[str, str]] = [
    ("publisher_direct_pdf", "Tier 0/0.5 Publisher-direct or citation_pdf_url PDF"),
    ("landing_page_pdf", "Tier 6  Landing-page PDF (JSON-LD / PDF anchors)"),
    ("landing_page_text", "Tier 6  Landing-page HTML text"),
    ("unpaywall_pdf", "Tier 1  Unpaywall PDF"),
    ("unpaywall_text", "Tier 1  Unpaywall text"),
    ("arxiv", "Tier 1b arXiv PDF"),
    ("semanticscholar_pdf", "Tier 2a Semantic Scholar PDF"),
    ("semantic_scholar", "Tier 2a Semantic Scholar (alt label)"),
    ("biorxiv_medrxiv", "Tier 2b bioRxiv/medRxiv PDF"),
    ("core", "Tier 2  CORE text"),
    ("core_pdf", "Tier 2  CORE PDF"),
    ("openalex_content", "Tier 2c OpenAlex Content PDF"),
    ("europepmc", "Tier 2d Europe PMC text"),
    ("sciencedirect", "Tier 3  ScienceDirect JSON text"),
    ("sciencedirect_pdf", "Tier 3  ScienceDirect PDF"),
    ("pmc", "Tier 4  PubMed Central XML"),
    ("crossref", "Tier 5  Crossref link"),
    ("abstract", "Fallback abstract only"),
]
_SOURCE_LABEL = {src: label for src, label in _ALL_SOURCES}


async def _resolve_db_path(
    run_dir: str | None, workflow_id: str | None, run_root: str
) -> pathlib.Path | None:
    if run_dir:
        p = pathlib.Path(run_dir).resolve()
        db = p / "runtime.db"
        return db if db.exists() else None
    if workflow_id:
        entry = await find_by_workflow_id(run_root, workflow_id)
        if entry is None:
            entry = await find_by_workflow_id_fallback(run_root, workflow_id)
        if entry and entry.db_path:
            return pathlib.Path(entry.db_path)
    return None


async def main(
    run_dir: str | None,
    workflow_id: str | None,
    run_root: str,
    verbose: bool = False,
) -> int:
    db_path = await _resolve_db_path(run_dir, workflow_id, run_root)
    if not db_path or not db_path.exists():
        console.print("[red]ERROR: Could not resolve runtime.db. Provide --run-dir or --workflow-id.[/]")
        return 1

    use_openalex = bool(os.getenv("OPENALEX_API_KEY", "").strip())
    if use_openalex:
        console.print("[green]OPENALEX_API_KEY found -- OpenAlex Content tier enabled[/]")
    else:
        console.print("[dim]No OPENALEX_API_KEY -- OpenAlex Content tier disabled[/]")

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        cursor = await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            console.print("[red]ERROR: No workflow in DB.[/]")
            return 1
        wf_id = str(row[0])

        included_ids = await repo.get_included_paper_ids(wf_id)
        if not included_ids:
            included_ids = await repo.get_title_abstract_include_ids(wf_id)
        if not included_ids:
            console.print("[yellow]No included papers found. Run may not have completed screening.[/]")
            return 0

        papers = await repo.load_papers_by_ids(included_ids)
        papers_with_doi = [p for p in papers if p.doi]
        papers_no_doi = [p for p in papers if not p.doi]

    console.print(
        f"[bold]Testing full-text retrieval for {len(papers)} included papers "
        f"({len(papers_with_doi)} with DOI, {len(papers_no_doi)} without)[/]\n"
    )

    source_counts: dict[str, int] = {}
    results: list[dict[str, object]] = []

    for i, paper in enumerate(papers, 1):
        console.print(f"  [{i}/{len(papers)}] {paper.title[:70]}...", end="\r")
        if not paper.doi and not paper.url:
            source = "abstract"
            source_counts[source] = source_counts.get(source, 0) + 1
            results.append(
                {
                    "title": paper.title[:55],
                    "doi": "N/A",
                    "url": paper.url or "",
                    "source": source,
                    "pdf": "NO",
                    "diagnostics": [],
                }
            )
            continue

        diag: list[str] = []
        ft = await fetch_full_text(
            doi=paper.doi,
            url=paper.url,
            pmid=None,
            use_sciencedirect=True,
            use_unpaywall=True,
            use_pmc=True,
            use_core=True,
            use_europepmc=True,
            use_semanticscholar=True,
            use_arxiv_pdf=True,
            use_biorxiv_medrxiv=True,
            use_openalex_content=use_openalex,
            use_crossref_links=True,
            use_landing_page=True,
            diagnostics=diag,
        )
        source = ft.source
        source_counts[source] = source_counts.get(source, 0) + 1
        pdf_ok = "YES" if ft.pdf_bytes else "NO"
        results.append(
            {
                "title": paper.title[:55],
                "doi": (paper.doi or "")[:30],
                "url": (paper.url or "")[:40],
                "source": source,
                "pdf": pdf_ok,
                "diagnostics": diag,
            }
        )

    console.print()  # clear progress line

    # Per-paper results table
    table = Table(title="Full-Text Retrieval Results", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="dim", max_width=56)
    table.add_column("DOI / URL", max_width=32)
    table.add_column("Source", min_width=20)
    table.add_column("PDF", min_width=5)
    for i, r in enumerate(results, 1):
        doi_or_url = r["doi"] if r["doi"] != "N/A" else r["url"][:30]
        src = str(r["source"])
        color = "green" if src != "abstract" else "red"
        table.add_row(
            str(i),
            str(r["title"]),
            str(doi_or_url),
            f"[{color}]{src}[/]",
            str(r["pdf"]),
        )
    console.print(table)

    # Verbose: per-paper tier failure diagnostics
    if verbose:
        console.print("\n[bold]Verbose: per-paper tier diagnostics[/]\n")
        for i, r in enumerate(results, 1):
            diag = r.get("diagnostics", [])
            if diag:
                label = str(r["doi"]) if r["doi"] != "N/A" else str(r["url"])[:50]
                console.print(f"  [cyan]#{i}[/] {label} -> [bold]{r['source']}[/]")
                for d in diag:
                    console.print(f"    [dim]{d}[/]")

    # Summary by source
    summary = Table(title="Summary by Source")
    summary.add_column("Source", style="cyan")
    summary.add_column("Count", style="green", justify="right")
    summary.add_column("Description", style="dim")
    for src, label in _ALL_SOURCES:
        cnt = source_counts.get(src, 0)
        if cnt > 0 or src == "abstract":
            color = "red" if src == "abstract" else "green"
            summary.add_row(f"[{color}]{src}[/]", str(cnt), label)
    # Catch any source not in _ALL_SOURCES (future tiers)
    for src, cnt in sorted(source_counts.items()):
        if src not in _SOURCE_LABEL:
            summary.add_row(f"[yellow]{src}[/]", str(cnt), "(unknown source)")
    console.print(summary)

    total = len(papers)
    fulltext_total = sum(cnt for src, cnt in source_counts.items() if src != "abstract")
    pdf_total = sum(
        cnt
        for src, cnt in source_counts.items()
        if "pdf" in src or src in ("pmc", "europepmc", "arxiv", "biorxiv_medrxiv")
    )
    abstract_total = source_counts.get("abstract", 0)
    console.print(
        f"\n[bold]Full-text coverage:[/] {fulltext_total}/{total} ({100 * fulltext_total / total:.0f}%)"
    )
    console.print(f"[bold]PDF coverage:[/] {pdf_total}/{total} ({100 * pdf_total / total:.0f}%)")
    console.print(
        f"[bold]Abstract-only fallback:[/] [red]{abstract_total}/{total}[/] "
        f"({100 * abstract_total / total:.0f}%)"
    )

    from src.extraction.table_extraction import _is_elsevier_doi

    abstract_dois = [str(r["doi"]) for r in results if r["source"] == "abstract" and r["doi"] not in ("N/A", "")]
    non_elsevier = sum(1 for d in abstract_dois if not _is_elsevier_doi(d))
    if non_elsevier > 0:
        console.print(
            f"\n[dim]{non_elsevier} abstract-only paper(s) have non-Elsevier DOIs "
            "(Wiley, MDPI, Sage, T&F, etc.) -- ScienceDirect tier only works for Elsevier content.[/]"
        )
    no_oa = sum(1 for r in results if any("no OA location" in str(d) for d in r.get("diagnostics", [])))
    if no_oa > 0:
        console.print(
            f"[dim]For 'no OA location' papers: add CORE_API_KEY (free at core.ac.uk/api-keys/register) "
            f"to try CORE institutional repos ({no_oa} paper(s) may benefit).[/]"
        )
    if not use_openalex:
        console.print(
            "[dim]Add OPENALEX_API_KEY to .env to enable OpenAlex Content tier "
            "(~60M OA works, $0.01/file).[/]"
        )

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test full-text retrieval for included papers from a workflow run."
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Path to run directory (e.g. runs/2026-03-02/.../run_06-33-08PM)",
    )
    parser.add_argument(
        "--workflow-id",
        default=None,
        help="Workflow ID (e.g. wf-58bd9dd5)",
    )
    parser.add_argument(
        "--run-root",
        default="runs",
        help="Root directory for runs (for workflow-id lookup)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show per-paper tier failure reasons",
    )
    args = parser.parse_args()
    if not args.run_dir and not args.workflow_id:
        parser.error("Provide --run-dir or --workflow-id")
    sys.exit(asyncio.run(main(args.run_dir, args.workflow_id, args.run_root, args.verbose)))
