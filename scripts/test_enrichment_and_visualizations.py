#!/usr/bin/env python3
"""
[Temporary Testing Script] Enrichment and Visualization Test

Tests the paper enrichment functionality and regenerates visualizations
with enriched data to verify the fixes from the enhanced visualization plan.
"""

import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel

from src.enrichment.paper_enricher import PaperEnricher
from src.visualization.charts import ChartGenerator
from src.utils.state_serialization import StateSerializer
from src.search.connectors.base import Paper

console = Console()
logger = logging.getLogger(__name__)


def find_best_checkpoint(checkpoint_path: str) -> str:
    """Find the best checkpoint file (preferring later stages with final_papers)."""
    checkpoint_file = Path(checkpoint_path)
    checkpoint_dir = checkpoint_file.parent
    
    # Prefer checkpoints in this order (later stages have final_papers)
    preferred_files = [
        "data_extraction_state.json",
        "fulltext_screening_state.json",
        "title_abstract_screening_state.json",
    ]
    
    # If a specific file was provided, check if it exists
    if checkpoint_file.exists():
        # Check if it's a directory or file
        if checkpoint_file.is_dir():
            checkpoint_dir = checkpoint_file
        else:
            # Try to find a better checkpoint in the same directory
            for preferred in preferred_files:
                preferred_path = checkpoint_dir / preferred
                if preferred_path.exists():
                    console.print(f"[dim]Found better checkpoint: {preferred}[/dim]")
                    return str(preferred_path)
            return str(checkpoint_file)
    
    # Try to find preferred checkpoints in the directory
    for preferred in preferred_files:
        preferred_path = checkpoint_dir / preferred
        if preferred_path.exists():
            console.print(f"[dim]Using checkpoint: {preferred}[/dim]")
            return str(preferred_path)
    
    # Fall back to provided path
    if checkpoint_file.exists():
        return str(checkpoint_file)
    
    raise FileNotFoundError(f"No checkpoint found: {checkpoint_path}")


def load_checkpoint_papers(checkpoint_path: str) -> List[Paper]:
    """Load papers from checkpoint file."""
    # Find the best checkpoint
    best_checkpoint = find_best_checkpoint(checkpoint_path)
    checkpoint_file = Path(best_checkpoint)
    
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"Checkpoint not found: {best_checkpoint}")
    
    with open(checkpoint_file, "r") as f:
        checkpoint_data = json.load(f)
    
    serializer = StateSerializer()
    
    # Try to get final_papers first, then eligible_papers, then screened_papers
    papers_data = None
    if "final_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["final_papers"]
    elif "eligible_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["eligible_papers"]
    elif "screened_papers" in checkpoint_data.get("data", {}):
        papers_data = checkpoint_data["data"]["screened_papers"]
    else:
        raise ValueError("No papers found in checkpoint data")
    
    papers = serializer.deserialize_papers(papers_data)
    return papers


def test_enrichment(papers: List[Paper], progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Paper]:
    """Test enrichment of papers."""
    # Count papers that need enrichment
    papers_needing_enrichment = [p for p in papers if not p.affiliations and p.doi]
    papers_with_affiliations = [p for p in papers if p.affiliations]
    papers_without_doi = [p for p in papers if not p.doi]
    
    # Calculate time estimate (10 req/sec = 0.1 sec per paper)
    estimated_time = len(papers_needing_enrichment) * 0.1
    
    console.print(Panel(
        "[bold cyan]Testing Paper Enrichment[/bold cyan]\n"
        f"Enriching {len(papers)} papers with missing affiliation data...\n"
        f"[dim]Estimated time: ~{estimated_time:.1f} seconds[/dim]",
        title="Enrichment Test",
        border_style="cyan"
    ))
    
    console.print(f"\n[dim]Papers needing enrichment: {len(papers_needing_enrichment)}[/dim]")
    console.print(f"[dim]Papers already with affiliations: {len(papers_with_affiliations)}[/dim]")
    console.print(f"[dim]Papers without DOI: {len(papers_without_doi)}[/dim]")
    
    if not papers_needing_enrichment:
        console.print("[yellow]No papers need enrichment - all papers already have affiliations or no DOI[/yellow]")
        return papers
    
    # Run enrichment with progress updates
    enricher = PaperEnricher()
    enriched = []
    enriched_count = 0
    skipped_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Enriching papers...",
            total=len(papers_needing_enrichment)
        )
        
        processed_count = 0
        for i, paper in enumerate(papers, 1):
            # Skip if already has affiliations
            if paper.affiliations:
                enriched.append(paper)
                skipped_count += 1
                continue
            
            # Skip if no DOI
            if not paper.doi:
                enriched.append(paper)
                skipped_count += 1
                continue
            
            # Try to fetch enriched data
            try:
                enriched_paper = enricher._fetch_by_doi(paper.doi)
                if enriched_paper and enriched_paper.affiliations:
                    # Update paper with enriched affiliations
                    paper.affiliations = enriched_paper.affiliations
                    enriched_count += 1
                    logger.debug(
                        f"Enriched paper {i}/{len(papers)}: {paper.title[:50]}... "
                        f"(found {len(enriched_paper.affiliations)} affiliations)"
                    )
                else:
                    logger.debug(
                        f"No affiliations found for paper {i}/{len(papers)}: {paper.doi}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to enrich paper {i}/{len(papers)} (DOI: {paper.doi}): {e}"
                )
            
            enriched.append(paper)
            processed_count += 1
            
            # Update progress bar (only for papers that were actually processed)
            progress.update(task, advance=1)
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(i, len(papers))
    
    console.print(f"\n[green]Enrichment complete![/green]")
    console.print(f"[green]Papers with affiliations: {enriched_count + len(papers_with_affiliations)}/{len(enriched)}[/green]")
    
    return enriched


