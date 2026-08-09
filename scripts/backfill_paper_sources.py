#!/usr/bin/env python3
"""Retroactively fix PRISMA source attribution for CSV-imported papers.

Older runs stored supplementary/masterlist CSV imports as a single "CSV Import"
bucket. Re-parse the original CSV exports with current source inference, then:

  1. Update papers.source_database / journal / source_category for matched rows.
  2. Replace stale search_results rows (CSV Import / generic other_source imports).
  3. Insert grouped search_results rows matching save_search_result semantics.

Usage:
    uv run python scripts/backfill_paper_sources.py --dry-run
    uv run python scripts/backfill_paper_sources.py --workflow-id wf-0025
    uv run python scripts/backfill_paper_sources.py --run-root runs

Do not run against production without a backup. This script mutates runtime.db files.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import aiosqlite
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.models.papers import SearchResult
from src.search.csv_import import parse_masterlist_csv, parse_supplementary_csvs

_DOI_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


@dataclass(frozen=True)
class SourceAttribution:
    source_database: str
    journal: str | None
    source_category: str


@dataclass
class WorkflowSummary:
    workflow_id: str
    db_path: str
    run_dir: str
    skipped_reason: str | None = None
    papers_matched: int = 0
    papers_updated: int = 0
    search_results_deleted: int = 0
    search_results_inserted: int = 0
    prisma_regenerated: bool = False
    new_search_groups: dict[str, int] | None = None


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    cleaned = doi.strip()
    cleaned = _DOI_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.strip().lower()
    return cleaned or None


def _attribution_key(title: str, doi: str | None) -> tuple[str, str | None]:
    return (_normalize_title(title), _normalize_doi(doi))


def _resolve_registry_path(run_root: str) -> pathlib.Path:
    path = pathlib.Path(run_root).resolve() / "workflows_registry.db"
    if not path.is_file():
        raise FileNotFoundError(f"Registry not found: {path}")
    return path


async def _list_registry_workflows(
    run_root: str,
    *,
    workflow_id: str | None,
) -> list[dict[str, str]]:
    registry_path = _resolve_registry_path(run_root)
    async with aiosqlite.connect(str(registry_path)) as db:
        db.row_factory = aiosqlite.Row
        if workflow_id:
            sql = """
                SELECT workflow_id, db_path, topic, status
                FROM workflows_registry
                WHERE workflow_id = ?
                ORDER BY updated_at DESC
            """
            params: tuple[Any, ...] = (workflow_id,)
        else:
            sql = """
                SELECT workflow_id, db_path, topic, status
                FROM workflows_registry
                ORDER BY updated_at DESC
            """
            params = ()
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [
        {
            "workflow_id": str(row["workflow_id"]),
            "db_path": str(row["db_path"]),
            "topic": str(row["topic"]),
            "status": str(row["status"]),
        }
        for row in rows
    ]


def _resolve_config_path(run_dir: pathlib.Path) -> pathlib.Path | None:
    for name in ("config_snapshot.yaml", "review.yaml"):
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    return None


def _resolve_csv_path(raw_path: str, run_dir: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw_path).expanduser()
    if path.is_file():
        return path.resolve()
    candidate = (run_dir / path).resolve()
    if candidate.is_file():
        return candidate
    return path.resolve()


def _load_csv_paths(run_dir: pathlib.Path) -> tuple[str | None, list[str]]:
    config_path = _resolve_config_path(run_dir)
    if config_path is None:
        return None, []

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    masterlist = data.get("masterlist_csv_path")
    supplementary = data.get("supplementary_csv_paths") or []
    if supplementary and not isinstance(supplementary, list):
        raise ValueError(f"supplementary_csv_paths must be a list in {config_path}")

    masterlist_resolved = str(_resolve_csv_path(str(masterlist), run_dir)) if masterlist else None
    supplementary_resolved = [str(_resolve_csv_path(str(p), run_dir)) for p in supplementary]
    return masterlist_resolved, supplementary_resolved


def _parse_csv_search_results(
    workflow_id: str,
    *,
    masterlist_csv_path: str | None,
    supplementary_csv_paths: list[str],
) -> list[SearchResult]:
    results: list[SearchResult] = []
    if masterlist_csv_path:
        results.extend(parse_masterlist_csv(masterlist_csv_path, workflow_id))
    if supplementary_csv_paths:
        results.extend(parse_supplementary_csvs(supplementary_csv_paths, workflow_id))
    return results


def _build_attribution_map(search_results: Sequence[SearchResult]) -> dict[tuple[str, str | None], SourceAttribution]:
    mapping: dict[tuple[str, str | None], SourceAttribution] = {}
    for result in search_results:
        for paper in result.papers:
            key = _attribution_key(paper.title, paper.doi)
            mapping[key] = SourceAttribution(
                source_database=paper.source_database,
                journal=paper.journal,
                source_category=paper.source_category.value,
            )
    return mapping


async def _workflow_paper_ids(db: aiosqlite.Connection, workflow_id: str) -> set[str]:
    """Paper ids scoped to a workflow via screening/cohort tables."""
    sql = """
        SELECT DISTINCT paper_id FROM (
            SELECT paper_id FROM screening_decisions WHERE workflow_id = ?
            UNION
            SELECT paper_id FROM dual_screening_results WHERE workflow_id = ?
            UNION
            SELECT paper_id FROM study_cohort_membership WHERE workflow_id = ?
        )
    """
    async with db.execute(sql, (workflow_id, workflow_id, workflow_id)) as cur:
        rows = await cur.fetchall()
    return {str(row[0]) for row in rows}


async def _count_stale_search_results(db: aiosqlite.Connection, workflow_id: str) -> int:
    async with db.execute(
        """
        SELECT COUNT(*) FROM search_results
        WHERE workflow_id = ?
          AND (
            database_name = 'CSV Import'
            OR (source_category = 'other_source' AND search_query LIKE 'Imported from%')
          )
        """,
        (workflow_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0] if row else 0)


async def _delete_stale_search_results(db: aiosqlite.Connection, workflow_id: str) -> int:
    cursor = await db.execute(
        """
        DELETE FROM search_results
        WHERE workflow_id = ?
          AND (
            database_name = 'CSV Import'
            OR (source_category = 'other_source' AND search_query LIKE 'Imported from%')
          )
        """,
        (workflow_id,),
    )
    return int(cursor.rowcount)


async def _search_results_columns(db: aiosqlite.Connection) -> set[str]:
    async with db.execute("PRAGMA table_info(search_results)") as cur:
        rows = await cur.fetchall()
    return {str(row[1]) for row in rows}


async def _insert_search_result_row(db: aiosqlite.Connection, result: SearchResult) -> None:
    """Insert or merge search_results row (add CSV counts to existing connector totals)."""
    columns = await _search_results_columns(db)
    async with db.execute(
        """
        SELECT records_retrieved FROM search_results
        WHERE workflow_id = ?
          AND database_name = ?
          AND source_category = ?
        """,
        (
            result.workflow_id,
            result.database_name,
            result.source_category.value,
        ),
    ) as cur:
        row = await cur.fetchone()

    if row:
        merged = int(row[0]) + int(result.records_retrieved)
        await db.execute(
            """
            UPDATE search_results
            SET records_retrieved = ?,
                search_date = ?,
                search_query = ?
            WHERE workflow_id = ?
              AND database_name = ?
              AND source_category = ?
            """,
            (
                merged,
                result.search_date,
                result.search_query,
                result.workflow_id,
                result.database_name,
                result.source_category.value,
            ),
        )
        return

    if "diagnostic_cause" in columns:
        await db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query,
                limits_applied, records_retrieved, diagnostic_cause, query_variant, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.database_name,
                result.source_category.value,
                result.search_date,
                result.search_query,
                result.limits_applied,
                result.records_retrieved,
                result.diagnostic_cause,
                result.query_variant or "primary",
                result.workflow_id,
            ),
        )
    else:
        await db.execute(
            """
            INSERT INTO search_results (
                database_name, source_category, search_date, search_query,
                limits_applied, records_retrieved, workflow_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.database_name,
                result.source_category.value,
                result.search_date,
                result.search_query,
                result.limits_applied,
                result.records_retrieved,
                result.workflow_id,
            ),
        )


