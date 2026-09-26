"""Filesystem path guards for web endpoints that accept client-supplied paths."""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterable

from fastapi import HTTPException

RUNS_ROOTS_ENV = "LITREVIEW_RUNS_ROOTS"
DEFAULT_RUNS_ROOT = "runs"

_DENIED_SUFFIXES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
    ".env",
)


def configured_runs_roots() -> list[pathlib.Path]:
    """Resolved run roots clients may target: ``runs/`` plus ``LITREVIEW_RUNS_ROOTS`` entries."""
    roots = [pathlib.Path(DEFAULT_RUNS_ROOT).resolve()]
    for raw in os.environ.get(RUNS_ROOTS_ENV, "").split(os.pathsep):
        if raw.strip():
            roots.append(pathlib.Path(raw.strip()).expanduser().resolve())
    return roots


def is_under_any(path: pathlib.Path, roots: Iterable[pathlib.Path | str]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(pathlib.Path(root).resolve()) for root in roots)


def require_allowed_run_root(run_root: str) -> pathlib.Path:
    """Return the resolved run root, or raise 400 when it is outside the configured runs roots."""
    resolved = pathlib.Path(run_root).expanduser().resolve()
    if not is_under_any(resolved, configured_runs_roots()):
        raise HTTPException(status_code=400, detail="run_root must be under the configured runs directory")
    return resolved


def is_sensitive_file(path: pathlib.Path) -> bool:
    name = path.name.lower()
    return name.endswith(_DENIED_SUFFIXES) or name == ".env" or name.startswith(".env.")
