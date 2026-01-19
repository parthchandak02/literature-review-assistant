#!/usr/bin/env python3
"""
Main Entry Point

Research Article Writer Agentic AI System
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from src.orchestration.workflow_manager import WorkflowManager
from src.config.debug_config import DebugLevel
from src.utils.logging_config import setup_logging, LogLevel

# Load environment variables from .env file
load_dotenv()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Research Article Writer Agentic AI System",
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
        "--log-to-file", action="store_true", help="Log to file in addition to console"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default="logs/workflow.log",
        help="Path to log file (default: logs/workflow.log)",
    )

    parser.add_argument("--no-metrics", action="store_true", help="Disable metrics display")

    parser.add_argument("--no-costs", action="store_true", help="Disable cost tracking display")

    parser.add_argument(
        "--test-databases",
        action="store_true",
        help="Test database connectors and exit (does not run workflow)",
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
        "--test-stage",
        type=str,
        help="Test a specific stage only (requires --checkpoint or --fixture)",
    )

    parser.add_argument(
        "--fixture",
        type=str,
        help="Test fixture JSON file path",
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

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

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

    # Setup logging
    setup_logging(
        level=LogLevel(debug_level.value),
        log_to_file=args.log_to_file,
        log_file=args.log_file,
        verbose=verbose,
        debug=args.debug,
    )

    # Set debug config in environment for components to pick up
    os.environ["DEBUG"] = "true" if args.debug else "false"
    os.environ["VERBOSE"] = "true" if args.verbose else "false"
    os.environ["DEBUG_LEVEL"] = debug_level.value
    if args.log_to_file:
        os.environ["LOG_TO_FILE"] = "true"
        os.environ["LOG_FILE"] = args.log_file

    print("Research Article Writer Agentic AI System")
    print("=" * 50)
    if args.debug:
        print("DEBUG MODE ENABLED")
    elif args.verbose:
        print("VERBOSE MODE ENABLED")
    print("=" * 50)

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

    # Handle test-stage mode
    if args.test_stage:
        from scripts.test_stage import test_stage
        test_stage(
            args.test_stage,
            args.checkpoint,
            args.fixture,
            config_path,
            False,  # test_citations
            False,  # test_charts
            False,  # validate_only
            False,  # save_checkpoint
        )
        return

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
        manager.debug_config.log_to_file = args.log_to_file
        manager.debug_config.log_file = args.log_file
        manager.debug_config.show_metrics = not args.no_metrics
        manager.debug_config.show_costs = not args.no_costs
        
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
        results = manager.run()

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
