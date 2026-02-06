#!/usr/bin/env python3
"""
[Recurring Usage Script] PRISMA 2020 Test Runner

Test runner for PRISMA 2020 tests.
Generates reports and tracks test execution.
Used by: make test-prisma
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

console = Console()

# Test files to run
PRISMA_TEST_FILES = [
    "tests/unit/test_prisma_validator.py",
    "tests/unit/test_prisma_checklist_generator.py",
    "tests/unit/test_extraction_form_generator.py",
    "tests/unit/test_quality_visualizations.py",
    "tests/unit/test_abstract_agent.py",
    "tests/unit/test_writing_agents.py",
    "tests/integration/test_prisma_checklist_generation.py",
    "tests/integration/test_search_strategy_export.py",
]

# Test output directory
OUTPUT_DIR = Path("data/test_outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_tests():
    """Run all PRISMA 2020 tests and generate reports."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Output files
    json_output = OUTPUT_DIR / f"test_results_{timestamp}.json"
    txt_output = OUTPUT_DIR / f"test_results_{timestamp}.txt"
    html_output = OUTPUT_DIR / f"test_results_{timestamp}.html"
    latest_json = OUTPUT_DIR / "latest_results.json"
    
    console.print(Panel.fit("[bold blue]Running PRISMA 2020 Tests[/bold blue]"))
    console.print(f"Output directory: {OUTPUT_DIR}")
    console.print(f"Timestamp: {timestamp}\n")
    
    # Build pytest arguments
    pytest_args = [
        *PRISMA_TEST_FILES,
        "-v",
        "--tb=short",
    ]
    
    # Try to add HTML report if pytest-html is available
    import importlib.util
    if importlib.util.find_spec("pytest_html") is not None:
        pytest_args.extend([
            f"--html={html_output}",
            "--self-contained-html",
        ])
        console.print("[green]HTML report enabled[/green]")
    else:
        console.print("[yellow]pytest-html not available, skipping HTML report[/yellow]")
    
    # Capture output for parsing
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest"] + pytest_args,
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # Parse output to extract test results
    output_lines = result.stdout.split("\n")
    test_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "error": 0,
        "tests": [],
    }
    
    # Parse pytest output
    for line in output_lines:
        if "PASSED" in line:
            test_results["passed"] += 1
            test_results["total"] += 1
        elif "FAILED" in line:
            test_results["failed"] += 1
            test_results["total"] += 1
        elif "SKIPPED" in line or "SKIP" in line:
            test_results["skipped"] += 1
            test_results["total"] += 1
        elif "ERROR" in line:
            test_results["error"] += 1
            test_results["total"] += 1
    
    # Save parsed results to JSON
    results = {
        "summary": test_results,
        "exit_code": result.returncode,
        "timestamp": timestamp,
        "duration": None,  # Will be set after
    }
    
    # Run tests and capture output
    start_time = datetime.now()
    
    # Capture output for parsing
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest"] + pytest_args,
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    exit_code = result.returncode
    
    # Parse output to extract test results
    output_lines = result.stdout.split("\n")
    test_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "error": 0,
        "tests": [],
    }
    
    # Parse pytest output
    for line in output_lines:
        if "PASSED" in line:
            test_results["passed"] += 1
            test_results["total"] += 1
        elif "FAILED" in line:
            test_results["failed"] += 1
            test_results["total"] += 1
        elif "SKIPPED" in line or "SKIP" in line:
            test_results["skipped"] += 1
            test_results["total"] += 1
        elif "ERROR" in line:
            test_results["error"] += 1
            test_results["total"] += 1
    
    # Save parsed results to JSON
    results = {
        "summary": test_results,
        "exit_code": exit_code,
        "timestamp": timestamp,
        "duration": duration,
        "output": result.stdout,
        "errors": result.stderr,
    }
    
    # Save JSON results
    with open(json_output, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate summary
    summary = generate_summary(results, duration, exit_code)
    
    # Save text summary
    with open(txt_output, "w") as f:
        f.write(summary)
    
    # Create symlink to latest results
    if latest_json.exists():
        latest_json.unlink()
    try:
        latest_json.symlink_to(json_output.name)
    except Exception:
        # Symlinks may not work on all systems, just copy instead
        import shutil
        shutil.copy(json_output, latest_json)
    
    # Display summary
    console.print("\n" + "=" * 70)
    console.print(Panel(summary, title="[bold green]Test Summary[/bold green]"))
    console.print("=" * 70)
    console.print("\n[bold]Results saved to:[/bold]")
    console.print(f"  JSON: {json_output}")
    console.print(f"  TXT:  {txt_output}")
    if html_output.exists():
        console.print(f"  HTML: {html_output}")
    console.print(f"  Latest: {latest_json}\n")
    
    return exit_code == 0


def generate_summary(results: dict, duration: float, exit_code: int) -> str:
    """Generate human-readable test summary."""
    lines = []
    lines.append("Test Execution Summary")
    lines.append(f"{'=' * 70}")
    lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Duration: {duration:.2f} seconds")
    lines.append(f"Exit Code: {exit_code}")
    lines.append("")
    
    # Extract test statistics
    if "summary" in results:
        summary = results["summary"]
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        error = summary.get("error", 0)
        
        lines.append(f"Total Tests: {total}")
        lines.append(f"  Passed:  {passed}")
        lines.append(f"  Failed:  {failed}")
        lines.append(f"  Skipped: {skipped}")
        lines.append(f"  Error:   {error}")
        lines.append("")
        
        # Test files
        if "collectors" in results:
            lines.append("Test Files:")
            for collector in results["collectors"]:
                if collector.get("nodeid"):
                    lines.append(f"  - {collector['nodeid']}")
            lines.append("")
        
        # Failed tests
        if failed > 0 or error > 0:
            lines.append("Failed Tests:")
            if "tests" in results:
                for test in results["tests"]:
                    if test.get("outcome") in ["failed", "error"]:
                        lines.append(f"  - {test.get('nodeid', 'Unknown')}")
                        if "call" in test and "longrepr" in test["call"]:
                            error_msg = test["call"]["longrepr"].split("\n")[0]
                            lines.append(f"    {error_msg}")
            lines.append("")
    else:
        # Fallback if JSON structure is different
        lines.append("Could not parse detailed results from JSON report.")
        lines.append(f"Exit code indicates: {'SUCCESS' if exit_code == 0 else 'FAILURE'}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    success = run_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
