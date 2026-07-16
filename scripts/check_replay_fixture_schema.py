#!/usr/bin/env python3
"""Verify the committed workflow replay fixture matches the runtime DB schema contract."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from rich.console import Console

console = Console()

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "replay"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
DATABASE_PY = REPO_ROOT / "src" / "db" / "database.py"


def _expected_schema_version() -> int:
    text = DATABASE_PY.read_text(encoding="utf-8")
    versions = [int(v) for v in re.findall(r"await _apply\(\s*(\d+)", text)]
    if not versions:
        raise RuntimeError(f"No migration versions found in {DATABASE_PY}")
    return max(versions)


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Replay fixture manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _db_schema_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def _workflow_present(db_path: Path, workflow_id: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM workflows WHERE workflow_id = ? LIMIT 1",
            (workflow_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _iter_profile_entries(manifest: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    profiles = manifest.get("profiles")
    if isinstance(profiles, dict) and profiles:
        entries: list[tuple[str, dict[str, object]]] = []
        for name, payload in profiles.items():
            if isinstance(payload, dict):
                entries.append((str(name), payload))
        if entries:
            return entries

    files = manifest.get("files")
    if not isinstance(files, dict):
        files = {}
    return [
        (
            "default",
            {
                "workflow_id": manifest.get("workflow_id"),
                "files": files,
            },
        )
    ]


def _check_profile(
    *,
    profile_name: str,
    profile: dict[str, object],
    fixture_dir: Path,
    expected: int,
) -> list[str]:
    errors: list[str] = []
    prefix = f"profiles.{profile_name}" if profile_name != "default" else "manifest"

    workflow_id = profile.get("workflow_id")
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        errors.append(f"{prefix}.workflow_id must be a non-empty string")
        workflow_id = ""

    files = profile.get("files")
    if not isinstance(files, dict):
        errors.append(f"{prefix}.files must be an object")
        files = {}

    runtime_name = files.get("runtime_db", "runtime.db")
    if not isinstance(runtime_name, str):
        errors.append(f"{prefix}.files.runtime_db must be a string")
        runtime_name = "runtime.db"

    runtime_db = fixture_dir / runtime_name
    if not runtime_db.is_file():
        errors.append(f"fixture runtime DB missing for {profile_name}: {runtime_db}")
        return errors

    db_version = _db_schema_version(runtime_db)
    if db_version != expected:
        errors.append(
            f"{runtime_db.name} ({profile_name}) schema_version={db_version}, expected {expected}; regenerate the fixture"
        )

    if isinstance(workflow_id, str) and workflow_id.strip() and not _workflow_present(runtime_db, workflow_id):
        errors.append(f"workflows row missing for workflow_id={workflow_id} in profile {profile_name}")

    return errors


def check_fixture(*, manifest_path: Path = MANIFEST_PATH, fixture_dir: Path = FIXTURE_DIR) -> list[str]:
    errors: list[str] = []
    expected = _expected_schema_version()
    manifest = _load_manifest(manifest_path)

    manifest_version = manifest.get("schema_version")
    if not isinstance(manifest_version, int):
        errors.append("manifest.schema_version must be an integer")
    elif manifest_version != expected:
        errors.append(
            f"manifest.schema_version={manifest_version} does not match code expected {expected}; "
            "run scripts/regenerate_replay_fixture.py after schema migrations"
        )

    for profile_name, profile in _iter_profile_entries(manifest):
        errors.extend(
            _check_profile(
                profile_name=profile_name,
                profile=profile,
                fixture_dir=fixture_dir,
                expected=expected,
            )
        )

    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Path to replay fixture manifest.json",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=FIXTURE_DIR,
        help="Directory containing replay fixture files",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    fixture_dir = args.fixture_dir.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    errors = check_fixture(manifest_path=manifest_path, fixture_dir=fixture_dir)
    if errors:
        for err in errors:
            console.print(f"[red]replay fixture check failed:[/red] {err}")
        return 1
    console.print(
        f"[green]replay fixture OK[/green] ({manifest_path.relative_to(REPO_ROOT)}) "
        f"schema_version={_expected_schema_version()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
