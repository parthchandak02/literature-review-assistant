#!/usr/bin/env python3
"""
[Recurring Usage Script] List Papers

List all papers found in the workflow.

Can read from:
- Workflow state JSON file
- Papers JSON file
- Or run a quick search to show papers
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

console = Console()


def load_papers_from_state(state_file: Path) -> Optional[List[Dict]]:
    """Load papers from workflow state file."""
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        
        # Try different possible keys
        papers = state.get("all_papers") or state.get("papers") or state.get("unique_papers")
        
        if papers:
            return papers
    except Exception as e:
        console.print(f"[yellow]Could not load from state file: {e}[/yellow]")
    
    return None


def load_papers_from_json(json_file: Path) -> Optional[List[Dict]]:
    """Load papers from JSON file."""
    try:
        with open(json_file, "r") as f:
            papers = json.load(f)
        
        if isinstance(papers, list):
            return papers
    except Exception as e:
        console.print(f"[yellow]Could not load from JSON file: {e}[/yellow]")
    
    return None


def search_for_paper_files(output_dir: Path) -> List[Path]:
    """Search for paper files in output directory."""
    paper_files = []
    
    # Look for various patterns
    patterns = [
        "*papers*.json",
        "*all_papers*.json",
        "*search_results*.json",
        "*workflow_state*.json",
    ]
    
    for pattern in patterns:
        paper_files.extend(list(output_dir.glob(pattern)))
    
    return paper_files


def display_papers(papers: List[Dict], title: str = "Papers Found"):
    """Display papers in a nice table format."""
    if not papers:
        console.print("[yellow]No papers found[/yellow]")
        return
    
    console.print(Panel.fit(f"[bold]{title}[/bold] - {len(papers)} papers", border_style="blue"))
    
    # Create table
    table = Table(title=f"{len(papers)} Papers", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold", width=60)
    table.add_column("Authors", width=40)
    table.add_column("Year", width=6, justify="center")
    table.add_column("Database", width=15)
    table.add_column("DOI", width=20)
    
    for i, paper in enumerate(papers, 1):
        # Handle both dict and Paper object
        if isinstance(paper, dict):
            title_text = paper.get("title", "[No title]")
            authors = paper.get("authors", [])
            authors_str = ", ".join(authors[:3]) if authors else "[No authors]"
            if len(authors) > 3:
                authors_str += f" ... (+{len(authors) - 3} more)"
            year = str(paper.get("year", "")) if paper.get("year") else ""
            database = paper.get("database", "Unknown")
            doi = paper.get("doi", "")
        else:
            # Paper object
            title_text = paper.title if paper.title else "[No title]"
            authors = paper.authors if paper.authors else []
            authors_str = ", ".join(authors[:3]) if authors else "[No authors]"
            if len(authors) > 3:
                authors_str += f" ... (+{len(authors) - 3} more)"
            year = str(paper.year) if paper.year else ""
            database = paper.database if paper.database else "Unknown"
            doi = paper.doi if paper.doi else ""
        
        # Truncate long titles
        if len(title_text) > 80:
            title_text = title_text[:77] + "..."
        
        table.add_row(
            str(i),
            title_text,
            authors_str,
            year,
            database,
            doi[:20] if doi else "",
        )
    
    console.print(table)
    
    # Summary statistics
    papers_with_titles = sum(1 for p in papers if (p.get("title") if isinstance(p, dict) else p.title))
    papers_with_authors = sum(1 for p in papers if (p.get("authors") if isinstance(p, dict) else p.authors))
    papers_with_doi = sum(1 for p in papers if (p.get("doi") if isinstance(p, dict) else p.doi))
    
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Total papers: {len(papers)}")
    console.print(f"  With titles: {papers_with_titles}/{len(papers)} ({papers_with_titles/len(papers)*100:.1f}%)")
    console.print(f"  With authors: {papers_with_authors}/{len(papers)} ({papers_with_authors/len(papers)*100:.1f}%)")
    console.print(f"  With DOI: {papers_with_doi}/{len(papers)} ({papers_with_doi/len(papers)*100:.1f}%)")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="List papers found in workflow")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/outputs",
        help="Output directory to search for paper files",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        help="Path to workflow state JSON file",
    )
    parser.add_argument(
        "--papers-file",
        type=str,
        help="Path to papers JSON file",
    )
    parser.add_argument(
        "--quick-search",
        action="store_true",
        help="Run a quick search to show papers (uses workflow config)",
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    papers = None
    
    # Try to load from specified file
    if args.state_file:
        papers = load_papers_from_state(Path(args.state_file))
    
    if not papers and args.papers_file:
        papers = load_papers_from_json(Path(args.papers_file))
    
    # Try to find files automatically
    if not papers and output_dir.exists():
        paper_files = search_for_paper_files(output_dir)
        
        for paper_file in paper_files:
            console.print(f"[dim]Trying to load from: {paper_file}[/dim]")
            
            if "state" in paper_file.name.lower():
                papers = load_papers_from_state(paper_file)
            else:
                papers = load_papers_from_json(paper_file)
            
            if papers:
                break
    
    # If still no papers and quick search requested
    if not papers and args.quick_search:
        console.print("[cyan]Running quick search...[/cyan]")
        try:
            from src.orchestration.workflow_manager import WorkflowManager
            
            config_file = Path("config/workflow.yaml")
            if config_file.exists():
                manager = WorkflowManager(str(config_file))
                manager._build_search_strategy()
                search_results = manager._search_databases()
                
                # Convert to dict format
                papers = []
                for paper in search_results:
                    papers.append({
                        "title": paper.title,
                        "authors": paper.authors,
                        "year": paper.year,
                        "doi": paper.doi,
                        "database": paper.database,
                        "abstract": paper.abstract,
                    })
            else:
                console.print("[red]Config file not found: config/workflow.yaml[/red]")
        except Exception as e:
            console.print(f"[red]Error running search: {e}[/red]")
    
    if papers:
        display_papers(papers)
    else:
        console.print("[red]No papers found. Try running the workflow first or use --quick-search[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
