#!/usr/bin/env python3
"""
[Recurring Usage Script] End-to-End Workflow Test

Tests the complete research paper generation workflow with real database connectors.
Validates outputs at each phase and reports any issues found.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.workflow_manager import WorkflowManager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Load environment variables
load_dotenv()

console = Console()

# Test configuration
TEST_TOPIC = "health literacy chatbots"
TEST_CONFIG = {
    "topic": {
        "topic": TEST_TOPIC,
        "keywords": ["health literacy", "chatbots", "LLM"],
        "domain": "public health",
        "scope": "Focus on health literacy chatbots",
        "research_question": "What is the effectiveness of health literacy chatbots?",
        "context": "Health literacy chatbots for improving health outcomes.",
    },
    "agents": {
        "search_agent": {
            "role": "Literature Search Specialist",
            "goal": "Find comprehensive literature",
            "backstory": "Expert researcher",
            "llm_model": "gemini-2.5-flash",
            "tools": ["database_search"],
            "temperature": 0.1,
            "max_iterations": 3,
        },
        "title_abstract_screener": {
            "role": "Title/Abstract Screening Specialist",
            "goal": "Screen papers for relevance by title/abstract",
            "backstory": "Meticulous reviewer",
            "llm_model": "gemini-2.5-flash-lite",
            "tools": ["title_screener"],
            "temperature": 0.2,
            "max_iterations": 10,
        },
        "fulltext_screener": {
            "role": "Fulltext Screening Specialist",
            "goal": "Screen papers for relevance by fulltext",
            "backstory": "Meticulous reviewer",
            "llm_model": "gemini-2.5-flash-lite",
            "tools": ["fulltext_screener"],
            "temperature": 0.2,
            "max_iterations": 5,
        },
        "extraction_agent": {
            "role": "Data Extraction Specialist",
            "goal": "Extract structured data",
            "backstory": "Detail-oriented analyst",
            "llm_model": "gemini-2.5-pro",
            "tools": ["data_extractor"],
            "temperature": 0.1,
            "max_iterations": 3,
        },
        "introduction_writer": {
            "role": "Introduction Writer",
            "goal": "Write introduction",
            "backstory": "Skilled academic writer",
            "llm_model": "gemini-2.5-pro",
            "tools": [],
            "temperature": 0.7,
            "max_iterations": 2,
        },
        "methods_writer": {
            "role": "Methods Writer",
            "goal": "Write methods section",
            "backstory": "Methodology expert",
            "llm_model": "gemini-2.5-pro",
            "tools": [],
            "temperature": 0.3,
            "max_iterations": 2,
        },
        "results_writer": {
            "role": "Results Writer",
            "goal": "Synthesize results",
            "backstory": "Data synthesis expert",
            "llm_model": "gemini-2.5-pro",
            "tools": [],
            "temperature": 0.4,
            "max_iterations": 2,
        },
        "discussion_writer": {
            "role": "Discussion Writer",
            "goal": "Write discussion",
            "backstory": "Critical analysis expert",
            "llm_model": "gemini-2.5-pro",
            "tools": [],
            "temperature": 0.6,
            "max_iterations": 2,
        },
    },
    "workflow": {
        "databases": ["PubMed", "arXiv", "Semantic Scholar", "Crossref"],
        "date_range": {"start": None, "end": 2025},
        "language": "English",
        "max_results_per_db": 20,  # Reasonable number for testing
        "similarity_threshold": 85,
        "database_settings": {
            "PubMed": {"enabled": True, "max_results": 20},
            "arXiv": {"enabled": True, "max_results": 20},
            "Semantic Scholar": {"enabled": True, "max_results": 20},
            "Crossref": {"enabled": True, "max_results": 20},
            "Scopus": {"enabled": False, "requires_api_key": True},
        },
        "cache": {"enabled": False},  # Disable cache for fresh testing
        "search_logging": {
            "enabled": True,
            "log_dir": "data/outputs/search_logs",
            "generate_prisma_report": True,
        },
    },
    "topic_context": {
        "topic": "Health Literacy Chatbots",
        "keywords": ["health literacy", "chatbot", "patient education"],
        "domain": "healthcare technology",
        "scope": "Focus on health literacy chatbots",
        "research_question": "How do health literacy chatbots improve patient understanding?",
        "context": "Health literacy chatbots are increasingly used in healthcare",
        "inclusion": [
            "Studies on health literacy chatbots",
            "Published in English",
        ],
        "exclusion": [
            "Non-chatbot interventions",
            "Non-peer-reviewed sources",
        ],
    },
    "output": {
        "directory": "data/outputs",
        "formats": ["markdown", "json"],
        "generate_prisma": True,
        "generate_charts": False,  # Disable for faster testing
    },
}


class WorkflowTester:
    """Test the complete workflow and validate outputs."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize tester."""
        self.config_path = config_path
        self.workflow_manager = None
        self.results = {}
        self.issues = []
        self.warnings = []

    def check_api_keys(self) -> Dict[str, bool]:
        """Check which API keys are configured."""
        return {
            "PUBMED_API_KEY": bool(os.getenv("PUBMED_API_KEY")),
            "PUBMED_EMAIL": bool(os.getenv("PUBMED_EMAIL")),
            "SEMANTIC_SCHOLAR_API_KEY": bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY")),
            "CROSSREF_EMAIL": bool(os.getenv("CROSSREF_EMAIL")),
            "SCOPUS_API_KEY": bool(os.getenv("SCOPUS_API_KEY")),
        }

    def create_test_config(self, output_dir: Path) -> str:
        """Create test config file."""
        import yaml
        
        config = TEST_CONFIG.copy()
        config["output"]["directory"] = str(output_dir)
        
        config_file = output_dir / "test_workflow.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)
        
        return str(config_file)

    def validate_search_phase(self) -> Tuple[bool, Dict]:
        """Validate search phase results."""
        console.print("\n[bold blue]Phase 1: Database Search[/bold blue]")
        
        try:
            self.workflow_manager._build_search_strategy()
            papers = self.workflow_manager._search_databases()
            self.workflow_manager.all_papers = papers
            
            # Quality metrics
            papers_with_titles = sum(1 for p in papers if p.title)
            papers_with_abstracts = sum(1 for p in papers if p.abstract)
            papers_with_authors = sum(1 for p in papers if p.authors)
            papers_with_doi = sum(1 for p in papers if p.doi)
            
            db_breakdown = self.workflow_manager._get_database_breakdown()
            
            metrics = {
                "total_papers": len(papers),
                "papers_with_titles": papers_with_titles,
                "papers_with_abstracts": papers_with_abstracts,
                "papers_with_authors": papers_with_authors,
                "papers_with_doi": papers_with_doi,
                "database_breakdown": db_breakdown,
            }
            
            # Validation checks
            if len(papers) == 0:
                self.issues.append("No papers found in search phase")
                return False, metrics
            
            if papers_with_titles / len(papers) < 0.8:
                self.warnings.append(
                    f"Low title coverage: {papers_with_titles}/{len(papers)} papers have titles"
                )
            
            console.print(f"  [green]Found {len(papers)} papers[/green]")
            console.print(f"  Titles: {papers_with_titles}/{len(papers)} ({papers_with_titles/len(papers)*100:.1f}%)")
            console.print(f"  Abstracts: {papers_with_abstracts}/{len(papers)} ({papers_with_abstracts/len(papers)*100:.1f}%)")
            console.print(f"  Authors: {papers_with_authors}/{len(papers)} ({papers_with_authors/len(papers)*100:.1f}%)")
            console.print(f"  DOI: {papers_with_doi}/{len(papers)} ({papers_with_doi/len(papers)*100:.1f}%)")
            
            return True, metrics
            
        except Exception as e:
            self.issues.append(f"Search phase failed: {e}")
            return False, {"error": str(e)}

    def validate_deduplication_phase(self) -> Tuple[bool, Dict]:
        """Validate deduplication phase."""
        console.print("\n[bold blue]Phase 2: Deduplication[/bold blue]")
        
        try:
            dedup_result = self.workflow_manager.deduplicator.deduplicate_papers(
                self.workflow_manager.all_papers
            )
            self.workflow_manager.unique_papers = dedup_result.unique_papers
            
            metrics = {
                "original_count": len(self.workflow_manager.all_papers),
                "unique_count": len(dedup_result.unique_papers),
                "duplicates_removed": dedup_result.duplicates_removed,
            }
            
            console.print(f"  [green]Removed {dedup_result.duplicates_removed} duplicates[/green]")
            console.print(f"  Unique papers: {len(dedup_result.unique_papers)}")
            
            return True, metrics
            
        except Exception as e:
            self.issues.append(f"Deduplication phase failed: {e}")
            return False, {"error": str(e)}

    def validate_screening_phase(self) -> Tuple[bool, Dict]:
        """Validate screening phase."""
        console.print("\n[bold blue]Phase 3: Title/Abstract Screening[/bold blue]")
        
        try:
            # Limit to first 10 for faster testing
            len(self.workflow_manager.unique_papers)
            self.workflow_manager.unique_papers = self.workflow_manager.unique_papers[:10]
            
            self.workflow_manager._screen_title_abstract()
            
            metrics = {
                "screened_count": len(self.workflow_manager.unique_papers),
                "included_count": len(self.workflow_manager.screened_papers),
                "excluded_count": len(self.workflow_manager.unique_papers) - len(self.workflow_manager.screened_papers),
            }
            
            console.print(f"  [green]Screened {metrics['screened_count']} papers[/green]")
            console.print(f"  Included: {metrics['included_count']}")
            console.print(f"  Excluded: {metrics['excluded_count']}")
            
            return True, metrics
            
        except Exception as e:
            self.warnings.append(f"Screening phase failed (may need LLM API): {e}")
            return False, {"error": str(e)}

    def validate_prisma_generation(self) -> Tuple[bool, Dict]:
        """Validate PRISMA diagram generation."""
        console.print("\n[bold blue]Phase 4: PRISMA Diagram Generation[/bold blue]")
        
        try:
            # Update PRISMA counter
            self.workflow_manager.prisma_counter.set_found(
                len(self.workflow_manager.all_papers),
                self.workflow_manager._get_database_breakdown()
            )
            self.workflow_manager.prisma_counter.set_no_dupes(
                len(self.workflow_manager.unique_papers)
            )
            
            prisma_path = self.workflow_manager._generate_prisma_diagram()
            
            if not prisma_path or not Path(prisma_path).exists():
                self.issues.append("PRISMA diagram file not created")
                return False, {"error": "PRISMA diagram not created"}
            
            file_size = Path(prisma_path).stat().st_size
            
            metrics = {
                "prisma_path": prisma_path,
                "file_size": file_size,
                "counts": self.workflow_manager.prisma_counter.get_counts(),
            }
            
            console.print("  [green]PRISMA diagram generated[/green]")
            console.print(f"  Path: {prisma_path}")
            console.print(f"  Size: {file_size} bytes")
            
            return True, metrics
            
        except Exception as e:
            self.issues.append(f"PRISMA generation failed: {e}")
            return False, {"error": str(e)}

    def run_full_workflow_test(self) -> bool:
        """Run complete workflow test."""
        console.print(Panel.fit("[bold]End-to-End Workflow Test[/bold]", border_style="blue"))
        
        # Check API keys
        api_keys = self.check_api_keys()
        console.print("\n[bold]API Key Configuration:[/bold]")
        for key, is_set in api_keys.items():
            status = "[green]SET[/green]" if is_set else "[yellow]NOT SET[/yellow]"
            console.print(f"  {key}: {status}")
        
        # Create test config
        output_dir = Path("data/outputs/test_workflow")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = self.create_test_config(output_dir)
        self.workflow_manager = WorkflowManager(config_file)
        self.workflow_manager.output_dir = output_dir
        
        # Run phases
        start_time = time.time()
        
        # Phase 1: Search
        success, search_metrics = self.validate_search_phase()
        self.results["search"] = search_metrics
        if not success:
            console.print("[red]Search phase failed, stopping test[/red]")
            return False
        
        # Phase 2: Deduplication
        success, dedup_metrics = self.validate_deduplication_phase()
        self.results["deduplication"] = dedup_metrics
        if not success:
            console.print("[red]Deduplication phase failed[/red]")
        
        # Phase 3: Screening (optional, may fail if no LLM API)
        success, screen_metrics = self.validate_screening_phase()
        self.results["screening"] = screen_metrics
        
        # Phase 4: PRISMA
        success, prisma_metrics = self.validate_prisma_generation()
        self.results["prisma"] = prisma_metrics
        
        duration = time.time() - start_time
        
        # Print summary
        self.print_summary(duration)
        
        return len(self.issues) == 0

    def print_summary(self, duration: float):
        """Print test summary."""
        console.print("\n" + "=" * 60)
        console.print("[bold]Test Summary[/bold]")
        console.print("=" * 60)
        
        # Results table
        table = Table(title="Phase Results")
        table.add_column("Phase", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")
        
        for phase, metrics in self.results.items():
            if "error" in metrics:
                status = "[red]FAILED[/red]"
                details = metrics["error"]
            else:
                status = "[green]PASSED[/green]"
                if phase == "search":
                    details = f"{metrics.get('total_papers', 0)} papers found"
                elif phase == "deduplication":
                    details = f"{metrics.get('duplicates_removed', 0)} duplicates removed"
                elif phase == "screening":
                    details = f"{metrics.get('included_count', 0)} included"
                elif phase == "prisma":
                    details = f"Diagram generated ({metrics.get('file_size', 0)} bytes)"
                else:
                    details = "Completed"
            
            table.add_row(phase.title(), status, details)
        
        console.print(table)
        
        # Issues and warnings
        if self.issues:
            console.print("\n[bold red]Issues Found:[/bold red]")
            for issue in self.issues:
                console.print(f"  - {issue}")
        
        if self.warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in self.warnings:
                console.print(f"  - {warning}")
        
        console.print(f"\n[bold]Duration:[/bold] {duration:.2f} seconds")
        
        # Save results
        results_file = Path("data/outputs/test_workflow/results.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, "w") as f:
            json.dump({
                "results": self.results,
                "issues": self.issues,
                "warnings": self.warnings,
                "duration": duration,
            }, f, indent=2)
        
        console.print(f"\n[bold]Results saved to:[/bold] {results_file}")


def main():
    """Main entry point."""
    tester = WorkflowTester()
    success = tester.run_full_workflow_test()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
