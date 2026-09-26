"""Helpers for read-only replay tests against committed fixture databases."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPLAY_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "replay"


def committed_replay_runtime_path(profile: str = "default") -> tuple[str, Path]:
    """Return (workflow_id, path) for a profile in tests/fixtures/replay/manifest.json."""
    manifest_path = REPLAY_FIXTURE_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = manifest.get("profiles")
    if isinstance(profiles, dict) and profile in profiles and isinstance(profiles[profile], dict):
        payload = profiles[profile]
        workflow_id = str(payload.get("workflow_id", manifest["workflow_id"]))
        files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
        db_name = str(files.get("runtime_db", "runtime.db"))
    else:
        workflow_id = str(manifest["workflow_id"])
        files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
        db_name = str(files.get("runtime_db", "runtime.db"))
    return workflow_id, REPLAY_FIXTURE_DIR / db_name


def copy_runtime_db_to_tmp(source: Path, tmp_dir: Path, *, name: str = "runtime.db") -> Path:
    """Copy a runtime.db into a writable temp directory (schema migrations must not touch commits)."""
    dest = tmp_dir / name
    shutil.copy2(source, dest)
    return dest
