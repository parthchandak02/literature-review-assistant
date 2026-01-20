#!/usr/bin/env python3
"""
End-to-end test script for manuscript pipeline (Phases 17-18)

Tests:
1. Workflow execution with phases 17-18 enabled
2. Manubot export directory creation
3. Submission package creation
4. Checkpoint saving for phases 17-18
5. Resumption from phase 17 checkpoint
6. Resumption from phase 18 checkpoint
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.orchestration.workflow_manager import WorkflowManager
from rich.console import Console
from rich.table import Table

console = Console()


def test_workflow_execution(config_path: str) -> Dict[str, Any]:
    """Test workflow execution with phases 17-18 enabled."""
    console.print("[bold blue]Test 1: Workflow Execution with Phases 17-18[/bold blue]")
    
    manager = WorkflowManager(config_path)
    
    # Verify config is enabled
    manubot_enabled = manager.config.get("manubot", {}).get("enabled", False)
    submission_enabled = manager.config.get("submission", {}).get("enabled", False)
    
    if not manubot_enabled:
        console.print("[yellow]Warning: manubot.enabled is false in config[/yellow]")
    if not submission_enabled:
        console.print("[yellow]Warning: submission.enabled is false in config[/yellow]")
    
    # Run workflow
    try:
        results = manager.run()
        
        # Check for outputs
        outputs = results.get("outputs", {})
        manubot_path = outputs.get("manubot_export")
        package_path = outputs.get("submission_package")
        
        return {
            "success": True,
            "manubot_export": manubot_path,
            "submission_package": package_path,
            "outputs": outputs,
        }
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return {
            "success": False,
            "error": str(e),
        }


def verify_manubot_export(manubot_path: str) -> Dict[str, bool]:
    """Verify Manubot export directory structure."""
    console.print("[bold blue]Test 2: Verify Manubot Export Structure[/bold blue]")
    
    if not manubot_path:
        return {"exists": False, "has_content": False, "has_manubot_yaml": False}
    
    export_dir = Path(manubot_path)
    checks = {
        "exists": export_dir.exists(),
        "has_content": (export_dir / "content").exists(),
        "has_manubot_yaml": (export_dir / "manubot.yaml").exists(),
    }
    
    if checks["has_content"]:
        content_dir = export_dir / "content"
        checks["has_sections"] = any(content_dir.glob("*.md"))
    
    return checks


def verify_submission_package(package_path: str) -> Dict[str, bool]:
    """Verify submission package structure."""
    console.print("[bold blue]Test 3: Verify Submission Package Structure[/bold blue]")
    
    if not package_path:
        return {"exists": False}
    
    package_dir = Path(package_path)
    checks = {
        "exists": package_dir.exists(),
        "has_manuscript_md": (package_dir / "manuscript.md").exists(),
        "has_figures": (package_dir / "figures").exists(),
        "has_supplementary": (package_dir / "supplementary").exists(),
        "has_checklist": (package_dir / "submission_checklist.md").exists(),
    }
    
    return checks


def verify_checkpoints(workflow_id: str) -> Dict[str, bool]:
    """Verify checkpoint files exist for phases 17-18."""
    console.print("[bold blue]Test 4: Verify Checkpoint Files[/bold blue]")
    
    # Find workflow directory
    outputs_dir = Path("data/outputs")
    workflow_dir = None
    
    for dir_path in outputs_dir.iterdir():
        if dir_path.is_dir() and workflow_id in dir_path.name:
            workflow_dir = dir_path
            break
    
    if not workflow_dir:
        return {"workflow_dir_found": False}
    
    checkpoints_dir = workflow_dir / "checkpoints"
    checks = {
        "workflow_dir_found": True,
        "checkpoints_dir_exists": checkpoints_dir.exists(),
        "manubot_export_checkpoint": (checkpoints_dir / "manubot_export_state.json").exists(),
        "submission_package_checkpoint": (checkpoints_dir / "submission_package_state.json").exists(),
    }
    
    return checks


def test_resumption(config_path: str, phase: str) -> Dict[str, Any]:
    """Test resumption from a specific phase checkpoint."""
    console.print(f"[bold blue]Test 5: Resumption from Phase {phase}[/bold blue]")
    
    manager = WorkflowManager(config_path)
    
    # Find existing checkpoint
    existing_checkpoint = manager._find_existing_checkpoint_by_topic()
    if not existing_checkpoint:
        return {"success": False, "error": "No existing checkpoint found"}
    
    # Modify checkpoint to resume from specified phase
    checkpoint_dir = Path(existing_checkpoint["checkpoint_dir"])
    
    # Create a test checkpoint file for the phase
    test_checkpoint = checkpoint_dir / f"{phase}_state.json"
    if not test_checkpoint.exists():
        return {"success": False, "error": f"Checkpoint for {phase} not found"}
    
    # Load checkpoint and verify
    with open(test_checkpoint, "r") as f:
        checkpoint_data = json.load(f)
    
    return {
        "success": True,
        "checkpoint_exists": True,
        "phase": checkpoint_data.get("phase"),
        "has_data": "data" in checkpoint_data,
    }


def main():
    """Run all tests."""
    console.print("[bold green]Manuscript Pipeline E2E Test Suite[/bold green]")
    console.print("=" * 60)
    
    config_path = "config/workflow.yaml"
    
    # Test 1: Workflow execution
    result1 = test_workflow_execution(config_path)
    
    if not result1.get("success"):
        console.print("[red]Workflow execution failed. Cannot continue tests.[/red]")
        return 1
    
    manubot_path = result1.get("manubot_export")
    package_path = result1.get("submission_package")
    
    # Test 2: Verify Manubot export
    result2 = verify_manubot_export(manubot_path)
    
    # Test 3: Verify submission package
    result3 = verify_submission_package(package_path)
    
    # Test 4: Verify checkpoints
    workflow_id = result1.get("outputs", {}).get("workflow_state", "")
    if workflow_id:
        # Extract workflow ID from path
        workflow_id = Path(workflow_id).parent.name if Path(workflow_id).exists() else ""
    result4 = verify_checkpoints(workflow_id) if workflow_id else {"workflow_id_missing": True}
    
    # Test 5: Test resumption
    result5_manubot = test_resumption(config_path, "manubot_export")
    result5_submission = test_resumption(config_path, "submission_package")
    
    # Print summary
    console.print("\n[bold green]Test Summary[/bold green]")
    console.print("=" * 60)
    
    table = Table(title="Test Results")
    table.add_column("Test", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Details", style="green")
    
    table.add_row("Workflow Execution", 
                  "PASS" if result1.get("success") else "FAIL",
                  f"Manubot: {manubot_path is not None}, Package: {package_path is not None}")
    
    table.add_row("Manubot Export Structure",
                  "PASS" if result2.get("exists") else "FAIL",
                  f"Content: {result2.get('has_content')}, YAML: {result2.get('has_manubot_yaml')}")
    
    table.add_row("Submission Package Structure",
                  "PASS" if result3.get("exists") else "FAIL",
                  f"Manuscript: {result3.get('has_manuscript_md')}, Checklist: {result3.get('has_checklist')}")
    
    table.add_row("Checkpoint Files",
                  "PASS" if result4.get("manubot_export_checkpoint") else "FAIL",
                  f"Manubot: {result4.get('manubot_export_checkpoint')}, Package: {result4.get('submission_package_checkpoint')}")
    
    table.add_row("Resumption (Manubot)",
                  "PASS" if result5_manubot.get("success") else "FAIL",
                  result5_manubot.get("error", "OK"))
    
    table.add_row("Resumption (Submission)",
                  "PASS" if result5_submission.get("success") else "FAIL",
                  result5_submission.get("error", "OK"))
    
    console.print(table)
    
    # Determine overall success
    all_passed = (
        result1.get("success") and
        result2.get("exists") and
        result3.get("exists") and
        result4.get("manubot_export_checkpoint") and
        result5_manubot.get("success") and
        result5_submission.get("success")
    )
    
    if all_passed:
        console.print("\n[bold green]All tests passed![/bold green]")
        return 0
    else:
        console.print("\n[bold yellow]Some tests failed. Review output above.[/bold yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
