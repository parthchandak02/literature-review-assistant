#!/usr/bin/env python3
"""Diagnostic table viewer for a completed or in-progress review run.

Reads from runtime.db and prints Rich tables showing:
  - Run metadata (workflow_id, topic, status, cost)
  - Search counts per database
  - Screening funnel (found -> deduped -> pre-filtered -> LLM-screened -> included)
  - Included papers with metadata and retrieval source
  - Top exclusion reasons breakdown

With --fetch-pdfs: also attempts live full-text retrieval for each included
paper and shows which tier succeeded (Unpaywall, PMC, Semantic Scholar, etc.).

Usage:
    uv run python scripts/show_run_info.py --workflow-id wf-d042e90e
    uv run python scripts/show_run_info.py --run-dir runs/2026-03-05/.../run_03-46-58AM
    uv run python scripts/show_run_info.py --workflow-id wf-d042e90e --fetch-pdfs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sqlite3
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# DB path resolution
# ---------------------------------------------------------------------------


async def _resolve_db_path(
    run_dir: str | None,
    workflow_id: str | None,
    run_root: str,
) -> pathlib.Path | None:
    if run_dir:
        p = pathlib.Path(run_dir).resolve()
        db = p / "runtime.db"
        return db if db.exists() else None
    if workflow_id:
        try:
            from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback

            entry = await find_by_workflow_id(run_root, workflow_id)
            if entry is None:
                entry = await find_by_workflow_id_fallback(run_root, workflow_id)
            if entry and entry.db_path:
                return pathlib.Path(entry.db_path)
        except Exception as exc:
            console.print(f"[yellow]Warning: registry lookup failed ({exc}); scanning run dirs...[/]")
            # Manual fallback: scan for runtime.db containing the workflow_id
            root = pathlib.Path(run_root)
            if root.exists():
                for db_path in sorted(root.rglob("runtime.db"), reverse=True):
                    try:
                        conn = sqlite3.connect(str(db_path))
                        row = conn.execute(
                            "SELECT workflow_id FROM workflows WHERE workflow_id=? LIMIT 1",
                            (workflow_id,),
                        ).fetchone()
                        conn.close()
                        if row:
                            return db_path
                    except Exception:
                        continue
    return None


# ---------------------------------------------------------------------------
# Rich table helpers
# ---------------------------------------------------------------------------


def _trunc(text: str | None, n: int = 70) -> str:
    if not text:
        return "[dim]--[/]"
    text = text.strip()
    return text[:n] + "..." if len(text) > n else text


def _fmt_authors(raw: str | None, max_len: int = 28) -> str:
    """Return a compact author string truncated to max_len characters."""
    if not raw:
        return "[dim]--[/]"
    try:
        parts = json.loads(raw)
        # First author last-name only, + et al. if more than one
        if isinstance(parts[0], dict):
            first = parts[0].get("name") or parts[0].get("raw_name") or str(parts[0])
        else:
            first = str(parts[0])
        # Extract last name (last word of first author)
        first_last = first.split()[-1] if first.split() else first
        suffix = " et al." if len(parts) > 1 else ""
        result = first_last + suffix
    except Exception:
        result = raw
    return result[:max_len] + "..." if len(result) > max_len else result


# ---------------------------------------------------------------------------
# Main diagnostic function
# ---------------------------------------------------------------------------


async def show_run(db_path: pathlib.Path, fetch_pdfs: bool = False, run_root: str = "runs") -> None:
    run_dir = db_path.parent
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # --- Run metadata ---
    wf = conn.execute("SELECT * FROM workflows LIMIT 1").fetchone()
    if not wf:
        console.print("[red]No workflow found in this database.[/]")
        return

    workflow_id = wf["workflow_id"]
    topic = wf["topic"]
    status = wf["status"]
    created_at = wf["created_at"]

    # Cost
    cost_row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM cost_records").fetchone()
    total_cost = float(cost_row[0]) if cost_row else 0.0

    console.print(
        Panel.fit(
            f"[bold white]{topic}[/]\n"
            f"[dim]workflow_id:[/] [cyan]{workflow_id}[/]  "
            f"[dim]status:[/] [{'green' if status == 'completed' else 'yellow'}]{status}[/]  "
            f"[dim]created:[/] {created_at}  "
            f"[dim]cost:[/] [yellow]${total_cost:.3f}[/]\n"
            f"[dim]run_dir:[/] {run_dir}",
            title="[bold violet]LitReview Run Info[/]",
            border_style="violet",
        )
    )

    # --- Search counts table ---
    papers_by_source = conn.execute(
        "SELECT source_database, COUNT(*) as cnt FROM papers GROUP BY source_database ORDER BY cnt DESC"
    ).fetchall()

    search_table = Table(title="Search Counts by Database", box=box.SIMPLE_HEAVY, show_footer=True)
    search_table.add_column("Database", style="cyan")
    search_table.add_column(
        "Records", justify="right", style="white", footer=str(sum(r["cnt"] for r in papers_by_source))
    )
    for row in papers_by_source:
        search_table.add_row(row["source_database"] or "unknown", str(row["cnt"]))
    console.print(search_table)

    # --- Screening funnel ---
    total_found = sum(r["cnt"] for r in papers_by_source)
    dedup_row = conn.execute("SELECT dedup_count FROM workflows LIMIT 1").fetchone()
    dedup_count = int(dedup_row["dedup_count"] or 0) if dedup_row else 0
    after_dedup = total_found - dedup_count

    # Pre-screen exclusions (keyword/bm25/insufficient_content heuristic)
    pre_filter_count = conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM screening_decisions "
        "WHERE reviewer_type IN ('keyword_filter', 'KEYWORD_FILTER') "
        "AND stage='title_abstract' AND decision='exclude'"
    ).fetchone()[0]

    ta_llm_screened = conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM screening_decisions "
        "WHERE reviewer_type NOT IN ('keyword_filter', 'KEYWORD_FILTER') "
        "AND stage='title_abstract'"
    ).fetchone()[0]

    ta_included = conn.execute(
        "SELECT COUNT(*) FROM dual_screening_results WHERE stage='title_abstract' AND final_decision='include'"
    ).fetchone()[0]

    ft_assessed = conn.execute("SELECT COUNT(*) FROM dual_screening_results WHERE stage='fulltext'").fetchone()[0]

    ft_included = conn.execute(
        "SELECT COUNT(*) FROM dual_screening_results WHERE stage='fulltext' AND final_decision='include'"
    ).fetchone()[0]

    funnel_table = Table(title="Screening Funnel", box=box.SIMPLE_HEAVY)
    funnel_table.add_column("Stage", style="cyan")
    funnel_table.add_column("N", justify="right", style="white")
    funnel_table.add_column("Notes", style="dim")
    funnel_table.add_row("Records identified", str(total_found), "from all databases")
    funnel_table.add_row("After deduplication", str(after_dedup), f"-{dedup_count} duplicates removed")
    funnel_table.add_row("  Pre-screen excluded", str(pre_filter_count), "BM25/heuristic auto-exclusion")
    funnel_table.add_row("  LLM screened (title/abstract)", str(ta_llm_screened), "dual-reviewer")
    funnel_table.add_row("  Passed title/abstract", str(ta_included), "")
    funnel_table.add_row("Full-text assessed", str(ft_assessed), "")
    funnel_table.add_row("[bold green]INCLUDED[/]", f"[bold green]{ft_included}[/]", "final study pool")
    console.print(funnel_table)

    # --- Included papers table ---
    included_rows = conn.execute("""
        SELECT p.paper_id, p.title, p.authors, p.year, p.source_database, p.doi, p.url,
               er.extraction_source
        FROM papers p
        JOIN dual_screening_results ft ON p.paper_id=ft.paper_id AND ft.stage='fulltext'
        LEFT JOIN extraction_records er ON p.paper_id=er.paper_id
        WHERE ft.final_decision='include'
        ORDER BY p.year DESC
    """).fetchall()

    inc_table = Table(
        title=f"Included Studies ({len(included_rows)} papers)",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
    )
    inc_table.add_column("#", style="dim", width=3, no_wrap=True)
    inc_table.add_column("Title", max_width=52, no_wrap=True)
    inc_table.add_column("First Author", width=16, no_wrap=True)
    inc_table.add_column("Year", justify="right", width=6, no_wrap=True)
    inc_table.add_column("DB", width=10, no_wrap=True)
    inc_table.add_column("Full Text?", width=15, no_wrap=True)
    inc_table.add_column("DOI", max_width=28, no_wrap=True)

    for idx, row in enumerate(included_rows, 1):
        ext_src = row["extraction_source"] or "abstract"
        is_fulltext = ext_src not in ("abstract", "text", "")
        ft_label = f"[green]{ext_src}[/]" if is_fulltext else "[dim]abstract only[/]"
        doi = (row["doi"] or "").strip()
        doi_display = doi[:28] if doi else "[dim]--[/]"
        inc_table.add_row(
            str(idx),
            _trunc(row["title"], 52),
            _fmt_authors(row["authors"]),
            str(row["year"]) if row["year"] else "[dim]--[/]",
            (row["source_database"] or "").split("_")[0][:10],
            ft_label,
            doi_display,
        )
    console.print(inc_table)

    # --- Exclusion reasons breakdown ---
    excl_rows = conn.execute("""
        SELECT
            CASE
                WHEN reason LIKE '%Insufficient content%' THEN 'Insufficient content (abstract absent/too short)'
                WHEN reason LIKE '%Protocol-only%' OR reason LIKE '%protocol%' THEN 'Protocol-only paper'
                WHEN reason LIKE '%no publication year%' THEN 'No publication year'
                WHEN reason LIKE '%BM25%' OR reason LIKE '%Low relevance%' THEN 'BM25 low relevance score'
                WHEN reason LIKE '%inpatient%' OR reason LIKE '%hospital ward%' THEN 'Inpatient/hospital setting only'
                WHEN reason LIKE '%surgical%' OR reason LIKE '%surgery%' THEN 'Surgical/procedural study'
                WHEN reason LIKE '%conference abstract%' THEN 'Conference abstract only'
                WHEN reason LIKE '%wrong population%' THEN 'Wrong population'
                WHEN reason LIKE '%wrong intervention%' THEN 'Wrong intervention'
                WHEN reason LIKE '%wrong outcome%' THEN 'Wrong outcome'
                WHEN reason LIKE '%wrong study design%' THEN 'Wrong study design'
                ELSE SUBSTR(reason, 1, 65)
            END as reason_label,
            COUNT(*) as cnt
        FROM screening_decisions
        WHERE decision='exclude'
        GROUP BY reason_label
        ORDER BY cnt DESC
        LIMIT 12
    """).fetchall()

    excl_table = Table(title="Top Exclusion Reasons", box=box.SIMPLE_HEAVY)
    excl_table.add_column("Reason", style="white", min_width=50)
    excl_table.add_column("Count", justify="right", style="red")
    for row in excl_rows:
        excl_table.add_row(row["reason_label"] or "[dim](no reason)[/]", str(row["cnt"]))
    console.print(excl_table)

    # --- Optional: fulltext retrieval attempt ---
    if fetch_pdfs:
        await _fetch_pdfs_for_included(included_rows, run_dir, conn)

    conn.close()


async def _fetch_pdfs_for_included(
    included_rows: list[sqlite3.Row],
    run_dir: pathlib.Path,
    conn: sqlite3.Connection,
) -> None:
    """Attempt live full-text retrieval for each included paper, show results."""
    try:
        from src.extraction.table_extraction import fetch_full_text
    except ImportError as exc:
        console.print(f"[red]Cannot import retrieval modules: {exc}[/]")
        return

    papers_dir = run_dir / "papers"
    papers_dir.mkdir(exist_ok=True)

    manifest_path = run_dir / "data_papers_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    fetch_table = Table(title="Full-Text Retrieval Attempt", box=box.SIMPLE_HEAVY, show_lines=True)
    fetch_table.add_column("#", width=3)
    fetch_table.add_column("Title", min_width=35, max_width=50)
    fetch_table.add_column("Tier", width=20)
    fetch_table.add_column("Chars", justify="right", width=8)
    fetch_table.add_column("PDF?", width=6)
    fetch_table.add_column("Saved", width=30)

    console.print("\n[bold]Attempting full-text retrieval for each included paper...[/]\n")

    for idx, row in enumerate(included_rows, 1):
        paper_id = row["paper_id"]
        title_short = _trunc(row["title"], 50)
        doi = row["doi"] or ""
        url = row["url"] or ""

        try:
            with console.status(f"[cyan]{idx}/{len(included_rows)}[/] Fetching {title_short[:40]}..."):
                ft = await fetch_full_text(doi=doi or None, url=url or None)
        except Exception as exc:
            fetch_table.add_row(
                str(idx),
                title_short,
                "[red]ERROR[/]",
                "--",
                "--",
                f"[red]{str(exc)[:40]}[/]",
            )
            continue

        if ft is None:
            fetch_table.add_row(str(idx), title_short, "[dim]None[/]", "0", "[dim]No[/]", "[dim]--[/]")
            continue

        source = ft.source or "abstract"
        source_color = "dim" if source == "abstract" else "green"
        has_pdf = "YES" if (ft.pdf_bytes and len(ft.pdf_bytes) > 1000) else "No"
        char_count = len(ft.text or "")

        saved_path: str | None = None
        if ft.pdf_bytes and len(ft.pdf_bytes) > 1000:
            dest = papers_dir / f"{paper_id}.pdf"
            dest.write_bytes(ft.pdf_bytes)
            saved_path = str(dest)
        elif ft.text and len(ft.text) >= 500:
            dest = papers_dir / f"{paper_id}.txt"
            dest.write_text(ft.text, encoding="utf-8")
            saved_path = str(dest)

        # Update manifest
        manifest[paper_id] = {
            "title": row["title"] or "",
            "authors": row["authors"] or "",
            "year": row["year"],
            "doi": doi,
            "url": url,
            "source": source,
            "file_path": saved_path,
            "file_type": ("pdf" if (saved_path and saved_path.endswith(".pdf")) else ("txt" if saved_path else None)),
        }

        saved_label = f"[green]{pathlib.Path(saved_path).name}[/]" if saved_path else "[dim]--[/]"

        fetch_table.add_row(
            str(idx),
            title_short,
            f"[{source_color}]{source}[/]",
            str(char_count) if char_count else "[dim]0[/]",
            "[green]YES[/]" if has_pdf == "YES" else "[dim]No[/]",
            saved_label,
        )

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(fetch_table)
    console.print(f"\n[green]Manifest updated:[/] {manifest_path}")
    console.print(f"[green]Papers directory:[/] {papers_dir}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a Rich diagnostic table for a LitReview run.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workflow-id", "-w", help="Workflow ID (e.g. wf-d042e90e)")
    group.add_argument("--run-dir", "-d", help="Path to run directory containing runtime.db")
    parser.add_argument("--run-root", default="runs", help="Root directory for runs (default: runs)")
    parser.add_argument(
        "--fetch-pdfs",
        action="store_true",
        help="Attempt live full-text retrieval for included papers and save to papers/ dir",
    )
    args = parser.parse_args()

    async def _run() -> None:
        db_path = await _resolve_db_path(args.run_dir, args.workflow_id, args.run_root)
        if db_path is None or not db_path.exists():
            console.print(
                f"[red]Could not find runtime.db for "
                f"{'workflow-id=' + args.workflow_id if args.workflow_id else 'run-dir=' + args.run_dir}[/]"
            )
            sys.exit(1)
        await show_run(db_path, fetch_pdfs=args.fetch_pdfs, run_root=args.run_root)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
