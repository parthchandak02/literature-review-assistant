#!/usr/bin/env python3
"""
Workflow Output Validation Script

Validates outputs from the research paper generation workflow:
- Validates papers have required fields
- Validates PRISMA diagram exists and is correct
- Validates article sections are complete
- Validates final report contains all sections
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from PIL import Image

# Load environment variables
load_dotenv()

console = Console()


class WorkflowOutputValidator:
    """Validate workflow outputs."""

    def __init__(self, output_dir: str = "data/outputs"):
        """Initialize validator."""
        self.output_dir = Path(output_dir)
        self.issues = []
        self.warnings = []
        self.validated = {}

    def validate_papers(self, papers_file: Optional[str] = None) -> Tuple[bool, Dict]:
        """Validate papers JSON file."""
        console.print("\n[bold blue]Validating Papers[/bold blue]")
        
        if papers_file is None:
            # Look for papers file
            papers_files = list(self.output_dir.glob("*papers*.json"))
            if not papers_files:
                self.warnings.append("No papers JSON file found")
                return False, {"error": "Papers file not found"}
            papers_file = papers_files[0]
        else:
            papers_file = Path(papers_file)
        
        if not papers_file.exists():
            self.issues.append(f"Papers file not found: {papers_file}")
            return False, {"error": "Papers file not found"}
        
        try:
            with open(papers_file, "r") as f:
                papers_data = json.load(f)
            
            if not isinstance(papers_data, list):
                self.issues.append("Papers file should contain a list")
                return False, {"error": "Invalid format"}
            
            metrics = {
                "total_papers": len(papers_data),
                "papers_with_titles": 0,
                "papers_with_abstracts": 0,
                "papers_with_authors": 0,
                "papers_with_doi": 0,
                "papers_with_year": 0,
                "issues": [],
            }
            
            for i, paper in enumerate(papers_data):
                if not isinstance(paper, dict):
                    metrics["issues"].append(f"Paper {i}: Not a dictionary")
                    continue
                
                if paper.get("title"):
                    metrics["papers_with_titles"] += 1
                else:
                    metrics["issues"].append(f"Paper {i}: Missing title")
                
                if paper.get("abstract"):
                    metrics["papers_with_abstracts"] += 1
                
                if paper.get("authors") and len(paper["authors"]) > 0:
                    metrics["papers_with_authors"] += 1
                
                if paper.get("doi"):
                    metrics["papers_with_doi"] += 1
                
                if paper.get("year"):
                    metrics["papers_with_year"] += 1
            
            # Validation checks
            if metrics["papers_with_titles"] / len(papers_data) < 0.9:
                self.issues.append(
                    f"Low title coverage: {metrics['papers_with_titles']}/{metrics['total_papers']}"
                )
            
            console.print(f"  Total papers: {metrics['total_papers']}")
            console.print(f"  With titles: {metrics['papers_with_titles']}/{metrics['total_papers']}")
            console.print(f"  With abstracts: {metrics['papers_with_abstracts']}/{metrics['total_papers']}")
            console.print(f"  With authors: {metrics['papers_with_authors']}/{metrics['total_papers']}")
            console.print(f"  With DOI: {metrics['papers_with_doi']}/{metrics['total_papers']}")
            
            if metrics["issues"]:
                console.print(f"  [yellow]Issues: {len(metrics['issues'])}[/yellow]")
            
            self.validated["papers"] = metrics
            return len(metrics["issues"]) == 0, metrics
            
        except json.JSONDecodeError as e:
            self.issues.append(f"Invalid JSON in papers file: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            self.issues.append(f"Error validating papers: {e}")
            return False, {"error": str(e)}

    def validate_prisma_diagram(self, prisma_file: Optional[str] = None) -> Tuple[bool, Dict]:
        """Validate PRISMA diagram."""
        console.print("\n[bold blue]Validating PRISMA Diagram[/bold blue]")
        
        if prisma_file is None:
            # Look for PRISMA diagram
            prisma_files = list(self.output_dir.glob("*prisma*.png"))
            if not prisma_files:
                self.warnings.append("No PRISMA diagram found")
                return False, {"error": "PRISMA diagram not found"}
            prisma_file = prisma_files[0]
        else:
            prisma_file = Path(prisma_file)
        
        if not prisma_file.exists():
            self.issues.append(f"PRISMA diagram not found: {prisma_file}")
            return False, {"error": "PRISMA diagram not found"}
        
        try:
            # Validate image
            img = Image.open(prisma_file)
            
            metrics = {
                "path": str(prisma_file),
                "format": img.format,
                "width": img.size[0],
                "height": img.size[1],
                "file_size": prisma_file.stat().st_size,
            }
            
            # Validation checks
            if img.format != "PNG":
                self.warnings.append(f"PRISMA diagram should be PNG, got {img.format}")
            
            if metrics["width"] < 800:
                self.warnings.append(f"PRISMA diagram width should be >= 800px, got {metrics['width']}")
            
            if metrics["file_size"] < 1000:
                self.warnings.append(f"PRISMA diagram file size seems small: {metrics['file_size']} bytes")
            
            if metrics["file_size"] > 10 * 1024 * 1024:
                self.warnings.append(f"PRISMA diagram file size seems large: {metrics['file_size']} bytes")
            
            console.print(f"  Path: {metrics['path']}")
            console.print(f"  Format: {metrics['format']}")
            console.print(f"  Dimensions: {metrics['width']}x{metrics['height']}")
            console.print(f"  File size: {metrics['file_size']} bytes")
            
            self.validated["prisma"] = metrics
            return True, metrics
            
        except Exception as e:
            self.issues.append(f"Error validating PRISMA diagram: {e}")
            return False, {"error": str(e)}

    def validate_article_sections(self, sections_dir: Optional[str] = None) -> Tuple[bool, Dict]:
        """Validate article sections."""
        console.print("\n[bold blue]Validating Article Sections[/bold blue]")
        
        if sections_dir is None:
            sections_dir = self.output_dir
        else:
            sections_dir = Path(sections_dir)
        
        expected_sections = [
            "introduction",
            "methods",
            "results",
            "discussion",
        ]
        
        metrics = {
            "sections_found": [],
            "sections_missing": [],
            "sections_with_content": [],
            "total_content_length": 0,
        }
        
        for section in expected_sections:
            # Look for section files
            section_files = list(sections_dir.glob(f"*{section}*.md"))
            section_files.extend(list(sections_dir.glob(f"*{section}*.txt")))
            
            if section_files:
                metrics["sections_found"].append(section)
                # Check content
                section_file = section_files[0]
                content = section_file.read_text()
                content_length = len(content.strip())
                metrics["total_content_length"] += content_length
                
                if content_length > 100:
                    metrics["sections_with_content"].append(section)
                else:
                    self.warnings.append(f"Section '{section}' has very little content ({content_length} chars)")
            else:
                metrics["sections_missing"].append(section)
                self.warnings.append(f"Section '{section}' not found")
        
        console.print(f"  Sections found: {len(metrics['sections_found'])}/{len(expected_sections)}")
        console.print(f"  Sections with content: {len(metrics['sections_with_content'])}")
        console.print(f"  Total content length: {metrics['total_content_length']} characters")
        
        if metrics["sections_missing"]:
            console.print(f"  [yellow]Missing: {', '.join(metrics['sections_missing'])}[/yellow]")
        
        self.validated["article_sections"] = metrics
        return len(metrics["sections_missing"]) == 0, metrics

    def validate_final_report(self, report_file: Optional[str] = None) -> Tuple[bool, Dict]:
        """Validate final report."""
        console.print("\n[bold blue]Validating Final Report[/bold blue]")
        
        if report_file is None:
            # Look for final report
            report_files = list(self.output_dir.glob("*final_report*.md"))
            report_files.extend(list(self.output_dir.glob("*report*.md")))
            if not report_files:
                self.warnings.append("No final report found")
                return False, {"error": "Final report not found"}
            report_file = report_files[0]
        else:
            report_file = Path(report_file)
        
        if not report_file.exists():
            self.issues.append(f"Final report not found: {report_file}")
            return False, {"error": "Final report not found"}
        
        try:
            content = report_file.read_text()
            
            expected_sections = [
                "# Introduction",
                "# Methods",
                "# Results",
                "# Discussion",
                "PRISMA",
            ]
            
            metrics = {
                "path": str(report_file),
                "file_size": report_file.stat().st_size,
                "content_length": len(content),
                "sections_found": [],
                "sections_missing": [],
                "has_prisma_reference": False,
            }
            
            # Check for section headers
            content_lower = content.lower()
            for section in expected_sections:
                section_lower = section.lower()
                if section_lower in content_lower or section_lower.replace("# ", "") in content_lower:
                    metrics["sections_found"].append(section)
                else:
                    metrics["sections_missing"].append(section)
                    self.warnings.append(f"Section '{section}' not found in report")
            
            # Check for PRISMA reference
            if "prisma" in content_lower or "prisma_diagram" in content_lower:
                metrics["has_prisma_reference"] = True
            
            console.print(f"  Path: {metrics['path']}")
            console.print(f"  File size: {metrics['file_size']} bytes")
            console.print(f"  Content length: {metrics['content_length']} characters")
            console.print(f"  Sections found: {len(metrics['sections_found'])}/{len(expected_sections)}")
            console.print(f"  Has PRISMA reference: {metrics['has_prisma_reference']}")
            
            if metrics["sections_missing"]:
                console.print(f"  [yellow]Missing sections: {', '.join(metrics['sections_missing'])}[/yellow]")
            
            # Validation checks
            if metrics["content_length"] < 1000:
                self.warnings.append(f"Final report seems short: {metrics['content_length']} characters")
            
            if not metrics["has_prisma_reference"]:
                self.warnings.append("Final report should reference PRISMA diagram")
            
            self.validated["final_report"] = metrics
            return len(metrics["sections_missing"]) == 0, metrics
            
        except Exception as e:
            self.issues.append(f"Error validating final report: {e}")
            return False, {"error": str(e)}

    def validate_workflow_state(self, state_file: Optional[str] = None) -> Tuple[bool, Dict]:
        """Validate workflow state file."""
        console.print("\n[bold blue]Validating Workflow State[/bold blue]")
        
        if state_file is None:
            state_files = list(self.output_dir.glob("*workflow_state*.json"))
            if not state_files:
                self.warnings.append("No workflow state file found")
                return False, {"error": "Workflow state not found"}
            state_file = state_files[0]
        else:
            state_file = Path(state_file)
        
        if not state_file.exists():
            self.warnings.append(f"Workflow state file not found: {state_file}")
            return False, {"error": "Workflow state not found"}
        
        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
            
            metrics = {
                "path": str(state_file),
                "has_prisma_counts": "prisma_counts" in state_data,
                "has_papers": "papers" in state_data or "all_papers" in state_data,
                "has_phase": "phase" in state_data,
            }
            
            console.print(f"  Path: {metrics['path']}")
            console.print(f"  Has PRISMA counts: {metrics['has_prisma_counts']}")
            console.print(f"  Has papers: {metrics['has_papers']}")
            console.print(f"  Has phase: {metrics['has_phase']}")
            
            self.validated["workflow_state"] = metrics
            return True, metrics
            
        except Exception as e:
            self.warnings.append(f"Error validating workflow state: {e}")
            return False, {"error": str(e)}

    def run_all_validations(self) -> bool:
        """Run all validations."""
        console.print(Panel.fit("[bold]Workflow Output Validation[/bold]", border_style="blue"))
        console.print(f"\nValidating outputs in: {self.output_dir}")
        
        if not self.output_dir.exists():
            console.print(f"[red]Output directory does not exist: {self.output_dir}[/red]")
            return False
        
        # Run all validations
        self.validate_papers()
        self.validate_prisma_diagram()
        self.validate_article_sections()
        self.validate_final_report()
        self.validate_workflow_state()
        
        # Print summary
        self.print_summary()
        
        return len(self.issues) == 0

    def print_summary(self):
        """Print validation summary."""
        console.print("\n" + "=" * 60)
        console.print("[bold]Validation Summary[/bold]")
        console.print("=" * 60)
        
        # Results table
        table = Table(title="Validation Results")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")
        
        for component, metrics in self.validated.items():
            if "error" in metrics:
                status = "[red]FAILED[/red]"
                details = metrics["error"]
            else:
                status = "[green]PASSED[/green]"
                if component == "papers":
                    details = f"{metrics.get('total_papers', 0)} papers"
                elif component == "prisma":
                    details = f"{metrics.get('format', 'unknown')} {metrics.get('width', 0)}x{metrics.get('height', 0)}"
                elif component == "article_sections":
                    details = f"{len(metrics.get('sections_found', []))} sections"
                elif component == "final_report":
                    details = f"{metrics.get('content_length', 0)} chars"
                else:
                    details = "Validated"
            
            table.add_row(component.replace("_", " ").title(), status, details)
        
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
        
        # Overall status
        if len(self.issues) == 0:
            console.print("\n[bold green]All validations passed![/bold green]")
        else:
            console.print(f"\n[bold red]{len(self.issues)} issue(s) found[/bold red]")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate workflow outputs")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/outputs",
        help="Output directory to validate",
    )
    parser.add_argument(
        "--papers",
        type=str,
        help="Path to papers JSON file",
    )
    parser.add_argument(
        "--prisma",
        type=str,
        help="Path to PRISMA diagram",
    )
    parser.add_argument(
        "--report",
        type=str,
        help="Path to final report",
    )
    
    args = parser.parse_args()
    
    validator = WorkflowOutputValidator(output_dir=args.output_dir)
    success = validator.run_all_validations()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
