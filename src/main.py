"""CLI entry point."""

from __future__ import annotations

# Set certifi CA bundle for SSL before any HTTP libs load (fixes macOS/python.org cert issues)
import os
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import argparse
from typing import Sequence

from rich.console import Console
from rich.table import Table

from src.orchestration import run_workflow_sync
from src.orchestration.context import RunContext, create_progress


def _print_run_summary(console: Console, summary: dict) -> None:
    """Print run summary as a Rich table."""
    table = Table(title="Workflow Run Complete")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Workflow ID", str(summary.get("workflow_id", "")))
    table.add_row("Log dir", str(summary.get("log_dir", "")))
    table.add_row("Output dir", str(summary.get("output_dir", "")))
    search_counts = summary.get("search_counts", {})
    search_str = ", ".join(f"{k}: {v}" for k, v in search_counts.items()) or "0"
    table.add_row("Search (by DB)", search_str)
    failures = summary.get("connector_init_failures", {})
    fail_count = len(failures)
    table.add_row("Connector failures", f"{fail_count} (see search appendix)" if fail_count else "0")
    table.add_row("Dedup removed", str(summary.get("dedup_count", 0)))
    table.add_row("Included papers", str(summary.get("included_papers", 0)))
    table.add_row("Extraction records", str(summary.get("extraction_records", 0)))
    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-agent-v2")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run")
    run.add_argument("--config", default="config/review.yaml")
    run.add_argument("--settings", default="config/settings.yaml")
    run.add_argument("--log-root", default="logs")
    run.add_argument("--output-root", default="data/outputs")
    run.add_argument("--verbose", "-v", action="store_true", help="Per-phase status, API call logging, screening summaries")
    run.add_argument("--debug", "-d", action="store_true", help="Verbose plus Pydantic model dumps at phase boundaries")
    run.add_argument("--offline", action="store_true", help="Force heuristic screening (no Gemini API) even when GEMINI_API_KEY is set")

    resume = sub.add_parser("resume")
    resume.add_argument("--topic")
    resume.add_argument("--workflow-id")

    validate = sub.add_parser("validate")
    validate.add_argument("--workflow-id", required=True)

    export = sub.add_parser("export")
    export.add_argument("--workflow-id", required=True)

    status = sub.add_parser("status")
    status.add_argument("--workflow-id", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    console = Console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "run":
        verbose = getattr(args, "verbose", False)
        debug = getattr(args, "debug", False)
        offline = getattr(args, "offline", False)
        if debug:
            verbose = True
        with create_progress(console) as progress:
            run_context = RunContext(
                console=console,
                verbose=verbose,
                debug=debug,
                offline=offline,
                progress=progress,
            )
            summary = run_workflow_sync(
                review_path=args.config,
                settings_path=args.settings,
                log_root=args.log_root,
                output_root=args.output_root,
                run_context=run_context,
            )
        _print_run_summary(console, summary)
        return 0
    console.print(
        f"Command '{args.command}' is not yet available in the single-path milestone. "
        "Use `run` for workflow execution."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
