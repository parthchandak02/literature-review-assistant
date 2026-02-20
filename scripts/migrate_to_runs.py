"""One-time migration: merge logs/ + data/outputs/ into runs/.

Each per-run directory in logs/ is merged with its matching data/outputs/ sibling
into a single runs/<date>/<topic>/<run>/ directory containing all files.

The central registry is moved to runs/workflows_registry.db and all db_path
values are updated to point to the new location.

Run once after upgrading to the consolidated layout:
    uv run python scripts/migrate_to_runs.py

Originals in logs/ and data/outputs/ are LEFT IN PLACE so nothing is
destructive. Delete them manually after verifying the migration.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from rich.console import Console
from rich.table import Table

LOGS_ROOT = Path("logs")
OUTPUTS_ROOT = Path("data/outputs")
RUNS_ROOT = Path("runs")

console = Console()


def _merge_run(log_run_dir: Path, out_run_dir: Path | None, runs_run_dir: Path) -> list[str]:
    """Copy files from log_run_dir (and optionally out_run_dir) into runs_run_dir."""
    runs_run_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src_dir in filter(None, [log_run_dir, out_run_dir]):
        if not src_dir.is_dir():
            continue
        for src_file in src_dir.iterdir():
            if src_file.is_dir():
                continue
            dst = runs_run_dir / src_file.name
            if dst.exists():
                continue
            shutil.copy2(src_file, dst)
            copied.append(src_file.name)
    return copied


def _update_registry_paths(registry_path: Path) -> int:
    """Update db_path entries in the registry to point to runs/ instead of logs/."""
    if not registry_path.exists():
        return 0
    conn = sqlite3.connect(str(registry_path))
    try:
        cursor = conn.execute("SELECT workflow_id, db_path FROM workflows_registry")
        rows = cursor.fetchall()
        updated = 0
        for wf_id, db_path in rows:
            p = Path(db_path)
            try:
                # Attempt to make db_path relative to cwd for comparison
                rel = p.relative_to(Path.cwd())
                parts = rel.parts
            except ValueError:
                parts = p.parts
            # Replace leading "logs" component with runs
            if parts and parts[0] == "logs":
                new_parts = ("runs",) + parts[1:]
                new_path = str(Path(*new_parts).resolve())
                conn.execute(
                    "UPDATE workflows_registry SET db_path = ? WHERE workflow_id = ?",
                    (new_path, wf_id),
                )
                updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def main() -> None:
    if not LOGS_ROOT.is_dir():
        console.print("[yellow]No logs/ directory found -- nothing to migrate.[/]")
        return

    RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    # Migrate workflows_registry.db
    src_registry = LOGS_ROOT / "workflows_registry.db"
    dst_registry = RUNS_ROOT / "workflows_registry.db"
    if src_registry.exists() and not dst_registry.exists():
        shutil.copy2(src_registry, dst_registry)
        console.print("[green]Copied[/] workflows_registry.db -> runs/")

    # Update db_path values in the new registry
    updated = _update_registry_paths(dst_registry)
    if updated:
        console.print(f"[green]Updated[/] {updated} db_path entries in runs/workflows_registry.db")

    # Walk logs/ to find all run directories
    table = Table("Run", "Files copied", "Status")
    total_runs = 0
    total_files = 0

    for date_dir in sorted(LOGS_ROOT.iterdir()):
        if not date_dir.is_dir() or date_dir.name == "workflows_registry.db":
            continue
        for topic_dir in sorted(date_dir.iterdir()):
            if not topic_dir.is_dir():
                continue
            for run_dir in sorted(topic_dir.iterdir()):
                if not run_dir.is_dir():
                    continue

                # Reconstruct relative path segments
                date_name = date_dir.name
                topic_name = topic_dir.name
                run_name = run_dir.name

                log_run = LOGS_ROOT / date_name / topic_name / run_name
                out_run = OUTPUTS_ROOT / date_name / topic_name / run_name
                dst_run = RUNS_ROOT / date_name / topic_name / run_name

                try:
                    copied = _merge_run(log_run, out_run, dst_run)
                    total_runs += 1
                    total_files += len(copied)
                    rel_label = f"{date_name}/{topic_name[:30]}/{run_name}"
                    table.add_row(rel_label, str(len(copied)), "[green]OK[/]")
                except Exception as exc:
                    rel_label = f"{date_name}/{topic_name[:30]}/{run_name}"
                    table.add_row(rel_label, "0", f"[red]ERROR: {exc}[/]")

    console.print(table)
    console.print(
        f"\nMigration complete: {total_runs} run(s), {total_files} file(s) copied into runs/."
    )
    console.print(
        "[dim]Originals in logs/ and data/outputs/ were left intact. "
        "Delete them manually after verifying runs/.[/]"
    )


if __name__ == "__main__":
    main()
