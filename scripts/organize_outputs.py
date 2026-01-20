#!/usr/bin/env python3
"""
Organize orphaned output files into workflow-specific directories.

This script moves files from data/outputs/ root into appropriate workflow directories
based on workflow_state.json or creates a new workflow directory.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import re


def generate_workflow_id_from_topic(topic: str) -> str:
    """Generate workflow ID from topic."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_slug = topic.lower().replace(" ", "_")[:30]
    # Remove special characters that might cause issues
    topic_slug = re.sub(r'[^a-z0-9_-]', '', topic_slug)
    return f"workflow_{topic_slug}_{timestamp}"


def find_matching_workflow_dir(outputs_dir: Path, topic: str) -> Optional[Path]:
    """Find existing workflow directory that matches the topic."""
    topic_lower = topic.lower().strip()
    
    for workflow_dir in outputs_dir.iterdir():
        if not workflow_dir.is_dir():
            continue
        
        if not workflow_dir.name.startswith("workflow_"):
            continue
        
        # Check workflow_state.json in this directory
        state_file = workflow_dir / "workflow_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    workflow_topic = state.get("topic_context", {}).get("topic", "").lower().strip()
                    if workflow_topic == topic_lower:
                        return workflow_dir
            except Exception:
                continue
    
    return None


def get_files_to_move(outputs_dir: Path) -> List[Path]:
    """Get list of files/directories that should be moved to workflow directory."""
    # Files that should be in workflow directory (not subdirectories)
    workflow_files = [
        "final_report.md",
        "workflow_state.json",
        "prisma_diagram.png",
        "network_graph.html",
        "network_graph.png",
        "papers_by_country.png",
        "papers_by_subject.png",
        "papers_per_year.png",
        "search_strategies.md",
        "data_extraction_form.md",
        "prisma_checklist.json",
        "prisma_validation_report.json",
        "dependency_analysis.json",
        "dependency_analysis_summary.md",
        "dependency_graph.dot",
        "enhanced_structure_verification.txt",
    ]
    
    # Directories that should be in workflow directory
    workflow_dirs = [
        "manuscript",
        "submission_package_ieee",
        "visualizations",
    ]
    
    files_to_move = []
    
    # Check for files
    for filename in workflow_files:
        file_path = outputs_dir / filename
        if file_path.exists():
            files_to_move.append(file_path)
    
    # Check for directories
    for dirname in workflow_dirs:
        dir_path = outputs_dir / dirname
        if dir_path.exists() and dir_path.is_dir():
            files_to_move.append(dir_path)
    
    return files_to_move


def organize_outputs(outputs_dir: Path, dry_run: bool = False) -> None:
    """Organize orphaned files into workflow directories."""
    outputs_dir = Path(outputs_dir)
    
    if not outputs_dir.exists():
        print(f"Output directory does not exist: {outputs_dir}")
        return
    
    # Check for workflow_state.json in root
    root_state_file = outputs_dir / "workflow_state.json"
    if not root_state_file.exists():
        print("No workflow_state.json found in root. Cannot determine workflow.")
        print("Available workflow directories:")
        for item in outputs_dir.iterdir():
            if item.is_dir() and item.name.startswith("workflow_"):
                print(f"  - {item.name}")
        return
    
    # Read workflow state
    try:
        with open(root_state_file, "r") as f:
            state = json.load(f)
    except Exception as e:
        print(f"Error reading workflow_state.json: {e}")
        return
    
    topic = state.get("topic_context", {}).get("topic", "")
    if not topic:
        print("Could not determine topic from workflow_state.json")
        return
    
    print(f"Topic: {topic}")
    
    # Find matching workflow directory or create new one
    workflow_dir = find_matching_workflow_dir(outputs_dir, topic)
    
    if workflow_dir:
        print(f"Found existing workflow directory: {workflow_dir.name}")
    else:
        workflow_id = generate_workflow_id_from_topic(topic)
        workflow_dir = outputs_dir / workflow_id
        if not dry_run:
            workflow_dir.mkdir(parents=True, exist_ok=True)
        print(f"Creating new workflow directory: {workflow_dir.name}")
    
    # Get files to move
    files_to_move = get_files_to_move(outputs_dir)
    
    if not files_to_move:
        print("No files to move.")
        return
    
    print(f"\nFiles/directories to move ({len(files_to_move)}):")
    for item in files_to_move:
        print(f"  - {item.name}")
    
    if dry_run:
        print("\n[DRY RUN] Would move files to:", workflow_dir)
        return
    
    # Move files
    print(f"\nMoving files to {workflow_dir}...")
    moved_count = 0
    skipped_count = 0
    
    for item in files_to_move:
        dest = workflow_dir / item.name
        
        if dest.exists():
            print(f"  SKIP: {item.name} (already exists in destination)")
            skipped_count += 1
            continue
        
        try:
            if item.is_dir():
                shutil.move(str(item), str(dest))
            else:
                shutil.move(str(item), str(dest))
            print(f"  MOVED: {item.name}")
            moved_count += 1
        except Exception as e:
            print(f"  ERROR moving {item.name}: {e}")
    
    print(f"\nDone! Moved {moved_count} items, skipped {skipped_count} items.")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Organize orphaned output files into workflow-specific directories"
    )
    parser.add_argument(
        "--outputs-dir",
        type=str,
        default="data/outputs",
        help="Path to outputs directory (default: data/outputs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be moved without actually moving files",
    )
    
    args = parser.parse_args()
    
    organize_outputs(Path(args.outputs_dir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
