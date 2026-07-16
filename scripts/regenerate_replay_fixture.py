#!/usr/bin/env python3
"""Rebuild tests/fixtures/replay from an existing completed workflow run.

Typical usage (from repo root):

  # Resolve runtime.db via workflows registry under ./runs
  uv run python scripts/regenerate_replay_fixture.py --workflow-id wf-0088

  # Point at a specific run directory or runtime.db
  uv run python scripts/regenerate_replay_fixture.py \\
    --workflow-id wf-0088 \\
    --source-run-dir runs/2026-05-15/wf-0088-.../run_01-59-24AM

  # Rebuild adversarial profile (failed early / zero-checkpoint fixture)
  uv run python scripts/regenerate_replay_fixture.py --profile adversarial

  # After copying, verify schema + manifest alignment
  uv run python scripts/check_replay_fixture_schema.py

The script copies runtime.db (and doc_manuscript.md when present), applies migrations
via get_db(), then writes manifest.json with workflow_id and schema_version.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from src.db.database import get_db
from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "replay"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
DATABASE_PY = REPO_ROOT / "src" / "db" / "database.py"

ADVERSARIAL_DEFAULTS = {
    "workflow_id": "wf-0044",
    "source_run_dir": (
        "runs/2026-03-30/wf-0044-what-is-the-effect-of-intervention-on-outcome-in-population/run_10-16-23AM"
    ),
    "runtime_db_name": "runtime_adversarial.db",
}


def _expected_schema_version() -> int:
    text = DATABASE_PY.read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"await _apply\(\s*(\d+)", text)]
    if not versions:
        raise RuntimeError(f"No migration versions found in {DATABASE_PY}")
    return max(versions)


def _db_schema_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def _load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.is_file():
        loaded = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    return {}


async def _resolve_source_db(workflow_id: str, run_root: str, source_run_dir: str, db_path: str) -> Path:
    if source_run_dir.strip():
        run_dir = Path(source_run_dir).expanduser()
        if not run_dir.is_absolute():
            run_dir = (REPO_ROOT / run_dir).resolve()
        else:
            run_dir = run_dir.resolve()
        candidate = run_dir / "runtime.db" if run_dir.is_dir() else run_dir
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"No runtime.db at {candidate}")

    if db_path.strip():
        resolved = Path(db_path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"runtime.db not found: {resolved}")
        return resolved

    roots = candidate_run_roots(run_root, anchor_file=__file__)
    resolved_path = await resolve_workflow_db_path(workflow_id, roots)
    if not resolved_path:
        raise RuntimeError(f"Could not resolve runtime.db for {workflow_id} under {roots}")
    return Path(resolved_path).expanduser().resolve()


async def _migrate_fixture_db(dest_db: Path) -> None:
    async with get_db(str(dest_db)) as _db:
        pass


def _profile_files(runtime_db_name: str, doc_manuscript_name: str | None) -> dict[str, str]:
    files: dict[str, str] = {"runtime_db": runtime_db_name}
    if doc_manuscript_name:
        files["doc_manuscript_md"] = doc_manuscript_name
    return files


def _write_manifest(
    *,
    profile: str,
    workflow_id: str,
    schema_version: int,
    source_run: str,
    runtime_db_name: str,
    doc_manuscript_name: str | None,
    description: str | None = None,
) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    profiles = manifest.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}

    profile_entry: dict[str, Any] = {
        "workflow_id": workflow_id,
        "source_run": source_run,
        "files": _profile_files(runtime_db_name, doc_manuscript_name),
    }
    if description:
        profile_entry["description"] = description
    profiles[profile] = profile_entry
    manifest["profiles"] = profiles

    if profile == "default":
        manifest.update(
            {
                "workflow_id": workflow_id,
                "schema_version": schema_version,
                "replay_profile": "local",
                "source_run": source_run,
                "generated_at": datetime.now(UTC).isoformat(),
                "files": _profile_files(runtime_db_name, doc_manuscript_name),
            }
        )
    else:
        manifest.setdefault("workflow_id", manifest.get("workflow_id", workflow_id))
        manifest["schema_version"] = schema_version
        manifest.setdefault("replay_profile", "local")
        manifest["generated_at"] = datetime.now(UTC).isoformat()

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        choices=["default", "adversarial"],
        default="default",
        help="Fixture profile to regenerate (default: completed happy-path replay)",
    )
    parser.add_argument("--workflow-id", default="", help="Workflow id stored in the source runtime.db")
    parser.add_argument("--run-root", default="runs", help="Runs root for registry resolution")
    parser.add_argument(
        "--source-run-dir",
        default="",
        help="Run directory containing runtime.db, or a direct path to runtime.db",
    )
    parser.add_argument("--db-path", default="", help="Optional direct runtime.db path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=FIXTURE_DIR,
        help="Fixture output directory (default: tests/fixtures/replay)",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    output_dir: Path = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    profile = args.profile
    workflow_id = args.workflow_id.strip()
    source_run_dir = args.source_run_dir.strip()
    db_path = args.db_path.strip()
    description: str | None = None

    if profile == "adversarial":
        workflow_id = workflow_id or ADVERSARIAL_DEFAULTS["workflow_id"]
        source_run_dir = source_run_dir or ADVERSARIAL_DEFAULTS["source_run_dir"]
        runtime_db_name = ADVERSARIAL_DEFAULTS["runtime_db_name"]
        description = "Failed early run with papers present, zero checkpoints, zero included studies"
    else:
        if not workflow_id:
            raise SystemExit("--workflow-id is required for --profile default")
        runtime_db_name = "runtime.db"

    source_db = await _resolve_source_db(workflow_id, args.run_root, source_run_dir, db_path)
    run_dir = source_db.parent
    source_run_label = str(run_dir.relative_to(REPO_ROOT)) if run_dir.is_relative_to(REPO_ROOT) else str(run_dir)

    dest_db = output_dir / runtime_db_name
    shutil.copy2(source_db, dest_db)
    for sidecar in (dest_db.with_suffix(dest_db.suffix + "-shm"), dest_db.with_suffix(dest_db.suffix + "-wal")):
        sidecar.unlink(missing_ok=True)

    await _migrate_fixture_db(dest_db)

    dest_md: Path | None = None
    src_md = run_dir / "doc_manuscript.md"
    if profile == "default" and src_md.is_file():
        dest_md = output_dir / "doc_manuscript.md"
        shutil.copy2(src_md, dest_md)

    db_version = _db_schema_version(dest_db)
    expected = _expected_schema_version()
    if db_version != expected:
        console.print(
            f"[yellow]warning[/yellow]: {dest_db.name} schema_version={db_version}, code expects {expected}; "
            "fixture migration did not reach current schema"
        )

    _write_manifest(
        profile=profile,
        workflow_id=workflow_id,
        schema_version=expected,
        source_run=source_run_label,
        runtime_db_name=dest_db.name,
        doc_manuscript_name=dest_md.name if dest_md else None,
        description=description,
    )

    console.print(f"Wrote replay fixture profile={profile} to {output_dir}")
    console.print(f"  workflow_id={workflow_id}")
    console.print(f"  runtime_db={dest_db}")
    if dest_md:
        console.print(f"  doc_manuscript_md={dest_md}")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
