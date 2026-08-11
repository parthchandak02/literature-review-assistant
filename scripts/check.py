#!/usr/bin/env python3
"""Run individual quality checks (API docs, replay fixture, workflow replay)."""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check",
        description="Run quality checks before commit or release",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "api",
        help="Verify API docs Section 10.1 match FastAPI routes",
    )
    subparsers.add_parser(
        "replay-fixture",
        help="Verify replay test fixture matches database schema",
    )

    replay = subparsers.add_parser(
        "replay-workflow",
        help="Validate an existing workflow runtime.db against replay checks",
    )
    replay.add_argument("--workflow-id", required=True, help="Workflow ID to validate")
    replay.add_argument(
        "--db-path",
        default="",
        help="Optional direct runtime.db path",
    )
    replay.add_argument(
        "--profile",
        choices=["quick", "standard", "deep", "local", "adversarial"],
        default="standard",
        help="Validation profile depth",
    )
    replay.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit non-zero when any error-level check fails",
    )
    replay.add_argument(
        "--run-root",
        default="runs",
        help="Runs root used for registry lookups",
    )
    return parser


def _replay_workflow_argv(args: argparse.Namespace) -> list[str]:
    argv = ["--workflow-id", args.workflow_id, "--profile", args.profile, "--run-root", args.run_root]
    if args.db_path:
        argv.extend(["--db-path", args.db_path])
    if args.fail_on_error:
        argv.append("--fail-on-error")
    return argv


def _run_subcommand_main(module_main, script_name: str, argv: list[str] | None = None) -> int:
    previous_argv = sys.argv
    sys.argv = [script_name, *(argv or [])]
    try:
        result = module_main()
        if isinstance(result, int):
            return result
        return 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    finally:
        sys.argv = previous_argv


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "api":
        from scripts.lib.check_api_docs import main as api_main

        return _run_subcommand_main(api_main, "check_api_docs.py")

    if args.command == "replay-fixture":
        from scripts.lib.check_replay_fixture import main as fixture_main

        return _run_subcommand_main(fixture_main, "check_replay_fixture.py")

    if args.command == "replay-workflow":
        from scripts.lib.check_workflow_replay import main as replay_main

        return _run_subcommand_main(
            replay_main,
            "check_workflow_replay.py",
            _replay_workflow_argv(args),
        )

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
