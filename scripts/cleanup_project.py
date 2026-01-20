#!/usr/bin/env python3
"""
[Utility Script] Project Cleanup

Removes unnecessary files and directories:
- __pycache__ directories and .pyc files
- htmlcov/ coverage reports
- Empty checkpoint directories
- Old test outputs
- Coverage files
"""

import os
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent


def remove_pycache():
    """Remove all __pycache__ directories and .pyc files."""
    removed_dirs = []
    removed_files = []
    
    for root, dirs, files in os.walk(project_root):
        # Skip .venv and other virtual environments
        if '.venv' in root or 'venv' in root or '__pycache__' in root:
            continue
            
        # Remove __pycache__ directories
        if '__pycache__' in dirs:
            pycache_path = Path(root) / '__pycache__'
            try:
                shutil.rmtree(pycache_path)
                removed_dirs.append(str(pycache_path.relative_to(project_root)))
            except Exception as e:
                print(f"Error removing {pycache_path}: {e}")
        
        # Remove .pyc files
        for file in files:
            if file.endswith('.pyc'):
                pyc_path = Path(root) / file
                try:
                    pyc_path.unlink()
                    removed_files.append(str(pyc_path.relative_to(project_root)))
                except Exception as e:
                    print(f"Error removing {pyc_path}: {e}")
    
    return removed_dirs, removed_files


def remove_coverage_files():
    """Remove coverage-related files."""
    removed = []
    
    coverage_items = [
        project_root / 'htmlcov',
        project_root / 'coverage.json',
        project_root / '.coverage',
    ]
    
    for item in coverage_items:
        if item.exists():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removed.append(str(item.relative_to(project_root)))
            except Exception as e:
                print(f"Error removing {item}: {e}")
    
    return removed


def remove_empty_checkpoints():
    """Remove empty checkpoint directories."""
    removed = []
    checkpoints_dir = project_root / 'data' / 'checkpoints'
    
    if not checkpoints_dir.exists():
        return removed
    
    for checkpoint_dir in checkpoints_dir.iterdir():
        if checkpoint_dir.is_dir():
            # Check if directory is empty or only contains empty subdirectories
            try:
                items = list(checkpoint_dir.iterdir())
                if not items:
                    shutil.rmtree(checkpoint_dir)
                    removed.append(str(checkpoint_dir.relative_to(project_root)))
                else:
                    # Check if all items are empty subdirectories
                    all_empty = True
                    for item in items:
                        if item.is_file():
                            all_empty = False
                            break
                        elif item.is_dir():
                            if list(item.iterdir()):
                                all_empty = False
                                break
                    if all_empty:
                        shutil.rmtree(checkpoint_dir)
                        removed.append(str(checkpoint_dir.relative_to(project_root)))
            except Exception as e:
                print(f"Error checking {checkpoint_dir}: {e}")
    
    return removed


def main():
    """Main cleanup function."""
    print("=" * 70)
    print("Project Cleanup")
    print("=" * 70)
    print()
    
    # Remove __pycache__ and .pyc files
    print("Removing __pycache__ directories and .pyc files...")
    removed_dirs, removed_files = remove_pycache()
    print(f"  Removed {len(removed_dirs)} __pycache__ directories")
    print(f"  Removed {len(removed_files)} .pyc files")
    if removed_dirs:
        print(f"  Example directories: {removed_dirs[:3]}")
    print()
    
    # Remove coverage files
    print("Removing coverage files...")
    removed_coverage = remove_coverage_files()
    print(f"  Removed {len(removed_coverage)} coverage items")
    if removed_coverage:
        for item in removed_coverage:
            print(f"    - {item}")
    print()
    
    # Remove empty checkpoints
    print("Removing empty checkpoint directories...")
    removed_checkpoints = remove_empty_checkpoints()
    print(f"  Removed {len(removed_checkpoints)} empty checkpoint directories")
    if removed_checkpoints:
        for checkpoint in removed_checkpoints[:10]:
            print(f"    - {checkpoint}")
        if len(removed_checkpoints) > 10:
            print(f"    ... and {len(removed_checkpoints) - 10} more")
    print()
    
    # Summary
    total_removed = len(removed_dirs) + len(removed_files) + len(removed_coverage) + len(removed_checkpoints)
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total items removed: {total_removed}")
    print(f"  - __pycache__ directories: {len(removed_dirs)}")
    print(f"  - .pyc files: {len(removed_files)}")
    print(f"  - Coverage files: {len(removed_coverage)}")
    print(f"  - Empty checkpoints: {len(removed_checkpoints)}")
    print()
    print("Cleanup complete!")


if __name__ == '__main__':
    main()
