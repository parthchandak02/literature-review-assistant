#!/usr/bin/env python3
"""
Main Entry Point

Literature Review Assistant - Agentic AI System
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

    # Manuscript pipeline commands
    parser.add_argument(
        "--manubot-export",
        action="store_true",
        help="Export to Manubot structure after workflow completion",
    )

    parser.add_argument(
        "--build-package",
        action="store_true",
        help="Build submission package after workflow completion",
    )

    parser.add_argument(
        "--journal",
        type=str,
        help="Journal name for submission package (e.g., 'ieee', 'nature', 'plos')",
    )

    parser.add_argument(
        "--resolve-citation",
        type=str,
        help="Resolve a single citation from identifier (e.g., 'doi:10.1038/...' or 'pmid:12345678')",
    )

    parser.add_argument(
        "--list-journals",
        action="store_true",
        help="List available journals and exit",
    )

    parser.add_argument(
        "--validate-submission",
        type=str,
        help="Validate submission package for journal (requires --journal)",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Handle list-journals flag
    if args.list_journals:
        from src.export.journal_selector import JournalSelector
        
        selector = JournalSelector()
        journals = selector.list_journals()
        print("Available Journals:")
        print("=" * 50)
        for journal in journals:
            config = selector.get_journal_config(journal)
            if config:
                print(f"  {journal}: {config.get('name', journal)}")
        sys.exit(0)

    # Handle resolve-citation flag
    if args.resolve_citation:
        from src.citations.manubot_resolver import ManubotCitationResolver
        
        resolver = ManubotCitationResolver()
        try:
            csl_item = resolver.resolve_from_identifier(args.resolve_citation)
            paper = resolver.csl_to_paper(csl_item)
            print(f"Resolved citation: {args.resolve_citation}")
            print("=" * 50)
            print(f"Title: {paper.title}")
            print(f"Authors: {', '.join(paper.authors) if paper.authors else 'N/A'}")
            print(f"Year: {paper.year or 'N/A'}")
            print(f"Journal: {paper.journal or 'N/A'}")
            print(f"DOI: {paper.doi or 'N/A'}")
        except Exception as e:
            print(f"Error resolving citation: {e}")
            sys.exit(1)
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

    print("Literature Review Assistant - Agentic AI System")
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
        # Determine start phase
        start_phase = None
        if args.force_fresh:
            start_phase = 1
        elif args.start_from_phase:
            start_phase = args.start_from_phase
        
        results = manager.run(start_from_phase=start_phase)

        # Handle manuscript pipeline commands
        if args.manubot_export or args.build_package:
            from pathlib import Path
            from src.export.manubot_exporter import ManubotExporter
            from src.citations import CitationManager

            # Get article sections from results or workflow manager
            article_sections = getattr(manager, "_article_sections", {})
            if not article_sections and "article_sections" in results.get("outputs", {}):
                article_sections = results["outputs"]["article_sections"]

            if article_sections:
                citation_manager = CitationManager(manager.final_papers)
                
                # Manubot export
                if args.manubot_export:
                    manubot_config = manager.config.get("manubot", {})
                    if manubot_config.get("enabled", True):
                        output_dir = Path(manager.output_dir) / manubot_config.get("output_dir", "manuscript")
                        exporter = ManubotExporter(output_dir, citation_manager)
                        
                        metadata = {
                            "title": f"{manager.topic_context.topic}: A Systematic Review",
                            "keywords": manager.topic_context.keywords if hasattr(manager.topic_context, 'keywords') else [],
                        }
                        
                        manuscript_dir = exporter.export(
                            article_sections,
                            metadata,
                            citation_style=manubot_config.get("citation_style", "ieee"),
                            auto_resolve_citations=manubot_config.get("auto_resolve_citations", True),
                        )
                        results["outputs"]["manubot_export"] = str(manuscript_dir)
                        print(f"\nManubot structure exported to: {manuscript_dir}")

                # Build submission package
                if args.build_package:
                    journal = args.journal or manager.config.get("submission", {}).get("default_journal", "ieee")
                    from src.export.submission_package import SubmissionPackageBuilder
                    
                    manuscript_path = Path(results["outputs"].get("final_report", ""))
                    if not manuscript_path.exists():
                        manuscript_path = Path(manager.output_dir) / "final_report.md"
                    
                    if manuscript_path.exists():
                        builder = SubmissionPackageBuilder(Path(manager.output_dir))
                        submission_config = manager.config.get("submission", {})
                        
                        package_dir = builder.build_package(
                            results["outputs"],
                            journal,
                            manuscript_path,
                            generate_pdf=submission_config.get("generate_pdf", True),
                            generate_docx=submission_config.get("generate_docx", True),
                            generate_html=submission_config.get("generate_html", True),
                            include_supplementary=submission_config.get("include_supplementary", True),
                        )
                        results["outputs"]["submission_package"] = str(package_dir)
                        print(f"\nSubmission package created: {package_dir}")

        # Handle validate-submission
        if args.validate_submission:
            from src.export.submission_checklist import SubmissionChecklistGenerator
            from pathlib import Path
            
            journal = args.journal or args.validate_submission
            package_dir = Path(args.validate_submission) if Path(args.validate_submission).is_dir() else Path(manager.output_dir) / f"submission_package_{journal}"
            
            if package_dir.exists():
                generator = SubmissionChecklistGenerator()
                checklist = generator.generate_checklist(journal, package_dir)
                print("\n" + "=" * 50)
                print("Submission Checklist:")
                print("=" * 50)
                print(checklist)
            else:
                print(f"Submission package not found: {package_dir}")

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
