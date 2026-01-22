#!/usr/bin/env python3
"""
[Utility Script] Workflow Progress Checker

Check workflow progress and verify PRISMA 2020 outputs are being generated correctly.
Can be run while workflow is executing or after completion.
"""

import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def find_workflow_outputs():
    """Find all workflow output directories."""
    output_base = Path("data/outputs")
    if not output_base.exists():
        return []
    
    workflow_dirs = []
    for item in output_base.iterdir():
        if item.is_dir():
            # Check if it contains workflow outputs
            if (item / "workflow_state.json").exists() or (item / "final_report.md").exists():
                workflow_dirs.append(item)
    
    # Sort by modification time (newest first)
    return sorted(workflow_dirs, key=lambda p: p.stat().st_mtime, reverse=True)

def check_checkpoints():
    """Check for workflow checkpoints."""
    checkpoint_base = Path("data/checkpoints")
    if not checkpoint_base.exists():
        return []
    
    checkpoints = []
    for workflow_dir in checkpoint_base.iterdir():
        if workflow_dir.is_dir():
            checkpoint_files = list(workflow_dir.glob("*.json"))
            if checkpoint_files:
                checkpoints.append({
                    "workflow_id": workflow_dir.name,
                    "checkpoints": sorted(checkpoint_files, key=lambda p: p.stat().st_mtime, reverse=True)
                })
    
    return sorted(checkpoints, key=lambda x: x["checkpoints"][0].stat().st_mtime if x["checkpoints"] else 0, reverse=True)

def analyze_workflow_state(workflow_dir: Path):
    """Analyze workflow state to determine progress."""
    state_file = workflow_dir / "workflow_state.json"
    if not state_file.exists():
        return None
    
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        
        prisma_counts = state.get("prisma_counts", {})
        
        return {
            "topic": state.get("topic_context", {}).get("topic", "Unknown"),
            "workflow_id": workflow_dir.name,
            "papers_found": prisma_counts.get("found", 0),
            "unique_papers": prisma_counts.get("no_dupes", 0),
            "screened": prisma_counts.get("screened", 0),
            "full_text_assessed": prisma_counts.get("full_text_assessed", 0),
            "final_included": prisma_counts.get("quantitative", 0),
            "last_modified": datetime.fromtimestamp(state_file.stat().st_mtime),
        }
    except Exception as e:
        console.print(f"[red]Error reading state: {e}[/red]")
        return None

def check_phase_completion(workflow_dir: Path):
    """Check which phases have completed based on outputs."""
    phases = {
        "Search": workflow_dir / "workflow_state.json",
        "Deduplication": workflow_dir / "workflow_state.json",  # Same file
        "Screening": workflow_dir / "workflow_state.json",  # Same file
        "Data Extraction": workflow_dir / "workflow_state.json",  # Same file
        "PRISMA Diagram": workflow_dir / "prisma_diagram.png",
        "Visualizations": list(workflow_dir.glob("*.png")),
        "Article Writing": workflow_dir / "final_report.md",
        "PRISMA Checklist": workflow_dir / "prisma_checklist.json",
        "Search Strategies": workflow_dir / "search_strategies.md",
        "Extraction Form": workflow_dir.glob("extraction_form.*"),
    }
    
    completed = []
    in_progress = []
    pending = []
    
    for phase_name, check_path in phases.items():
        if isinstance(check_path, list):
            # Multiple files expected
            files = list(check_path)
            if files:
                completed.append(phase_name)
            else:
                pending.append(phase_name)
        elif isinstance(check_path, Path):
            if check_path.exists():
                completed.append(phase_name)
            else:
                # Check if workflow state exists (means workflow started)
                if (workflow_dir / "workflow_state.json").exists():
                    pending.append(phase_name)
                else:
                    pending.append(phase_name)
    
    return {
        "completed": completed,
        "pending": pending,
        "total_phases": len(phases)
    }

def verify_prisma_features(report_path: Path):
    """Verify PRISMA 2020 features in the report."""
    if not report_path.exists():
        return None
    
    content = report_path.read_text()
    
    checks = {
        "PRISMA 2020 Abstract (12 elements)": any(marker in content for marker in [
            "Background:", "Objectives:", "Eligibility criteria:", "Information sources:",
            "Risk of bias:", "Synthesis methods:", "Results:", "Limitations:",
            "Interpretation:", "Funding:", "Registration:"
        ]),
        "Explicit Objectives Paragraph": "objectives" in content.lower() and ("bullet" in content.lower() or "•" in content or "-" in content[:2000]),
        "Full Search Strategies": any(db in content for db in ["PubMed", "Scopus", "Embase", "Web of Science"]),
        "Study Characteristics Table": "study characteristics" in content.lower() or "table" in content.lower(),
        "Limitations Split": "limitations of the evidence" in content.lower() or "limitations of the review" in content.lower(),
        "PRISMA Diagram Reference": "prisma" in content.lower() and "diagram" in content.lower(),
    }
    
    return checks

