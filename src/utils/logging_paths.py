"""Unified run path helpers for all phases.

All per-run files (operational DB, app log, output documents, figures) live
under a single run directory:
    <run_root>/<YYYY-MM-DD>/<topic-slug>/run_<HH-MM-SSAM>/
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def workflow_slug(text: str, max_len: int = 64) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9\s-]", "", normalized)
    normalized = re.sub(r"\s+", "-", normalized).strip("-")
    if not normalized:
        normalized = "workflow"
    return normalized[:max_len].rstrip("-")


@dataclass(frozen=True)
class RunPaths:
    """All paths for a single workflow run, under one directory."""

    run_dir: Path
    date_folder: str
    run_dir_name: str
    # Operational
    runtime_db: Path
    app_log: Path
    run_summary: Path
    acceptance_checklist: Path
    revalidation_log: Path
    phase_readiness: Path
    # Output documents / figures
    search_appendix: Path
    protocol_markdown: Path


def create_run_paths(run_root: str, workflow_description: str) -> RunPaths:
    """Create and return all paths for a new workflow run.

    Creates the run directory on disk. Every log and output artifact for
    this run lives inside the returned run_dir.
    """
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    run_dir_name = f"run_{now.strftime('%I-%M-%S%p')}"
    run_dir = Path(run_root) / date_folder / workflow_slug(workflow_description) / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        run_dir=run_dir,
        date_folder=date_folder,
        run_dir_name=run_dir_name,
        runtime_db=run_dir / "runtime.db",
        app_log=run_dir / "app.jsonl",
        run_summary=run_dir / "run_summary.json",
        acceptance_checklist=run_dir / "acceptance_checklist.md",
        revalidation_log=run_dir / "revalidation.log",
        phase_readiness=run_dir / "phase_readiness.md",
        search_appendix=run_dir / "doc_search_strategies_appendix.md",
        protocol_markdown=run_dir / "doc_protocol.md",
    )