async def _papers_has_journal_column(db: aiosqlite.Connection) -> bool:
    async with db.execute("PRAGMA table_info(papers)") as cur:
        rows = await cur.fetchall()
    return any(str(row[1]) == "journal" for row in rows)


async def _update_papers_for_workflow(
    db: aiosqlite.Connection,
    workflow_id: str,
    attribution_map: dict[tuple[str, str | None], SourceAttribution],
    *,
    dry_run: bool,
) -> tuple[int, int]:
    has_journal = await _papers_has_journal_column(db)
    journal_col = ", journal" if has_journal else ""
    query = f"""
        SELECT paper_id, title, doi, source_database{journal_col}, source_category
        FROM papers
    """
    async with db.execute(query) as cur:
        rows = await cur.fetchall()

    matched = 0
    updated = 0
    for row in rows:
        if has_journal:
            paper_id, title, doi, source_database, journal, source_category = row
        else:
            paper_id, title, doi, source_database, source_category = row
            journal = None
        attr = attribution_map.get(_attribution_key(str(title), str(doi) if doi else None))
        if attr is None:
            continue
        matched += 1
        journal_unchanged = (not has_journal) or ((journal or None) == attr.journal)
        if (
            str(source_database) == attr.source_database
            and journal_unchanged
            and str(source_category) == attr.source_category
        ):
            continue
        updated += 1
        if not dry_run:
            if has_journal:
                await db.execute(
                    """
                    UPDATE papers
                    SET source_database = ?, journal = ?, source_category = ?
                    WHERE paper_id = ?
                    """,
                    (attr.source_database, attr.journal, attr.source_category, str(paper_id)),
                )
            else:
                await db.execute(
                    """
                    UPDATE papers
                    SET source_database = ?, source_category = ?
                    WHERE paper_id = ?
                    """,
                    (attr.source_database, attr.source_category, str(paper_id)),
                )
    return matched, updated


