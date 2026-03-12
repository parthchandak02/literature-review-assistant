"""Backfill extraction_records.primary_study_status for historical runtime DBs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.extraction.primary_status import resolve_primary_status
from src.models import ExclusionReason, PrimaryStudyStatus, StudyDesign


@dataclass
class BackfillStats:
    db_path: str
    scanned: int = 0
    updated: int = 0
    already_set: int = 0
    unknown: int = 0
    errors: int = 0


def _list_runtime_dbs(runs_root: Path) -> list[Path]:
    if not runs_root.exists():
        return []
    return sorted([p for p in runs_root.rglob("runtime.db") if p.is_file()])


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _ensure_primary_status_column(con: sqlite3.Connection) -> None:
    cols = _table_columns(con, "extraction_records")
    if "primary_study_status" not in cols:
        con.execute(
            "ALTER TABLE extraction_records ADD COLUMN primary_study_status TEXT NOT NULL DEFAULT 'unknown'"
        )


def _load_screening_reason_map(con: sqlite3.Connection, workflow_id: str) -> dict[str, ExclusionReason]:
    out: dict[str, ExclusionReason] = {}
    rows = con.execute(
        """
        SELECT paper_id, exclusion_reason
        FROM screening_decisions
        WHERE workflow_id = ? AND exclusion_reason IS NOT NULL AND exclusion_reason != ''
        """,
        (workflow_id,),
    ).fetchall()
    for paper_id, reason_raw in rows:
        try:
            reason = ExclusionReason(str(reason_raw))
        except ValueError:
            continue
        pid = str(paper_id)
        # Prefer stronger signals when multiple reasons exist.
        if pid in out and out[pid] == ExclusionReason.PROTOCOL_ONLY:
            continue
        if reason == ExclusionReason.PROTOCOL_ONLY:
            out[pid] = reason
        elif pid not in out:
            out[pid] = reason
    return out


def _compute_status(
    study_design_raw: str,
    exclusion_reason: ExclusionReason | None,
) -> PrimaryStudyStatus:
    study_design: StudyDesign | None = None
    try:
        study_design = StudyDesign(study_design_raw)
    except ValueError:
        study_design = None
    return resolve_primary_status(study_design=study_design, exclusion_reason=exclusion_reason)


def backfill_db(db_path: Path, *, dry_run: bool, overwrite: bool) -> BackfillStats:
    stats = BackfillStats(db_path=str(db_path))
    con = sqlite3.connect(str(db_path))
    try:
        con.row_factory = sqlite3.Row
        _ensure_primary_status_column(con)
        workflow_rows = con.execute("SELECT workflow_id FROM workflows").fetchall()
        workflow_ids = [str(r[0]) for r in workflow_rows]
        for workflow_id in workflow_ids:
            reason_map = _load_screening_reason_map(con, workflow_id)
            rows = con.execute(
                """
                SELECT workflow_id, paper_id, study_design, primary_study_status, data
                FROM extraction_records
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchall()
            for row in rows:
                stats.scanned += 1
                paper_id = str(row["paper_id"])
                study_design_raw = str(row["study_design"])
                current_status = str(row["primary_study_status"] or "unknown")
                data_raw = row["data"] if row["data"] is not None else "{}"

                if not overwrite and current_status != PrimaryStudyStatus.UNKNOWN.value:
                    stats.already_set += 1
                    continue

                exclusion_reason = reason_map.get(paper_id)
                resolved = _compute_status(study_design_raw, exclusion_reason)
                if resolved == PrimaryStudyStatus.UNKNOWN:
                    stats.unknown += 1

                try:
                    payload = json.loads(str(data_raw))
                    if not isinstance(payload, dict):
                        payload = {}
                except Exception:
                    payload = {}
                payload["primary_study_status"] = resolved.value

                if not dry_run:
                    con.execute(
                        """
                        UPDATE extraction_records
                        SET primary_study_status = ?, data = ?
                        WHERE workflow_id = ? AND paper_id = ?
                        """,
                        (resolved.value, json.dumps(payload), workflow_id, paper_id),
                    )
                stats.updated += 1
        if not dry_run:
            con.commit()
    except Exception:
        stats.errors += 1
        con.rollback()
    finally:
        con.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill extraction_records.primary_study_status in historical run databases."
    )
    parser.add_argument(
        "--runs-root",
        default="runs",
        help="Root directory that contains historical run folders (default: runs).",
    )
    parser.add_argument(
        "--db-path",
        action="append",
        default=[],
        help="Specific runtime.db path(s). Can be passed multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report changes without writing updates.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute rows even when primary_study_status is already set.",
    )
    args = parser.parse_args()

    console = Console()
    explicit_dbs = [Path(p).expanduser().resolve() for p in args.db_path]
    discovered = _list_runtime_dbs(Path(args.runs_root).expanduser().resolve())
    all_dbs = explicit_dbs if explicit_dbs else discovered
    if not all_dbs:
        console.print("No runtime.db files found.")
        return 0

    results: list[BackfillStats] = []
    for db in all_dbs:
        results.append(backfill_db(db, dry_run=args.dry_run, overwrite=args.overwrite))

    table = Table(title="Primary Study Status Backfill")
    table.add_column("DB")
    table.add_column("Scanned", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Already Set", justify="right")
    table.add_column("Unknown", justify="right")
    table.add_column("Errors", justify="right")
    for r in results:
        table.add_row(
            r.db_path,
            str(r.scanned),
            str(r.updated),
            str(r.already_set),
            str(r.unknown),
            str(r.errors),
        )
    console.print(table)

    total_errors = sum(r.errors for r in results)
    if total_errors:
        console.print(f"Completed with errors in {total_errors} database(s).")
        return 1
    console.print("Backfill completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

