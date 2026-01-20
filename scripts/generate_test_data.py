#!/usr/bin/env python3
"""
[Utility Script] Test Data Generator

Generate test fixtures from checkpoints or create mock data.
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.testing.stage_loader import StageLoader
from tests.fixtures.test_helpers import (
    create_mock_papers,
    create_mock_screening_results,
    create_mock_extracted_data,
    serialize_papers_for_json,
    serialize_screening_results_for_json,
    serialize_extracted_data_for_json,
)

console = Console()


def generate_from_checkpoint(
    checkpoint_path: str,
    output_dir: str,
    stage_name: Optional[str] = None,
):
    """Generate fixtures from checkpoint."""
    loader = StageLoader()
    
    checkpoint_file = Path(checkpoint_path)
    if checkpoint_file.is_dir():
        # Generate fixtures for all stages in directory
        checkpoints = loader.list_available_checkpoints(checkpoint_path)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating fixtures...", total=len(checkpoints))
            
            for checkpoint in checkpoints:
                checkpoint_path_obj = Path(checkpoint)
                phase_name = checkpoint_path_obj.stem.replace("_state", "")
                
                # Load checkpoint
                state = loader._load_from_checkpoint(checkpoint)
                
                # Determine fixture filename
                stage_to_fixture = {
                    "search_databases": "stage_01_search_results.json",
                    "deduplication": "stage_02_deduplicated.json",
                    "title_abstract_screening": "stage_03_title_screened.json",
                    "fulltext_screening": "stage_04_fulltext_screened.json",
                    "data_extraction": "stage_05_extracted_data.json",
                    "article_writing": "stage_06_article_sections.json",
                }
                
                fixture_filename = stage_to_fixture.get(
                    phase_name,
                    f"{phase_name}.json"
                )
                
                # Save fixture
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
                fixture_path = output_path / fixture_filename
                
                with open(fixture_path, "w") as f:
                    json.dump(state, f, indent=2, default=str)
                
                progress.update(task, advance=1)
                console.print(f"[green]Generated: {fixture_path}[/green]")
    else:
        # Generate fixture for single checkpoint
        if not stage_name:
            # Try to infer from filename
            stage_name = checkpoint_file.stem.replace("_state", "")
        
        state = loader._load_from_checkpoint(str(checkpoint_file), stage_name)
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        fixture_path = output_path / f"{stage_name}.json"
        
        with open(fixture_path, "w") as f:
            json.dump(state, f, indent=2, default=str)
        
        console.print(f"[green]Generated: {fixture_path}[/green]")


def generate_mock_data(
    stage: str,
    count: int,
    output_dir: str,
    topic: str = "test topic",
):
    """Generate mock test data for a stage."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    if stage == "search_databases":
        papers = create_mock_papers(count, topic)
        fixture_data = {
            "stage": "search_databases",
            "data": {
                "all_papers": serialize_papers_for_json(papers),
                "database_breakdown": {"PubMed": count // 2, "arXiv": count // 2},
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_01_search_results.json"
    
    elif stage == "deduplication":
        papers = create_mock_papers(count, topic)
        fixture_data = {
            "stage": "deduplication",
            "data": {
                "unique_papers": serialize_papers_for_json(papers),
                "all_papers": serialize_papers_for_json(papers),
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_02_deduplicated.json"
    
    elif stage == "title_abstract_screening":
        papers = create_mock_papers(count, topic)
        results = create_mock_screening_results(papers, include_ratio=0.7)
        included_papers = [p for p, r in zip(papers, results) if r.decision.value == "include"]
        
        fixture_data = {
            "stage": "title_abstract_screening",
            "data": {
                "screened_papers": serialize_papers_for_json(included_papers),
                "title_abstract_results": serialize_screening_results_for_json(results),
                "unique_papers": serialize_papers_for_json(papers),
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_03_title_screened.json"
    
    elif stage == "fulltext_screening":
        papers = create_mock_papers(count, topic)
        results = create_mock_screening_results(papers, include_ratio=0.6)
        eligible_papers = [p for p, r in zip(papers, results) if r.decision.value == "include"]
        
        fixture_data = {
            "stage": "fulltext_screening",
            "data": {
                "eligible_papers": serialize_papers_for_json(eligible_papers),
                "fulltext_results": serialize_screening_results_for_json(results),
                "screened_papers": serialize_papers_for_json(papers),
                "fulltext_available_count": len(papers),
                "fulltext_unavailable_count": 0,
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_04_fulltext_screened.json"
    
    elif stage == "data_extraction":
        papers = create_mock_papers(count, topic)
        extracted = create_mock_extracted_data(papers)
        
        fixture_data = {
            "stage": "data_extraction",
            "data": {
                "extracted_data": serialize_extracted_data_for_json(extracted),
                "final_papers": serialize_papers_for_json(papers),
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_05_extracted_data.json"
    
    elif stage == "article_writing":
        fixture_data = {
            "stage": "article_writing",
            "data": {
                "article_sections": {
                    "introduction": "This is a test introduction section.",
                    "methods": "This is a test methods section.",
                    "results": "This is a test results section.",
                    "discussion": "This is a test discussion section.",
                },
            },
            "topic_context": {"topic": topic},
        }
        filename = "stage_06_article_sections.json"
    
    else:
        console.print(f"[red]Unknown stage: {stage}[/red]")
        return
    
    fixture_path = output_path / filename
    with open(fixture_path, "w") as f:
        json.dump(fixture_data, f, indent=2, default=str)
    
    console.print(f"[green]Generated mock data: {fixture_path}[/green]")


def generate_all_stages(output_dir: str, count: int = 10, topic: str = "test topic"):
    """Generate fixtures for all stages."""
    stages = [
        "search_databases",
        "deduplication",
        "title_abstract_screening",
        "fulltext_screening",
        "data_extraction",
        "article_writing",
    ]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating all fixtures...", total=len(stages))
        
        for stage in stages:
            generate_mock_data(stage, count, output_dir, topic)
            progress.update(task, advance=1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate test fixtures from checkpoints or create mock data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--from-checkpoint",
        type=str,
        help="Generate fixtures from checkpoint file or directory",
    )
    
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Generate mock data instead of using checkpoint",
    )
    
    parser.add_argument(
        "--stage",
        type=str,
        help="Stage name (required for --mock)",
    )
    
    parser.add_argument(
        "--all-stages",
        action="store_true",
        help="Generate fixtures for all stages",
    )
    
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of mock papers to generate (default: 10)",
    )
    
    parser.add_argument(
        "--topic",
        type=str,
        default="test topic",
        help="Topic for mock data generation (default: 'test topic')",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="tests/fixtures/stages",
        help="Output directory for fixtures (default: tests/fixtures/stages)",
    )
    
    args = parser.parse_args()
    
    if args.from_checkpoint:
        generate_from_checkpoint(args.from_checkpoint, args.output)
    elif args.all_stages:
        generate_all_stages(args.output, args.count, args.topic)
    elif args.mock:
        if not args.stage:
            parser.error("--stage required when using --mock")
        generate_mock_data(args.stage, args.count, args.output, args.topic)
    else:
        parser.error("Must provide --from-checkpoint, --mock, or --all-stages")


if __name__ == "__main__":
    main()
