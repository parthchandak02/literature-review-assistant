#!/usr/bin/env python3
"""
Main Entry Point

Literature Review Assistant - Agentic AI System
"""

import os
import sys

# Configure SSL certificates BEFORE any other imports
# This ensures all HTTPS requests (including third-party libraries) use certifi
try:
    import ssl

    import certifi

    # Set environment variables for requests and other libraries
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

    # Monkey patch SSL context creation to use certifi
    _original_create_default_context = ssl.create_default_context

    def _patched_create_default_context(purpose=ssl.Purpose.SERVER_AUTH, *args, **kwargs):
        kwargs.setdefault("cafile", certifi.where())
        return _original_create_default_context(purpose, *args, **kwargs)

    ssl.create_default_context = _patched_create_default_context
except ImportError:
    pass  # certifi not installed, use system certificates

import argparse

from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule

from src.config.debug_config import DebugLevel
from src.orchestration.workflow_manager import WorkflowManager
from src.utils.logging_config import LogLevel, setup_logging

console = Console()

# Load environment variables from .env file
load_dotenv()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Literature Review Assistant - Agentic AI System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("WORKFLOW_CONFIG", "config/workflow.yaml"),
        help="Path to workflow configuration file (default: config/workflow.yaml)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output (detailed logging)",
    )

    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode (full logging with all details)",
    )

    parser.add_argument(
        "--verbose-level",
        type=str,
        choices=["minimal", "normal", "detailed", "full"],
        default="normal",
        help="Set verbose level: minimal, normal, detailed, or full (default: normal)",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        nargs="?",
        const="logs/workflow.log",
        default=None,
        help="Enable file logging. Use --log-file to log to default location (logs/workflow.log) or --log-file <path> to specify custom path",
    )

    parser.add_argument("--no-metrics", action="store_true", help="Disable metrics display")

    parser.add_argument("--no-costs", action="store_true", help="Disable cost tracking display")

    parser.add_argument(
        "--test-databases",
        action="store_true",
        help="Test database connectors and exit (does not run workflow)",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Automatically find and resume from the latest checkpoint for this topic (this is the default behavior - flag makes it explicit)",
    )

    parser.add_argument(
        "--resume-from",
        type=str,
        help="Resume workflow from a specific phase (requires --checkpoint)",
    )

    parser.add_argument(
        "--checkpoint",
        type=str,
        help="Checkpoint directory or file path to load state from",
    )


    parser.add_argument(
        "--save-checkpoints",
        action="store_true",
        default=True,
        help="Save checkpoints after each phase (default: True)",
    )

    parser.add_argument(
        "--no-save-checkpoints",
        action="store_true",
        help="Disable checkpoint saving",
    )

    parser.add_argument(
        "--start-from-phase",
        type=int,
        help="Force start from a specific phase (1-based). Use --start-from-phase 1 to ignore all checkpoints and start fresh.",
    )

    parser.add_argument(
        "--force-fresh",
        action="store_true",
        help="Force fresh start from phase 1, ignoring all checkpoints (equivalent to --start-from-phase 1)",
    )


    parser.add_argument(
        "--no-auto-fill-qa",
        action="store_true",
        help="Disable automatic LLM-based quality assessment filling (default: auto-fill is enabled)",
    )

    parser.add_argument(
        "--auto-fill-qa",
        action="store_true",
        help="Enable automatic LLM-based quality assessment filling (default: enabled, use --no-auto-fill-qa to disable)",
    )

    # Cleanup commands
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up old workflow folders, keeping only the most recent per topic",
    )

    parser.add_argument(
        "--topic",
        type=str,
        help="Topic filter for cleanup (use with --cleanup)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup without actually deleting files (use with --cleanup)",
    )

    parser.add_argument(
        "--keep-n",
        type=int,
        default=1,
        help="Number of most recent workflow folders to keep per topic (default: 1, use with --cleanup)",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Handle cleanup flag
    if args.cleanup:
        from src.utils.workflow_cleaner import WorkflowCleaner

        cleaner = WorkflowCleaner()
        report = cleaner.cleanup(dry_run=args.dry_run, topic_filter=args.topic, keep_n=args.keep_n)
        print(report)
        sys.exit(0)


    # Handle test-databases flag
    if args.test_databases:
        from scripts.test_database_health import DatabaseHealthChecker

        print("Testing database connectors...")
        print("=" * 50)
        checker = DatabaseHealthChecker()
        all_working = checker.run_all_checks()
        sys.exit(0 if all_working else 1)

    # Determine debug level
    if args.debug:
        debug_level = DebugLevel.FULL
        verbose = True
    elif args.verbose:
        debug_level = DebugLevel.DETAILED
        verbose = True
    else:
        debug_level = DebugLevel(args.verbose_level)
        verbose = debug_level in [DebugLevel.DETAILED, DebugLevel.FULL]

    # Simplified log file handling: if --log-file is specified, enable file logging
    log_to_file = args.log_file is not None
    log_file = args.log_file if args.log_file is not None else "logs/workflow.log"

    # Setup logging
    setup_logging(
        level=LogLevel(debug_level.value),
        log_to_file=log_to_file,
        log_file=log_file,
        verbose=verbose,
        debug=args.debug,
    )

    # Set debug config in environment for components to pick up
    os.environ["DEBUG"] = "true" if args.debug else "false"
    os.environ["VERBOSE"] = "true" if args.verbose else "false"
    os.environ["DEBUG_LEVEL"] = debug_level.value
    if log_to_file:
        os.environ["LOG_TO_FILE"] = "true"
        os.environ["LOG_FILE"] = log_file

    console.print()
    console.print(
        Rule("[bold cyan]Literature Review Assistant - Agentic AI System[/bold cyan]", style="cyan")
    )
    if args.debug:
        console.print("[bold yellow]DEBUG MODE ENABLED[/bold yellow]")
    elif args.verbose:
        console.print("[bold cyan]VERBOSE MODE ENABLED[/bold cyan]")
    console.print(Rule(style="cyan"))
    console.print()

    # Get config path
    config_path = args.config

    # Check for API keys
    llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    llm_api_key = None
    if llm_provider in ["openai", "gpt"]:
        llm_api_key = os.getenv("OPENAI_API_KEY")
    elif llm_provider in ["anthropic", "claude"]:
        llm_api_key = os.getenv("ANTHROPIC_API_KEY")
    elif llm_provider in ["gemini", "google"]:
        llm_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    elif llm_provider == "perplexity":
        llm_api_key = os.getenv("PERPLEXITY_API_KEY")
    else:
        # Fallback: try all common API keys
        llm_api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )

    if not llm_api_key:
        print("\nWarning: No LLM API key found.")
        print(
            f"Set API key for provider '{llm_provider}' (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GEMINI_API_KEY, or PERPLEXITY_API_KEY)."
        )
        print("Continuing with fallback (keyword-based) methods...\n")


    # Create workflow manager (loads config from YAML)
    try:
        # Handle resume from checkpoint
        if args.resume_from:
            if not args.checkpoint:
                print("\nError: --checkpoint required when using --resume-from")
                sys.exit(1)

            manager = WorkflowManager.resume_from_phase(
                args.resume_from,
                args.checkpoint,
                config_path,
            )
        else:
            manager = WorkflowManager(config_path)

        # Override debug config from CLI args
        manager.debug_config.enabled = (
            args.debug or args.verbose or debug_level != DebugLevel.NORMAL
        )
        manager.debug_config.level = debug_level
        manager.debug_config.log_to_file = log_to_file
        manager.debug_config.log_file = log_file
        manager.debug_config.show_metrics = not args.no_metrics
        manager.debug_config.show_costs = not args.no_costs

        # Override quality assessment auto-fill from CLI args
        if args.no_auto_fill_qa:
            manager.config.setdefault("quality_assessment", {})["auto_fill"] = False
        elif args.auto_fill_qa:
            manager.config.setdefault("quality_assessment", {})["auto_fill"] = True

        # Handle checkpoint saving
        if args.no_save_checkpoints:
            manager.save_checkpoints = False
        else:
            manager.save_checkpoints = args.save_checkpoints

    except FileNotFoundError:
        print(f"\nError: Configuration file not found: {config_path}")
        print("Please create config/workflow.yaml or set WORKFLOW_CONFIG environment variable.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError loading configuration: {e}")
        sys.exit(1)

    # Run workflow
    try:
        # Determine start phase
        start_phase = None
        if args.force_fresh:
            start_phase = 1
        elif args.start_from_phase:
            start_phase = args.start_from_phase
        elif args.resume:
            # --resume flag: explicitly enable automatic checkpoint detection
            # (this is the default behavior, but --resume makes it explicit)
            start_phase = None  # Let automatic detection handle it

        results = manager.run(start_from_phase=start_phase)

        if not args.debug and not args.verbose:
            print("\n" + "=" * 50)
            print("Workflow Results:")
            print("=" * 50)
            for key, value in results["outputs"].items():
                print(f"{key}: {value}")

            print(f"\nFinal report: {results['outputs'].get('final_report', 'N/A')}")

    except Exception as e:
        print(f"\nError during workflow execution: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
