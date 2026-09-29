#!/usr/bin/env python3
"""Redraw a run's PRISMA figure and prisma_counts.json from its runtime.db (no LLM calls).

Usage:
  uv run python scripts/regenerate_prisma.py --run <run-dir | runtime.db | wf-XXXX> [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from scripts.lib._paths import ensure_repo_on_path

ensure_repo_on_path()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Redraw the PRISMA figure and counts sidecar from runtime.db.")
    parser.add_argument("--run", required=True, help="Run directory, runtime.db path, or workflow id (wf-XXXX)")
    parser.add_argument("--run-root", default="runs", help="Run root for workflow id lookup (default: runs)")
    parser.add_argument("--dry-run", action="store_true", help="Print old vs new counts; write nothing")
    args = parser.parse_args(argv)

    from src.prisma.regenerate import format_counts_diff, regenerate_prisma, stale_manuscript_warning

    try:
        result = asyncio.run(regenerate_prisma(args.run, dry_run=args.dry_run, run_root=args.run_root))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(format_counts_diff(result))
    if args.dry_run:
        print("dry run: nothing written")
    else:
        for path in result.written:
            print(f"wrote {path}")
    warning = stale_manuscript_warning(result)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    if not result.new.arithmetic_valid:
        print("warning: PRISMA arithmetic check failed for the new counts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
