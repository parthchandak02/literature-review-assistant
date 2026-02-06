#!/usr/bin/env python3
"""
[Recurring Usage Script] Stage Testing CLI Tool

Test individual workflow stages using checkpoints or test fixtures.
Used by: python main.py --test-stage
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.orchestration.workflow_manager import WorkflowManager
from src.testing.stage_loader import StageLoader
from src.testing.stage_validators import StageValidatorFactory, CitationValidator, ChartValidator

console = Console()


def list_checkpoints(checkpoint_dir: str):
    """List available checkpoints."""
    loader = StageLoader()
    checkpoints = loader.list_available_checkpoints(checkpoint_dir)
    
    if not checkpoints:
        console.print(f"[yellow]No checkpoints found in {checkpoint_dir}[/yellow]")
        return
    
    table = Table(title="Available Checkpoints")
    table.add_column("Checkpoint File", style="cyan")
    table.add_column("Phase", style="green")
    
    for checkpoint in checkpoints:
        checkpoint_path = Path(checkpoint)
        phase_name = checkpoint_path.stem.replace("_state", "")
        table.add_row(str(checkpoint_path), phase_name)
    
    console.print(table)


def list_fixtures():
    """List available fixtures."""
    loader = StageLoader()
    fixtures = loader.list_available_fixtures()
    
    if not fixtures:
        console.print("[yellow]No fixtures found[/yellow]")
        return
    
    table = Table(title="Available Fixtures")
    table.add_column("Fixture File", style="cyan")
    
    for fixture in fixtures:
        table.add_row(str(fixture))
    
    console.print(table)


def validate_stage(
    stage: str,
    checkpoint_path: Optional[str] = None,
    fixture_path: Optional[str] = None,
):
    """Validate prerequisites for a stage."""
    loader = StageLoader()
    validator = StageValidatorFactory.create(stage)
    
    # Load state
    if checkpoint_path:
        state = loader.load_stage_data("checkpoint", stage, checkpoint_path)
    elif fixture_path:
        loader.fixtures_dir = Path(fixture_path).parent
        state = loader._load_from_fixture(Path(fixture_path).stem)
    else:
        console.print("[red]Error: Must provide --checkpoint or --fixture[/red]")
        return
    
    # Validate prerequisites
    result = validator.validate_prerequisites(stage, state)
    
    if result.is_valid:
        console.print(Panel(
            "[green]Validation passed[/green]\n"
            + "\n".join(result.warnings) if result.warnings else "No issues found",
            title="Prerequisites Validation",
            border_style="green"
        ))
    else:
        console.print(Panel(
            "[red]Validation failed[/red]\n"
            + "\n".join(result.errors)
            + ("\n\nWarnings:\n" + "\n".join(result.warnings) if result.warnings else ""),
            title="Prerequisites Validation",
            border_style="red"
        ))
        sys.exit(1)


def test_stage(
    stage: str,
    checkpoint_path: Optional[str] = None,
    fixture_path: Optional[str] = None,
    config_path: Optional[str] = None,
    test_citations: bool = False,
    test_charts: bool = False,
    validate_only: bool = False,
    save_checkpoint: bool = False,
):
    """Test a specific stage."""
    console.print(f"[bold cyan]Testing stage: {stage}[/bold cyan]")
    
    # Load state
    loader = StageLoader()
    
    if checkpoint_path:
        state = loader.load_stage_data("checkpoint", stage, checkpoint_path)
        console.print(f"[green]Loaded checkpoint from: {checkpoint_path}[/green]")
    elif fixture_path:
        loader.fixtures_dir = Path(fixture_path).parent
        state = loader._load_from_fixture(Path(fixture_path).stem)
        console.print(f"[green]Loaded fixture from: {fixture_path}[/green]")
    else:
        console.print("[red]Error: Must provide --checkpoint or --fixture[/red]")
        return
    
    # Validate prerequisites
    validator = StageValidatorFactory.create(stage)
    prereq_result = validator.validate_prerequisites(stage, state)
    
    if not prereq_result.is_valid:
        console.print(Panel(
            "[red]Prerequisites validation failed[/red]\n"
            + "\n".join(prereq_result.errors),
            title="Error",
            border_style="red"
        ))
        sys.exit(1)
    
    if prereq_result.warnings:
        console.print(Panel(
            "[yellow]Warnings:[/yellow]\n" + "\n".join(prereq_result.warnings),
            title="Prerequisites Warnings",
            border_style="yellow"
        ))
    
    if validate_only:
        console.print("[green]Validation only - skipping execution[/green]")
        return
    
    # Load state into WorkflowManager
    if checkpoint_path:
        # Resume from checkpoint
        checkpoint_file = Path(checkpoint_path)
        if checkpoint_file.is_dir():
            checkpoint_file = checkpoint_file / f"{stage}_state.json"
        
        manager = WorkflowManager.resume_from_phase(
            stage,
            str(checkpoint_file),
            config_path,
        )
    else:
        # Load from fixture
        manager = WorkflowManager(config_path)
        manager.load_state_from_dict(state)
    
    # Execute stage
    console.print(f"[bold]Executing stage: {stage}[/bold]")
    
    try:
        # Map stage names to phase execution
        stage_execution_map = {
            "search": lambda: manager._search_databases(),
            "deduplication": lambda: manager.deduplicator.deduplicate_papers(manager.all_papers),
            "title_screening": lambda: manager._screen_title_abstract(),
            "fulltext_screening": lambda: manager._screen_fulltext(),
            "extraction": lambda: manager._extract_data(),
            "prisma": lambda: manager._generate_prisma_diagram(),
            "visualizations": lambda: manager._generate_visualizations(),
            "writing": lambda: manager._write_article(),
            "report": lambda: manager._generate_final_report(
                getattr(manager, "_article_sections", {}),
                "",
                {}
            ),
        }
        
        # Normalize stage name
        stage_normalized = stage.replace("_", "").lower()
        if "title" in stage_normalized and "abstract" in stage_normalized:
            stage_normalized = "title_screening"
        elif "fulltext" in stage_normalized or "full" in stage_normalized:
            stage_normalized = "fulltext_screening"
        elif "visualization" in stage_normalized:
            stage_normalized = "visualizations"
        elif "article" in stage_normalized or "writing" in stage_normalized:
            stage_normalized = "writing"
        
        if stage_normalized in stage_execution_map:
            result = stage_execution_map[stage_normalized]()
            console.print("[green]Stage executed successfully[/green]")
        else:
            # Use run_from_stage as fallback
            result = manager.run_from_stage(stage)
            console.print("[green]Stage executed successfully[/green]")
        
        # Specialized validation
        if test_citations and stage in ["writing", "report"]:
            citation_validator = CitationValidator()
            article_sections = getattr(manager, "_article_sections", {})
            papers_data = [p.__dict__ if hasattr(p, "__dict__") else p for p in manager.final_papers]
            citation_result = citation_validator.validate_citations(article_sections, papers_data)
            
            if citation_result.is_valid:
                console.print("[green]Citation validation passed[/green]")
            else:
                console.print(f"[red]Citation validation failed: {citation_result.errors}[/red]")
        
        if test_charts and stage == "visualizations":
            chart_validator = ChartValidator()
            chart_paths = result if isinstance(result, dict) else {}
            papers_data = [p.__dict__ if hasattr(p, "__dict__") else p for p in manager.final_papers]
            chart_result = chart_validator.validate_charts(chart_paths, papers_data)
            
            if chart_result.is_valid:
                console.print("[green]Chart validation passed[/green]")
            else:
                console.print(f"[red]Chart validation failed: {chart_result.errors}[/red]")
        
        # Save checkpoint if requested
        if save_checkpoint:
            checkpoint_path = manager._save_phase_state(stage)
            if checkpoint_path:
                console.print(f"[green]Saved checkpoint to: {checkpoint_path}[/green]")
        
    except Exception as e:
        console.print(Panel(
            f"[red]Error executing stage: {e}[/red]",
            title="Execution Error",
            border_style="red"
        ))
        import traceback
        console.print(traceback.format_exc())
        sys.exit(1)


def test_stage_range(
    from_stage: str,
    to_stage: str,
    checkpoint_path: str,
    config_path: Optional[str] = None,
):
    """Test a range of stages."""
    console.print(f"[bold cyan]Testing stages from {from_stage} to {to_stage}[/bold cyan]")
    
    # Load checkpoint for from_stage
    checkpoint_file = Path(checkpoint_path)
    if checkpoint_file.is_dir():
        checkpoint_file = checkpoint_file / f"{from_stage}_state.json"
    
    manager = WorkflowManager.resume_from_phase(
        from_stage,
        str(checkpoint_file),
        config_path,
    )
    
    # Execute range
    manager.run_from_stage(from_stage, to_stage)
    console.print("[green]Stage range executed successfully[/green]")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Test individual workflow stages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--stage",
        type=str,
        help="Stage to test (e.g., 'title_screening', 'writing', 'visualizations')",
    )
    
    parser.add_argument(
        "--checkpoint",
        type=str,
        help="Path to checkpoint file or directory",
    )
    
    parser.add_argument(
        "--fixture",
        type=str,
        help="Path to test fixture JSON file",
    )
    
    parser.add_argument(
        "--from-stage",
        type=str,
        help="Start stage for range testing",
    )
    
    parser.add_argument(
        "--to-stage",
        type=str,
        help="End stage for range testing",
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("WORKFLOW_CONFIG", "config/workflow.yaml"),
        help="Path to workflow config file",
    )
    
    parser.add_argument(
        "--test-citations",
        action="store_true",
        help="Test citation features specifically",
    )
    
    parser.add_argument(
        "--test-charts",
        action="store_true",
        help="Test chart features specifically",
    )
    
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate prerequisites, don't execute",
    )
    
    parser.add_argument(
        "--save-checkpoint",
        action="store_true",
        help="Save checkpoint after execution",
    )
    
    parser.add_argument(
        "--list-checkpoints",
        type=str,
        metavar="DIR",
        help="List available checkpoints in directory",
    )
    
    parser.add_argument(
        "--list-fixtures",
        action="store_true",
        help="List available fixtures",
    )
    
    args = parser.parse_args()
    
    # Handle list commands
    if args.list_checkpoints:
        list_checkpoints(args.list_checkpoints)
        return
    
    if args.list_fixtures:
        list_fixtures()
        return
    
    # Validate arguments
    if not args.stage and not args.from_stage:
        parser.error("Must provide --stage or --from-stage")
    
    if args.from_stage and not args.to_stage:
        parser.error("--to-stage required when using --from-stage")
    
    if args.from_stage:
        if not args.checkpoint:
            parser.error("--checkpoint required for range testing")
        test_stage_range(args.from_stage, args.to_stage, args.checkpoint, args.config)
        return
    
    if not args.checkpoint and not args.fixture:
        parser.error("Must provide --checkpoint or --fixture")
    
    if args.checkpoint and args.fixture:
        parser.error("Cannot use both --checkpoint and --fixture")
    
    # Test single stage
    test_stage(
        args.stage,
        args.checkpoint,
        args.fixture,
        args.config,
        args.test_citations,
        args.test_charts,
        args.validate_only,
        args.save_checkpoint,
    )


if __name__ == "__main__":
    main()
