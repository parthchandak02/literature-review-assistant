"""Aggregate key signals from historical run app.jsonl logs.

Focuses on:
- screening kappa
- included/screened counts
- transient LLM errors and rate-limit signals
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class RunStats:
    run_dir: str
    workflow_id: str
    screened: int | None = None
    included: int | None = None
    kappa: float | None = None
    llm_transient_errors: int = 0
    rate_limit_wait_events: int = 0
    rate_limit_resolved_events: int = 0
    deadline_exceeded_mentions: int = 0


def _scan_file(path: Path) -> RunStats:
    stats = RunStats(run_dir=str(path.parent), workflow_id="")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        parsed: dict | None = None
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except Exception:
                parsed = None
        if parsed is None and line.startswith('"') and line.endswith('"'):
            try:
                parsed = json.loads(json.loads(line))
            except Exception:
                parsed = None

        lower = line.lower()
        if "llm transient error" in lower:
            stats.llm_transient_errors += 1
        if "deadline_exceeded" in lower:
            stats.deadline_exceeded_mentions += 1
        if "rate_limit_wait" in lower:
            stats.rate_limit_wait_events += 1
        if "rate_limit_resolved" in lower:
            stats.rate_limit_resolved_events += 1

        if not parsed:
            continue
        if not stats.workflow_id:
            stats.workflow_id = str(parsed.get("workflow_id", ""))

        if parsed.get("phase") == "phase_3_screening" and parsed.get("action") == "done":
            summary = parsed.get("summary", {}) or {}
            try:
                stats.screened = int(summary.get("screened")) if summary.get("screened") is not None else None
            except Exception:
                pass
            try:
                stats.included = int(summary.get("included")) if summary.get("included") is not None else None
            except Exception:
                pass
            try:
                kappa_val = summary.get("kappa")
                stats.kappa = float(kappa_val) if kappa_val is not None else None
            except Exception:
                pass
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze historical app.jsonl run logs.")
    parser.add_argument("--runs-root", default="runs")
    args = parser.parse_args()

    root = Path(args.runs_root)
    log_files = sorted(root.glob("**/app.jsonl"))
    if not log_files:
        console.print("[red]No app.jsonl files found.[/red]")
        return 1

    all_stats = [_scan_file(p) for p in log_files]

    table = Table(title="Historical Run Signals")
    table.add_column("Workflow")
    table.add_column("Run dir")
    table.add_column("Screened", justify="right")
    table.add_column("Included", justify="right")
    table.add_column("Kappa", justify="right")
    table.add_column("Transient", justify="right")
    table.add_column("DeadlineExceeded", justify="right")
    table.add_column("RL wait", justify="right")

    for s in all_stats:
        table.add_row(
            s.workflow_id or "-",
            Path(s.run_dir).name,
            str(s.screened) if s.screened is not None else "-",
            str(s.included) if s.included is not None else "-",
            f"{s.kappa:.3f}" if s.kappa is not None else "-",
            str(s.llm_transient_errors),
            str(s.deadline_exceeded_mentions),
            str(s.rate_limit_wait_events),
        )
    console.print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
