#!/usr/bin/env python3
"""Unified CLI for review workflow operations.

Subcommands:
  start   Generate config/review.yaml from a research question
  watch   Monitor workflow stage changes (cron-friendly)
  info    Show Rich diagnostic tables for a run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from scripts.lib._paths import ensure_repo_on_path

ensure_repo_on_path()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review workflow CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Generate review.yaml from a research question.")
    start.add_argument("--question", required=True, help="Plain-English research question.")
    start.add_argument(
        "--profile",
        default="standard",
        choices=["standard", "health_sdg"],
        help="Generation profile for config synthesis.",
    )
    start.add_argument(
        "--output",
        default="config/review.yaml",
        help="Output path for generated YAML (absolute or relative to repo root).",
    )

    watch = sub.add_parser("watch", help="Monitor major workflow stage changes.")
    watch.add_argument("--workflow-id", required=True, help="Workflow identifier (e.g. wf-0096).")
    watch.add_argument("--run-root", default="runs", help="Runs root used to resolve workflows_registry.db.")
    watch.add_argument("--state-file", help="Optional state file path for one-shot dedup output.")
    watch.add_argument("--json", action="store_true", help="Emit JSON in one-shot mode.")
    watch.add_argument("--reset-state", action="store_true", help="Reset dedup state before one-shot check.")
    watch.add_argument("--follow", action="store_true", help="Follow app.jsonl and stream major events.")
    watch.add_argument("--interval", type=float, default=2.0, help="Poll interval in follow mode.")

    info = sub.add_parser("info", help="Show Rich diagnostic tables for a run.")
    info_group = info.add_mutually_exclusive_group(required=True)
    info_group.add_argument("--workflow-id", "-w", help="Workflow ID (e.g. wf-d042e90e)")
    info_group.add_argument("--run-dir", "-d", help="Path to run directory containing runtime.db")
    info.add_argument("--run-root", default="runs", help="Root directory for runs (default: runs)")
    info.add_argument(
        "--fetch-pdfs",
        action="store_true",
        help="Attempt live full-text retrieval for included papers and save to papers/ dir",
    )
    info.add_argument(
        "--costs",
        action="store_true",
        help="After run info, print model usage summary from cost_records",
    )

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "start":
        from scripts.lib.review_start import run_start

        return await run_start(question=args.question, profile=args.profile, output=args.output)

    if args.command == "watch":
        from scripts.lib.review_watch import run_watch

        return await run_watch(
            workflow_id=args.workflow_id,
            run_root=args.run_root,
            state_file=args.state_file,
            json_output=args.json,
            reset_state=args.reset_state,
            follow=args.follow,
            interval=args.interval,
        )

    if args.command == "info":
        from scripts.lib.diag_costs import run_costs
        from scripts.lib.review_show_info import _resolve_db_path, run_info

        code = await run_info(
            workflow_id=args.workflow_id,
            run_dir=args.run_dir,
            run_root=args.run_root,
            fetch_pdfs=args.fetch_pdfs,
        )
        if code != 0 or not args.costs:
            return code

        db_path = await _resolve_db_path(args.run_dir, args.workflow_id, args.run_root)
        if db_path is None:
            print("Could not resolve runtime.db for cost summary.", file=sys.stderr)
            return 1
        print()
        return run_costs(Path(db_path))

    raise SystemExit(f"Unknown command: {args.command}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_dispatch(args))


if __name__ == "__main__":
    raise SystemExit(main())