async def _regenerate_prisma_diagram(
    *,
    run_dir: pathlib.Path,
    workflow_id: str,
    db_path: pathlib.Path,
) -> bool:
    """Rebuild fig_prisma_flow.png from updated search_results."""
    try:
        from src.db.database import get_db
        from src.db.repositories import WorkflowRepository
        from src.prisma import build_prisma_counts, render_prisma_diagram
    except ImportError:
        return False

    try:
        async with get_db(str(db_path)) as db:
            repo = WorkflowRepository(db)
            dedup = (await repo.get_dedup_count(workflow_id)) or 0
            included_ids, _ = await repo.resolve_canonical_included_paper_ids(workflow_id)
            counts = await build_prisma_counts(
                repo,
                workflow_id,
                dedup,
                included_quantitative=len(included_ids),
            )
            targets = [
                run_dir / "fig_prisma_flow.png",
                run_dir / "submission" / "figures" / "fig_prisma_flow.png",
            ]
            for target in targets:
                if target.parent.exists() or target == targets[0]:
                    render_prisma_diagram(counts, str(target))
        return True
    except Exception:
        return False


async def _backfill_workflow(
    entry: dict[str, str],
    *,
    dry_run: bool,
) -> WorkflowSummary:
    workflow_id = entry["workflow_id"]
    db_path = pathlib.Path(entry["db_path"]).resolve()
    run_dir = db_path.parent
    summary = WorkflowSummary(
        workflow_id=workflow_id,
        db_path=str(db_path),
        run_dir=str(run_dir),
    )

    if not db_path.is_file():
        summary.skipped_reason = f"runtime.db missing: {db_path}"
        return summary

    try:
        masterlist_path, supplementary_paths = _load_csv_paths(run_dir)
    except Exception as exc:
        summary.skipped_reason = f"config load failed: {exc}"
        return summary

    if not masterlist_path and not supplementary_paths:
        summary.skipped_reason = "no masterlist_csv_path or supplementary_csv_paths in run config"
        return summary

    missing = [
        p
        for p in ([masterlist_path] if masterlist_path else []) + supplementary_paths
        if not pathlib.Path(p).is_file()
    ]
    if missing:
        summary.skipped_reason = f"CSV file(s) not found: {', '.join(missing)}"
        return summary

    try:
        csv_results = _parse_csv_search_results(
            workflow_id,
            masterlist_csv_path=masterlist_path,
            supplementary_csv_paths=supplementary_paths,
        )
    except Exception as exc:
        summary.skipped_reason = f"CSV parse failed: {exc}"
        return summary

    if not csv_results:
        summary.skipped_reason = "CSV parse produced no search results"
        return summary

    attribution_map = _build_attribution_map(csv_results)
    summary.new_search_groups = {
        f"{r.database_name} ({r.source_category.value})": r.records_retrieved for r in csv_results
    }

    async with aiosqlite.connect(str(db_path)) as db:
        summary.search_results_deleted = await _count_stale_search_results(db, workflow_id)
        summary.papers_matched, summary.papers_updated = await _update_papers_for_workflow(
            db,
            workflow_id,
            attribution_map,
            dry_run=dry_run,
        )
        summary.search_results_inserted = len(csv_results)

        if dry_run:
            return summary

        await _delete_stale_search_results(db, workflow_id)
        for result in csv_results:
            await _insert_search_result_row(db, result)
        await db.commit()

    summary.prisma_regenerated = await _regenerate_prisma_diagram(
        run_dir=run_dir,
        workflow_id=workflow_id,
        db_path=db_path,
    )

    return summary