def main():
    """Main function."""
    console.print(Panel.fit("[bold blue]Workflow Progress Checker[/bold blue]"))
    
    # Check for checkpoints (active workflows)
    checkpoints = check_checkpoints()
    if checkpoints:
        console.print(f"[green]Found {len(checkpoints)} workflow(s) with checkpoints[/green]")
        for cp in checkpoints[:3]:  # Show top 3
            latest = cp["checkpoints"][0] if cp["checkpoints"] else None
            if latest:
                mod_time = datetime.fromtimestamp(latest.stat().st_mtime)
                console.print(f"  - {cp['workflow_id']}: Last checkpoint at {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        console.print()
    
    # Find workflow outputs
    workflow_dirs = find_workflow_outputs()
    if not workflow_dirs:
        console.print("[yellow]No workflow outputs found yet.[/yellow]")
        console.print("The workflow may still be running or hasn't generated outputs yet.")
        return False
    
    # Analyze latest workflow
    latest_dir = workflow_dirs[0]
    console.print(f"[bold]Latest Workflow Output:[/bold] {latest_dir.name}\n")
    
    state_info = analyze_workflow_state(latest_dir)
    if state_info:
        table = Table(title="Workflow Progress", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Topic", state_info["topic"])
        table.add_row("Papers Found", str(state_info["papers_found"]))
        table.add_row("Unique Papers", str(state_info["unique_papers"]))
        table.add_row("Screened", str(state_info["screened"]))
        table.add_row("Full-text Assessed", str(state_info["full_text_assessed"]))
        table.add_row("Final Included", str(state_info["final_included"]))
        table.add_row("Last Modified", state_info["last_modified"].strftime("%Y-%m-%d %H:%M:%S"))
        
        console.print(table)
        console.print()
    
    # Check phase completion
    phases = check_phase_completion(latest_dir)
    console.print("[bold]Phase Completion Status:[/bold]")
    
    phase_table = Table(show_header=True, header_style="bold")
    phase_table.add_column("Phase", style="cyan")
    phase_table.add_column("Status", style="green")
    
    all_phases = set(phases["completed"] + phases["pending"])
    for phase in sorted(all_phases):
        if phase in phases["completed"]:
            status = "[green]COMPLETE[/green]"
        else:
            status = "[yellow]PENDING[/yellow]"
        phase_table.add_row(phase, status)
    
    console.print(phase_table)
    console.print(f"\nProgress: {len(phases['completed'])}/{phases['total_phases']} phases complete")
    console.print()
    
    # Check PRISMA features if report exists
    report_path = latest_dir / "final_report.md"
    if report_path.exists():
        console.print("[bold]PRISMA 2020 Features Check:[/bold]")
        features = verify_prisma_features(report_path)
        
        if features:
            feature_table = Table(show_header=True, header_style="bold")
            feature_table.add_column("Feature", style="cyan")
            feature_table.add_column("Status", style="green")
            
            for feature, present in features.items():
                status = "[green]PRESENT[/green]" if present else "[red]MISSING[/red]"
                feature_table.add_row(feature, status)
            
            console.print(feature_table)
            console.print()
            
            # PRISMA compliance check
            try:
                from src.validation.prisma_validator import PRISMAValidator
                validator = PRISMAValidator()
                result = validator.validate_report(str(report_path))
                
                console.print("[bold]PRISMA 2020 Compliance:[/bold]")
                console.print(f"  Compliant: {'[green]YES[/green]' if result.get('is_compliant') else '[red]NO[/red]'}")
                console.print(f"  Score: {result.get('compliance_score', 0):.1f}%")
                console.print(f"  Checklist Items: {result.get('items_present', 0)}/{result.get('items_total', 27)}")
                console.print(f"  Abstract Elements: {result.get('abstract_elements_present', 0)}/{result.get('abstract_elements_total', 12)}")
            except Exception as e:
                console.print(f"[yellow]Could not validate compliance: {e}[/yellow]")
    
    # Summary
    is_complete = len(phases["completed"]) == phases["total_phases"]
    status_color = "green" if is_complete else "yellow"
    status_text = "COMPLETE" if is_complete else "IN PROGRESS"
    
    console.print()
    console.print(Panel.fit(
        f"[{status_color}]{status_text}[/{status_color}]",
        title="[bold]Workflow Status[/bold]"
    ))
    
    return is_complete

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
