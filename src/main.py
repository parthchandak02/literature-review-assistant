"""CLI entry point."""

from __future__ import annotations

# Set certifi CA bundle for SSL before any HTTP libs load (fixes macOS/python.org cert issues)
import os

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Sequence

import aiosqlite
from rich.console import Console
from rich.table import Table

from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback
from src.export import package_submission, validate_ieee, validate_prisma
from src.orchestration import run_workflow_resume, run_workflow_sync
from src.orchestration.context import RunContext, create_progress
from src.utils.structured_log import load_events_from_jsonl


async def _run_export(workflow_id: str, run_root: str) -> str | None:
    """Run export for workflow. Returns submission dir path or None."""
    result = await package_submission(workflow_id=workflow_id, run_root=run_root)
    return str(result) if result else None


async def _run_validate(workflow_id: str, run_root: str, console: Console) -> bool:
    """Run validators. Returns True if all pass."""
    import json
    from pathlib import Path

    entry = await find_by_workflow_id(run_root, workflow_id)
    if entry is None:
        entry = await find_by_workflow_id_fallback(run_root, workflow_id)
    if entry is None:
        console.print(f"[red]Error:[/] Workflow '{workflow_id}' not found.")
        return False

    log_dir = str(Path(entry.db_path).parent)
    run_summary_path = Path(log_dir) / "run_summary.json"
    if not run_summary_path.exists():
        console.print("[red]Error:[/] run_summary.json not found.")
        return False

    data = json.loads(run_summary_path.read_text(encoding="utf-8"))
    output_dir = data.get("output_dir")
    artifacts = data.get("artifacts", {})
    submission_dir = Path(output_dir) / "submission" if output_dir else None

    tex_content = None
    bib_content = ""
    md_content = ""
    md_path = Path(artifacts.get("manuscript_md", ""))
    if not md_path.exists() and output_dir:
        md_path = Path(output_dir) / "doc_manuscript.md"
    if md_path.exists():
        md_content = md_path.read_text(encoding="utf-8")

    if submission_dir and submission_dir.exists():
        tex_path = submission_dir / "manuscript.tex"
        bib_path = submission_dir / "references.bib"
        tex_content = tex_path.read_text(encoding="utf-8") if tex_path.exists() else None
        bib_content = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
    else:
        console.print("[yellow]Note:[/] submission/ not found. IEEE validation requires `export` first.")

    ieee_result = validate_ieee(tex_content or "", bib_content) if tex_content or bib_content else None
    prisma_result = validate_prisma(tex_content, md_content)

    all_pass = (ieee_result.passed if ieee_result else True) and prisma_result.passed
    if ieee_result:
        if ieee_result.errors:
            for e in ieee_result.errors:
                console.print(f"[red]IEEE:[/] {e}")
        if ieee_result.warnings:
            for w in ieee_result.warnings:
                console.print(f"[yellow]IEEE:[/] {w}")
        if ieee_result.passed and not ieee_result.errors:
            console.print("[green]IEEE validation:[/] PASSED")

    console.print(
        f"[green]PRISMA:[/] {prisma_result.reported_count}/27 reported "
        f"({'PASSED' if prisma_result.passed else 'FAILED'})"
    )
    return all_pass


async def _run_status(workflow_id: str, run_root: str, console: Console) -> bool:
    """Print workflow status. Returns True if found."""
    import json
    from pathlib import Path

    entry = await find_by_workflow_id(run_root, workflow_id)
    if entry is None:
        entry = await find_by_workflow_id_fallback(run_root, workflow_id)
    if entry is None:
        console.print(f"[red]Error:[/] Workflow '{workflow_id}' not found.")
        return False

    log_dir = str(Path(entry.db_path).parent)
    run_summary_path = Path(log_dir) / "run_summary.json"
    if run_summary_path.exists():
        data = json.loads(run_summary_path.read_text(encoding="utf-8"))
        table = Table(title=f"Workflow {workflow_id}")
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")
        for k in ["workflow_id", "run_id", "log_dir", "output_dir"]:
            table.add_row(k, str(data.get(k, "")))
        table.add_row("registry_status", entry.status)
        table.add_row("included_papers", str(data.get("included_papers", "")))
        table.add_row("extraction_records", str(data.get("extraction_records", "")))
        artifacts = data.get("artifacts", {})
        table.add_row("artifacts", ", ".join(Path(p).name for p in artifacts.values()) if artifacts else "")
        console.print(table)
    else:
        console.print(f"[dim]Status:[/] {entry.status} (db: {entry.db_path})")
    return True


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