def _print_summary(summary: WorkflowSummary, *, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n[{mode}] {summary.workflow_id}")
    print(f"  db_path: {summary.db_path}")
    print(f"  run_dir: {summary.run_dir}")
    if summary.skipped_reason:
        print(f"  skipped: {summary.skipped_reason}")
        return
    print(f"  papers matched (title/doi): {summary.papers_matched}")
    print(f"  papers updated: {summary.papers_updated}")
    print(f"  search_results deleted (stale CSV rows): {summary.search_results_deleted}")
    print(f"  search_results inserted: {summary.search_results_inserted}")
    if summary.new_search_groups:
        print("  new search_result groups:")
        for label, count in sorted(summary.new_search_groups.items()):
            print(f"    - {label}: {count}")
    if not summary.skipped_reason and not dry_run:
        print(f"  prisma diagram regenerated: {summary.prisma_regenerated}")


async def _run(args: argparse.Namespace) -> int:
    try:
        entries = await _list_registry_workflows(args.run_root, workflow_id=args.workflow_id)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not entries:
        if args.workflow_id:
            print(f"ERROR: workflow_id '{args.workflow_id}' not found in registry.")
        else:
            print("No workflows found in registry.")
        return 1

    totals = {
        "workflows": 0,
        "skipped": 0,
        "papers_updated": 0,
        "search_results_deleted": 0,
        "search_results_inserted": 0,
    }

    for entry in entries:
        try:
            summary = await _backfill_workflow(entry, dry_run=args.dry_run)
        except Exception as exc:
            summary = WorkflowSummary(
                workflow_id=entry["workflow_id"],
                db_path=entry["db_path"],
                run_dir=str(pathlib.Path(entry["db_path"]).parent),
                skipped_reason=f"error: {exc}",
            )
        _print_summary(summary, dry_run=args.dry_run)
        totals["workflows"] += 1
        if summary.skipped_reason:
            totals["skipped"] += 1
            continue
        totals["papers_updated"] += summary.papers_updated
        totals["search_results_deleted"] += summary.search_results_deleted
        totals["search_results_inserted"] += summary.search_results_inserted

    print("\n=== Totals ===")
    print(f"  workflows processed: {totals['workflows']}")
    print(f"  skipped: {totals['skipped']}")
    print(f"  papers updated: {totals['papers_updated']}")
    print(f"  search_results deleted: {totals['search_results_deleted']}")
    print(f"  search_results inserted: {totals['search_results_inserted']}")
    if args.dry_run:
        print("  (dry run: no database changes written)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill PRISMA source attribution for CSV-imported papers.",
    )
    parser.add_argument(
        "--run-root",
        default="runs",
        help="Runs root containing workflows_registry.db (default: runs).",
    )
    parser.add_argument(
        "--workflow-id",
        help="Process a single workflow (e.g. wf-0025). Default: all registry workflows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned changes without writing to runtime.db.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
