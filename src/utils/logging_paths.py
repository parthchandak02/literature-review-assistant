"""Unified log path and artifact naming helpers for all phases."""

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
class LogRunPaths:
    run_dir: Path
    run_summary: Path
    acceptance_checklist: Path
    revalidation_log: Path
    phase_readiness: Path
    runtime_db: Path
    app_log: Path


@dataclass(frozen=True)
class OutputRunPaths:
    run_dir: Path
    search_appendix: Path
    protocol_markdown: Path


def create_run_paths(log_root: str, workflow_description: str) -> LogRunPaths:
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    run_folder = f"run_{now.strftime('%I-%M-%S%p')}"
    run_dir = Path(log_root) / date_folder / workflow_slug(workflow_description) / run_folder
    run_dir.mkdir(parents=True, exist_ok=True)
    return LogRunPaths(
        run_dir=run_dir,
        run_summary=run_dir / "run_summary.json",
        acceptance_checklist=run_dir / "acceptance_checklist.md",
        revalidation_log=run_dir / "revalidation.log",
        phase_readiness=run_dir / "phase_readiness.md",
        runtime_db=run_dir / "runtime.db",
        app_log=run_dir / "app.jsonl",
    )


def create_output_paths(output_root: str, workflow_description: str, run_dir_name: str, date_folder: str) -> OutputRunPaths:
    run_dir = Path(output_root) / date_folder / workflow_slug(workflow_description) / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return OutputRunPaths(
        run_dir=run_dir,
        search_appendix=run_dir / "doc_search_strategies_appendix.md",
        protocol_markdown=run_dir / "doc_protocol.md",
    )