class _HelpfulParser(argparse.ArgumentParser):
    """Parser that suggests correct resume usage when user passes resume args to run."""

    def error(self, message: str) -> None:
        if "unrecognized arguments" in message and ("resume" in message or "workflow-id" in message):
            sys.stderr.write(f"research-agent-v2: {message}\n")
            sys.stderr.write(
                "\nHint: 'resume' and '--workflow-id' belong to the resume subcommand, not run.\n"
                "Use: uv run python -m src.main resume --workflow-id <id>\n"
            )
            sys.exit(2)
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _HelpfulParser(prog="research-agent-v2")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run")
    run.add_argument("--config", default="config/review.yaml")
    run.add_argument("--settings", default="config/settings.yaml")
    run.add_argument("--run-root", default="runs")
    run.add_argument("--fresh", action="store_true", help="Always start new run; skip resume prompt (needed when running in Progress context)")
    run.add_argument("--verbose", "-v", action="store_true", help="Per-phase status, API call logging, screening summaries")
    run.add_argument("--debug", "-d", action="store_true", help="Verbose plus Pydantic model dumps at phase boundaries")
    run.add_argument("--offline", action="store_true", help="Force heuristic screening (no LLM API calls) even when API keys are set")

    resume = sub.add_parser("resume")
    resume.add_argument("--topic", help="Resume by topic (research question, case-insensitive)")
    resume.add_argument("--workflow-id", help="Resume by workflow ID (e.g. wf-abc123)")
    resume.add_argument("--config", default="config/review.yaml")
    resume.add_argument("--settings", default="config/settings.yaml")
    resume.add_argument("--run-root", default="runs")
    resume.add_argument("--verbose", "-v", action="store_true")
    resume.add_argument("--debug", "-d", action="store_true")

    validate = sub.add_parser("validate")
    validate.add_argument("--workflow-id", required=True)
    validate.add_argument("--run-root", default="runs")

    export = sub.add_parser("export")
    export.add_argument("--workflow-id", required=True)
    export.add_argument("--run-root", default="runs")

    status = sub.add_parser("status")
    status.add_argument("--workflow-id", required=True)
    status.add_argument("--run-root", default="runs")

    return parser


async def _backfill_event_log(log_dir: str, workflow_id: str) -> None:
    """Populate event_log in the run's SQLite DB from the app.jsonl written by structured_log.

    This makes phase timeline and activity log work in the web UI for CLI runs.
    Uses INSERT OR IGNORE so it is safe to call multiple times.
    """
    db_path = str(Path(log_dir) / "runtime.db")
    jsonl_path = str(Path(log_dir) / "app.jsonl")
    events = load_events_from_jsonl(jsonl_path)
    if not events:
        return
    import json as _json
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO event_log (workflow_id, event_type, payload, ts) VALUES (?, ?, ?, ?)",
                [
                    (
                        workflow_id,
                        e.get("type", "unknown"),
                        _json.dumps(e, default=str),
                        str(e.get("ts", "")),
                    )
                    for e in events
                ],
            )
            await db.commit()
    except Exception:
        pass


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
                run_root=args.run_root,
                run_context=run_context,
                fresh=getattr(args, "fresh", False),
            )
        _print_run_summary(console, summary)
        log_dir = summary.get("log_dir")
        workflow_id = summary.get("workflow_id")
        if log_dir and workflow_id:
            asyncio.run(_backfill_event_log(str(log_dir), str(workflow_id)))
        return 0

    if args.command == "resume":
        if not getattr(args, "topic", None) and not getattr(args, "workflow_id", None):
            console.print("[red]Error:[/] Either --topic or --workflow-id is required for resume.")
            return 1
        verbose = getattr(args, "verbose", False)
        debug = getattr(args, "debug", False)
        if debug:
            verbose = True
        try:
            with create_progress(console) as progress:
                run_context = RunContext(
                    console=console,
                    verbose=verbose,
                    debug=debug,
                    offline=False,
                    progress=progress,
                )
                summary = asyncio.run(
                    run_workflow_resume(
                        workflow_id=getattr(args, "workflow_id", None),
                        topic=getattr(args, "topic", None),
                        review_path=args.config,
                        settings_path=args.settings,
                        run_root=args.run_root,
                        run_context=run_context,
                    )
                )
            _print_run_summary(console, summary)
            return 0
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/] {e}")
            return 1
        except ValueError as e:
            console.print(f"[red]Error:[/] {e}")
            return 1

    if args.command == "export":
        try:
            result = asyncio.run(
                _run_export(
                    workflow_id=args.workflow_id,
                    run_root=args.run_root,
                )
            )
            if result is None:
                console.print(f"[red]Error:[/] Workflow '{args.workflow_id}' not found.")
                return 1
            console.print(f"[green]Export complete:[/] {result}")
            return 0
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            return 1

    if args.command == "validate":
        try:
            ok = asyncio.run(
                _run_validate(
                    workflow_id=args.workflow_id,
                    run_root=args.run_root,
                    console=console,
                )
            )
            return 0 if ok else 1
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            return 1

    if args.command == "status":
        try:
            ok = asyncio.run(
                _run_status(
                    workflow_id=args.workflow_id,
                    run_root=args.run_root,
                    console=console,
                )
            )
            return 0 if ok else 1
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            return 1

    console.print(
        f"Command '{args.command}' is not yet available in the single-path milestone. "
        "Use `run` for workflow execution."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