def regenerate_visualizations(papers: List[Paper], output_dir: str = "data/outputs"):
    """Regenerate visualizations with enriched data."""
    console.print(Panel(
        "[bold cyan]Regenerating Visualizations[/bold cyan]\n"
        f"Generating charts for {len(papers)} papers...",
        title="Visualization Generation",
        border_style="cyan"
    ))
    
    chart_generator = ChartGenerator(output_dir=output_dir)
    
    # Generate all visualizations
    viz_paths = {}
    
    # Papers per year
    console.print("\n[dim]Generating papers per year chart...[/dim]")
    year_path = chart_generator.papers_per_year(papers)
    if year_path:
        viz_paths["papers_per_year"] = year_path
        console.print(f"[green]Generated: {year_path}[/green]")
    
    # Papers by country
    console.print("\n[dim]Generating papers by country chart...[/dim]")
    country_path = chart_generator.papers_by_country(papers)
    if country_path:
        viz_paths["papers_by_country"] = country_path
        console.print(f"[green]Generated: {country_path}[/green]")
    
    # Papers by subject
    console.print("\n[dim]Generating papers by subject chart...[/dim]")
    subject_path = chart_generator.papers_by_subject(papers)
    if subject_path:
        viz_paths["papers_by_subject"] = subject_path
        console.print(f"[green]Generated: {subject_path}[/green]")
    
    # Network graph
    console.print("\n[dim]Generating network graph...[/dim]")
    network_path = chart_generator.network_graph(papers)
    if network_path:
        viz_paths["network_graph"] = network_path
        console.print(f"[green]Generated: {network_path}[/green]")
    
    return viz_paths


def analyze_results(papers: List[Paper], viz_paths: Dict[str, str]):
    """Analyze and display results."""
    console.print(Panel(
        "[bold green]Results Analysis[/bold green]",
        title="Analysis",
        border_style="green"
    ))
    
    # Count papers with affiliations
    papers_with_affiliations = [p for p in papers if p.affiliations]
    affiliation_count = len(papers_with_affiliations)
    
    # Extract countries
    countries = []
    for paper in papers:
        if paper.country:
            countries.append(paper.country)
        elif paper.affiliations:
            # Try to extract country from affiliations
            chart_gen = ChartGenerator()
            country = chart_gen._extract_country_from_affiliations(paper.affiliations)
            if country:
                countries.append(country)
    
    unique_countries = list(set(countries))
    
    # Extract subjects
    subjects = []
    chart_gen = ChartGenerator()
    for paper in papers:
        if paper.subjects:
            for subject in paper.subjects:
                normalized = chart_gen._normalize_subject(subject)
                if normalized:
                    subjects.append(normalized)
        elif paper.keywords:
            for keyword in paper.keywords:
                normalized = chart_gen._normalize_subject(keyword)
                if normalized:
                    subjects.append(normalized)
    
    unique_subjects = list(set(subjects))
    subject_counts = {}
    for subject in subjects:
        subject_counts[subject] = subject_counts.get(subject, 0) + 1
    
    # Display results
    console.print(f"\n[bold]Papers with affiliations:[/bold] {affiliation_count}/{len(papers)} ({affiliation_count/len(papers)*100:.1f}%)")
    console.print(f"[bold]Unique countries found:[/bold] {len(unique_countries)}")
    if unique_countries:
        console.print(f"  Countries: {', '.join(unique_countries[:10])}")
        if len(unique_countries) > 10:
            console.print(f"  ... and {len(unique_countries) - 10} more")
    
    console.print(f"\n[bold]Unique subjects found:[/bold] {len(unique_subjects)}")
    if unique_subjects:
        console.print("  Subject distribution:")
        for subject, count in sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            console.print(f"    - {subject}: {count}")
    
    console.print(f"\n[bold]Generated visualizations:[/bold] {len(viz_paths)}")
    for name, path in viz_paths.items():
        console.print(f"  - {name}: {path}")


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test enrichment and regenerate visualizations")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="data/checkpoints/workflow_llm-powered_health_literacy_ch_20260118_212151/title_abstract_screening_state.json",
        help="Path to checkpoint file or directory"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/outputs",
        help="Output directory for visualizations"
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip enrichment step (just regenerate visualizations)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)"
    )
    
    args = parser.parse_args()
    
    # Configure logging based on verbose flag
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console.print("[dim]Verbose logging enabled[/dim]")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    # Logger is already defined at module level
    
    try:
        # Load papers from checkpoint
        console.print(f"[cyan]Loading papers from checkpoint: {args.checkpoint}[/cyan]")
        papers = load_checkpoint_papers(args.checkpoint)
        console.print(f"[green]Loaded {len(papers)} papers[/green]")
        
        # Test enrichment (unless skipped)
        if not args.skip_enrichment:
            papers = test_enrichment(papers)
        else:
            console.print("[yellow]Skipping enrichment step[/yellow]")
        
        # Regenerate visualizations
        viz_paths = regenerate_visualizations(papers, args.output_dir)
        
        # Analyze results
        analyze_results(papers, viz_paths)
        
        console.print("\n[bold green]Test complete![/bold green]")
        console.print("\n[dim]Next steps:[/dim]")
        console.print("  1. Check the generated visualizations in the output directory")
        console.print("  2. Verify country chart shows multiple countries")
        console.print("  3. Verify subject chart shows multiple subject categories")
        console.print("  4. Check network graph HTML file is generated")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
