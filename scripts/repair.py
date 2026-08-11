#!/usr/bin/env python3
"""Repair old or broken review runs (manuscript, extraction, citations, test fixtures).

Subcommands:
  finalize              Regenerate doc_manuscript.md appended sections for a run
  re-extract            Re-run LLM extraction for failed/placeholder records
  inject-citations      Patch missing included-study citations into manuscript
  regen-replay-fixture  Rebuild tests/fixtures/replay from a completed workflow
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from scripts.lib._paths import ensure_repo_on_path

ensure_repo_on_path()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair old or broken review runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    finalize = sub.add_parser(
        "finalize",
        help="Regenerate appended sections in an existing doc_manuscript.md.",
    )
    finalize.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing doc_manuscript.md and runtime.db",
    )

    re_extract = sub.add_parser(
        "re-extract",
        help="Re-run LLM extraction for papers with failed/placeholder extraction data.",
    )
    re_extract.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing runtime.db",
    )
    re_extract.add_argument(
        "--config",
        default=None,
        help=(
            "Path to the review.yaml config to use. "
            "Defaults to run_dir/config_snapshot.yaml if present, then config/review.yaml."
        ),
    )

    inject = sub.add_parser(
        "inject-citations",
        help="Inject missing included-study citations into a completed run's manuscript.",
    )
    inject_group = inject.add_mutually_exclusive_group(required=True)
    inject_group.add_argument(
        "--run-dir",
        help="Path to the run directory containing runtime.db and doc_manuscript.md",
    )
    inject_group.add_argument(
        "--workflow-id",
        help="Workflow ID (e.g. wf-0005) to look up in the central registry",
    )

    regen = sub.add_parser(
        "regen-replay-fixture",
        help="Rebuild tests/fixtures/replay from an existing completed workflow run.",
    )
    regen.add_argument(
        "--profile",
        choices=["default", "adversarial"],
        default="default",
        help="Fixture profile to regenerate (default: completed happy-path replay)",
    )
    regen.add_argument("--workflow-id", default="", help="Workflow id stored in the source runtime.db")
    regen.add_argument("--run-root", default="runs", help="Runs root for registry resolution")
    regen.add_argument(
        "--source-run-dir",
        default="",
        help="Run directory containing runtime.db, or a direct path to runtime.db",
    )
    regen.add_argument("--db-path", default="", help="Optional direct runtime.db path")
    regen.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Fixture output directory (default: tests/fixtures/replay)",
    )

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "finalize":
        from scripts.lib.maint_finalize import run_finalize

        return await run_finalize(args.run_dir)

    if args.command == "re-extract":
        from scripts.lib.maint_re_extract import run_re_extract

        return await run_re_extract(args.run_dir, args.config)

    if args.command == "inject-citations":
        from scripts.lib.inject_citations import resolve_run_dir, run_inject_citations

        try:
            run_dir = resolve_run_dir(run_dir=args.run_dir, workflow_id=args.workflow_id)
        except (FileNotFoundError, LookupError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return await run_inject_citations(run_dir)

    if args.command == "regen-replay-fixture":
        from scripts.lib.maint_replay_fixture import run_regen_replay_fixture

        return await run_regen_replay_fixture(
            profile=args.profile,
            workflow_id=args.workflow_id,
            run_root=args.run_root,
            source_run_dir=args.source_run_dir,
            db_path=args.db_path,
            output_dir=args.output_dir,
        )

    raise SystemExit(f"Unknown command: {args.command}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_dispatch(args))


if __name__ == "__main__":
    raise SystemExit(main())
