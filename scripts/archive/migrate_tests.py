#!/usr/bin/env python3
"""
Test Migration Helper

Helps migrate tests to new structure mirroring src/.
This script assists with moving and renaming test files.
"""

import os
import shutil
import json
from pathlib import Path
from typing import Dict, Optional

def load_test_mapping() -> Dict:
    """Load test mapping."""
    mapping_path = Path('data/test_mapping.json')
    if mapping_path.exists():
        with open(mapping_path, 'r') as f:
            return json.load(f)
    return {}

def get_new_test_path(old_test_path: Path, source_mapping: Optional[str]) -> Optional[Path]:
    """
    Determine new test path based on source mapping.
    
    Args:
        old_test_path: Current test file path
        source_mapping: Source file path relative to src/
    
    Returns:
        New test path or None if cannot determine
    """
    if not source_mapping:
        return None
    
    # New path: tests/unit/<same_path_as_src>/test_<module>.py
    source_path = Path('src') / source_mapping
    source_name = source_path.stem
    
    # Build new test path
    new_test_dir = Path('tests/unit') / source_path.parent.relative_to('src')
    new_test_file = new_test_dir / f'test_{source_name}.py'
    
    return new_test_file

def migrate_test_file(old_path: Path, new_path: Path, dry_run: bool = True) -> bool:
    """
    Migrate a test file to new location.
    
    Args:
        old_path: Current test file path
        new_path: New test file path
        dry_run: If True, only show what would be done
    
    Returns:
        True if successful
    """
    if not old_path.exists():
        print(f"ERROR: Test file not found: {old_path}")
        return False
    
    if new_path.exists() and not dry_run:
        print(f"WARNING: Target file already exists: {new_path}")
        return False
    
    if dry_run:
        print(f"Would move: {old_path} -> {new_path}")
        return True
    
    # Create directory if needed
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Move file
    shutil.move(str(old_path), str(new_path))
    print(f"Moved: {old_path} -> {new_path}")
    
    return True

def main():
    """Main migration function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate tests to new structure')
    parser.add_argument('--test-file', help='Specific test file to migrate')
    parser.add_argument('--all', action='store_true', help='Migrate all mappable tests')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Show what would be done (default)')
    parser.add_argument('--execute', action='store_true', help='Actually perform migration')
    
    args = parser.parse_args()
    
    if not args.execute:
        args.dry_run = True
    
    mapping = load_test_mapping()
    test_mapping = mapping.get('mapping', {})
    
    if args.test_file:
        # Migrate specific test
        old_path = Path(args.test_file)
        if not old_path.exists():
            print(f"ERROR: Test file not found: {old_path}")
            return
        
        test_rel = str(old_path.relative_to('tests'))
        source_mapping = test_mapping.get(test_rel)
        
        if not source_mapping:
            print(f"ERROR: No source mapping found for {test_rel}")
            return
        
        new_path = get_new_test_path(old_path, source_mapping)
        if new_path:
            migrate_test_file(old_path, new_path, dry_run=args.dry_run)
        else:
            print(f"ERROR: Could not determine new path for {old_path}")
    
    elif args.all:
        # Migrate all mappable tests
        migrated = 0
        skipped = 0
        
        for test_rel, source_rel in test_mapping.items():
            old_path = Path('tests') / test_rel
            
            # Skip if already in correct location
            if test_rel.startswith('unit/') and '/'.join(test_rel.split('/')[1:]) == source_rel.replace('.py', ''):
                continue
            
            new_path = get_new_test_path(old_path, source_rel)
            if new_path:
                if migrate_test_file(old_path, new_path, dry_run=args.dry_run):
                    migrated += 1
            else:
                skipped += 1
        
        print(f"\nMigration complete:")
        print(f"  Migrated: {migrated}")
        print(f"  Skipped: {skipped}")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
