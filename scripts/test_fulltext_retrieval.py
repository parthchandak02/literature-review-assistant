#!/usr/bin/env python3
"""Test full-text retrieval for included papers from a previous workflow.

Reports how many papers get full text from each tier (ScienceDirect, Unpaywall,
PMC) vs abstract fallback. Use this to assess full-text coverage before
committing to a Scopus-only run or adding institutional token support.

Usage:
    uv run python scripts/test_fulltext_retrieval.py --run-dir <path-to-run>
    uv run python scripts/test_fulltext_retrieval.py --workflow-id wf-58bd9dd5

Example:
    uv run python scripts/test_fulltext_retrieval.py --run-dir runs/2026-03-02/what-is-the-effectiveness-of-artificial-intelligence-ai-interven/run_06-33-08PM
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback
from src.extraction.table_extraction import fetch_full_text

console = Console()


async def _resolve_db_path(run_dir: str | None, workflow_id: str | None, run_root: str) -> pathlib.Path | None:
    """Resolve runtime.db path from run-dir or workflow-id."""
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


async def main(run_dir: str | None, workflow_id: str | None, run_root: str, verbose: bool = False) -> int:
    db_path = await _resolve_db_path(run_dir, workflow_id, run_root)
    if not db_path or not db_path.exists():
        console.print("[red]ERROR: Could not resolve runtime.db. Provide --run-dir or --workflow-id.[/]")
        return 1

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

    counts = {
        "sciencedirect": 0,
        "sciencedirect_pdf": 0,
        "unpaywall_pdf": 0,
        "unpaywall_text": 0,
        "core": 0,
        "core_pdf": 0,
        "pmc": 0,
        "abstract": 0,
    }
    results: list[dict[str, str]] = []

    for i, paper in enumerate(papers, 1):
        if not paper.doi:
            counts["abstract"] += 1
            results.append(
                {
                    "title": paper.title[:55],
                    "doi": "N/A",
                    "source": "abstract (no DOI)",
                    "pdf": "N/A",
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
            diagnostics=diag,
        )
        source = ft.source
        counts[source] = counts.get(source, 0) + 1
        pdf_ok = "YES" if ft.pdf_bytes else "NO"
        results.append(
            {
                "title": paper.title[:55],
                "doi": paper.doi[:30],
                "source": source,
                "pdf": pdf_ok,
                "diagnostics": diag,
            }
        )

    table = Table(title="Full-Text Retrieval Results", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="dim", max_width=56)
    table.add_column("DOI", max_width=32)
    table.add_column("Source", min_width=14)
    table.add_column("PDF", min_width=6)
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r["title"], r["doi"], r["source"], r["pdf"])
    console.print(table)

    if verbose:
        console.print("\n[bold]Verbose: per-paper tier failures[/]\n")
        for i, r in enumerate(results, 1):
            diag = r.get("diagnostics", [])
            if diag:
                console.print(f"  [cyan]#{i}[/] {r['doi']}")
                for d in diag:
                    console.print(f"    [dim]{d}[/]")

    summary = Table(title="Summary by Source")
    summary.add_column("Source", style="cyan")
    summary.add_column("Count", style="green")
    summary.add_column("Notes", style="dim")
    summary.add_row("ScienceDirect (JSON text)", str(counts["sciencedirect"]), "Elsevier OA; API key only")
    summary.add_row("ScienceDirect PDF", str(counts.get("sciencedirect_pdf", 0)), "Requires SCOPUS_INSTTOKEN")
    summary.add_row("Unpaywall PDF", str(counts["unpaywall_pdf"]), "Open-access PDF")
    summary.add_row("Unpaywall text", str(counts["unpaywall_text"]), "OA HTML/text")
    summary.add_row("CORE API", str(counts.get("core", 0) + counts.get("core_pdf", 0)), "Requires CORE_API_KEY")
    summary.add_row("PubMed Central", str(counts["pmc"]), "NIH-funded OA XML")
    summary.add_row("Abstract fallback", str(counts["abstract"]), "No full text found")
    console.print(summary)

    pdf_total = counts["unpaywall_pdf"] + counts.get("sciencedirect_pdf", 0) + counts.get("core_pdf", 0)
    fulltext_total = (
        counts["sciencedirect"]
        + counts.get("sciencedirect_pdf", 0)
        + counts["unpaywall_pdf"]
        + counts["unpaywall_text"]
        + counts.get("core", 0)
        + counts.get("core_pdf", 0)
        + counts["pmc"]
    )
    console.print(
        f"\n[bold]Full-text coverage:[/] {fulltext_total}/{len(papers)} ({100 * fulltext_total / len(papers):.0f}%)"
    )
    console.print(f"[bold]PDF coverage:[/] {pdf_total}/{len(papers)} ({100 * pdf_total / len(papers):.0f}%)")
    # Explain abstract fallbacks: non-Elsevier DOIs cannot use ScienceDirect
    from src.extraction.table_extraction import _is_elsevier_doi

    abstract_dois = [r["doi"] for r in results if r["source"] == "abstract" and r["doi"] != "N/A"]
    non_elsevier = sum(1 for d in abstract_dois if not _is_elsevier_doi(d))
    if non_elsevier > 0:
        console.print(
            f"\n[dim]{non_elsevier} abstract-only paper(s) have non-Elsevier DOIs "
            "(Wiley, MDPI, SAGE, T&F, etc.) -- ScienceDirect only works for Elsevier content.[/]"
        )
    console.print(
        "\n[dim]For ScienceDirect PDFs: add SCOPUS_INSTTOKEN (institutional token). "
        "Scopus subscription alone does not grant ScienceDirect full-text. Contact Elsevier "
        "Research Product APIs support or your librarian.[/]"
    )
    no_oa = sum(1 for r in results if any("no OA location" in d for d in r.get("diagnostics", [])))
    if no_oa > 0:
        console.print(
            f"[dim]For 'no OA location' papers: add CORE_API_KEY (free at core.ac.uk/api-keys/register) "
            f"to try CORE institutional repos ({no_oa} paper(s) may benefit).[/]"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test full-text retrieval for included papers from a workflow run.")
    parser.add_argument(
        "--run-dir", default=None, help="Path to run directory (e.g. runs/2026-03-02/.../run_06-33-08PM)"
    )
    parser.add_argument("--workflow-id", default=None, help="Workflow ID (e.g. wf-58bd9dd5)")
    parser.add_argument("--run-root", default="runs", help="Root directory for runs (for workflow-id lookup)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show per-paper tier failure reasons")
    args = parser.parse_args()
    if not args.run_dir and not args.workflow_id:
        parser.error("Provide --run-dir or --workflow-id")
    sys.exit(asyncio.run(main(args.run_dir, args.workflow_id, args.run_root, args.verbose)))
