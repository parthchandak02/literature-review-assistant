#!/usr/bin/env python3
"""
[Recurring Usage Script] Test Status Checker

Quick test status check without running full tests.
Used by: make test-status
"""
"""
Quick status check for PRISMA 2020 tests.
Shows last test run timestamp and pass/fail counts without running tests.
"""

import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

OUTPUT_DIR = Path("data/test_outputs")
LATEST_RESULTS = OUTPUT_DIR / "latest_results.json"


def check_status():
    """Check test status from latest results."""
    console.print(Panel.fit("[bold blue]PRISMA 2020 Test Status[/bold blue]"))
    
    if not LATEST_RESULTS.exists():
        console.print("[yellow]No test results found. Run tests first with:[/yellow]")
        console.print("  [cyan]python scripts/run_prisma_tests.py[/cyan]\n")
        return False
    
    try:
        with open(LATEST_RESULTS, "r") as f:
            results = json.load(f)
    except Exception as e:
        console.print(f"[red]Error reading results: {e}[/red]\n")
        return False
    
    # Display summary
    summary = results.get("summary", {})
    timestamp = results.get("timestamp", "Unknown")
    duration = results.get("duration", 0)
    exit_code = results.get("exit_code", 1)
    
    # Format timestamp
    try:
        dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        formatted_time = timestamp
    
    # Create status table
    table = Table(title="Test Results Summary", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Last Run", formatted_time)
    table.add_row("Duration", f"{duration:.2f}s" if duration else "N/A")
    table.add_row("Status", "[green]PASSED[/green]" if exit_code == 0 else "[red]FAILED[/red]")
    table.add_row("", "")  # Separator
    
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    error = summary.get("error", 0)
    
    table.add_row("Total Tests", str(total))
    table.add_row("Passed", f"[green]{passed}[/green]")
    table.add_row("Failed", f"[red]{failed}[/red]" if failed > 0 else "[green]0[/green]")
    table.add_row("Skipped", f"[yellow]{skipped}[/yellow]" if skipped > 0 else "0")
    table.add_row("Errors", f"[red]{error}[/red]" if error > 0 else "0")
    
    if total > 0:
        pass_rate = (passed / total) * 100
        table.add_row("", "")  # Separator
        table.add_row("Pass Rate", f"{pass_rate:.1f}%")
    
    console.print(table)
    console.print()
    
    # Show failed tests if any
    if failed > 0 or error > 0:
        console.print("[yellow]Failed Tests:[/yellow]")
        if "output" in results:
            output_lines = results["output"].split("\n")
            for line in output_lines:
                if "FAILED" in line or "ERROR" in line:
                    console.print(f"  [red]{line}[/red]")
        console.print()
    
    # Recommendations
    if exit_code == 0:
        console.print("[green]All tests passed![/green]\n")
    else:
        console.print("[yellow]Some tests failed. Run full test suite for details:[/yellow]")
        console.print("  [cyan]python scripts/run_prisma_tests.py[/cyan]\n")
    
    return exit_code == 0


def main():
    """Main entry point."""
    success = check_status()
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
