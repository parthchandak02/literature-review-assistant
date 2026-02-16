"""CLI entry point."""

from __future__ import annotations

import argparse
from typing import Sequence

from rich.console import Console

from src.config.loader import load_configs
from src.search.live_validation import run_live_phase2_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-agent-v2")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run")
    run.add_argument("--config", default="config/review.yaml")
    run.add_argument("--settings", default="config/settings.yaml")

    phase2_live = sub.add_parser("phase2-live")
    phase2_live.add_argument("--config", default="config/review.yaml")
    phase2_live.add_argument("--settings", default="config/settings.yaml")
    phase2_live.add_argument("--log-root", default="logs")

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
        review_config, settings_config = load_configs(args.config, args.settings)
        console.print(
            f"Loaded configs for review_type={review_config.review_type} "
            f"with {len(settings_config.agents)} agent profiles."
        )
        return 0
    if args.command == "phase2-live":
        summary = run_live_phase2_sync(
            review_path=args.config,
            settings_path=args.settings,
            log_root=args.log_root,
        )
        console.print(f"Phase 2 live run complete. Log dir: {summary['log_dir']}")
        console.print(f"Run summary: {summary['log_dir']}/run_summary.json")
        console.print(f"Successful connectors: {', '.join(summary['successful_connectors'])}")
        return 0

    console.print(f"Command '{args.command}' is scaffolded for later phases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
