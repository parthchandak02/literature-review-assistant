#!/usr/bin/env python3
"""
Analyze current test structure and create mapping to source files.

This script analyzes the current test organization and creates a mapping
between source files and test files to help with reorganization.
"""

import os
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

def get_source_files() -> Dict[str, Path]:
    """Get all source Python files."""
    src_files = {}
    for root, dirs, files in os.walk('src'):
        for f in files:
            if f.endswith('.py') and f != '__init__.py':
                full_path = Path(root) / f
                rel_path = str(full_path.relative_to('src'))
                src_files[rel_path] = full_path
    return src_files

def get_test_files() -> Dict[str, Path]:
    """Get all test Python files."""
    test_files = {}
    for root, dirs, files in os.walk('tests'):
        for f in files:
            if f.startswith('test_') and f.endswith('.py'):
                full_path = Path(root) / f
                rel_path = str(full_path.relative_to('tests'))
                test_files[rel_path] = full_path
    return test_files

def guess_test_source_mapping(test_file: Path, src_files: Dict[str, Path]) -> Optional[str]:
    """Guess which source file a test file tests."""
    test_name = test_file.stem  # Remove 'test_' prefix and .py extension
    test_name = test_name.replace('test_', '')
    
    # Try exact match
    for src_rel, src_path in src_files.items():
        src_name = src_path.stem
        if test_name == src_name:
            return src_rel
    
    # Try partial match (e.g., test_acm_connector -> database_connectors)
    for src_rel, src_path in src_files.items():
        src_name = src_path.stem
        if test_name in src_name or src_name in test_name:
            return src_rel
    
    return None

def analyze_structure():
    """Analyze current test structure."""
    src_files = get_source_files()
    test_files = get_test_files()
    
    print(f"Source files: {len(src_files)}")
    print(f"Test files: {len(test_files)}")
    print()
    
    # Group source files by directory
    src_by_dir = defaultdict(list)
    for rel_path, full_path in src_files.items():
        dir_name = str(Path(rel_path).parent) if '/' in rel_path else '.'
        src_by_dir[dir_name].append((rel_path, full_path))
    
    # Group test files by directory
    test_by_dir = defaultdict(list)
    for rel_path, full_path in test_files.items():
        dir_name = str(Path(rel_path).parent) if '/' in rel_path else '.'
        test_by_dir[dir_name].append((rel_path, full_path))
    
    # Create mapping
    mapping = {}
    unmapped_tests = []
    unmapped_sources = []
    
    for test_rel, test_path in test_files.items():
        mapped = guess_test_source_mapping(test_path, src_files)
        if mapped:
            mapping[test_rel] = mapped
        else:
            unmapped_tests.append(test_rel)
    
    # Find sources without tests
    mapped_sources = set(mapping.values())
    for src_rel in src_files.keys():
        if src_rel not in mapped_sources:
            unmapped_sources.append(src_rel)
    
    # Print analysis
    print("=" * 80)
    print("SOURCE MODULES BY DIRECTORY")
    print("=" * 80)
    for dir_name in sorted(src_by_dir.keys()):
        files = src_by_dir[dir_name]
        print(f"\n{dir_name}/ ({len(files)} files):")
        for rel_path, _ in sorted(files):
            print(f"  - {rel_path}")
    
    print("\n" + "=" * 80)
    print("TEST FILES BY DIRECTORY")
    print("=" * 80)
    for dir_name in sorted(test_by_dir.keys()):
        files = test_by_dir[dir_name]
        print(f"\n{dir_name}/ ({len(files)} files):")
        for rel_path, _ in sorted(files):
            mapped = mapping.get(rel_path, "UNMAPPED")
            print(f"  - {rel_path} -> {mapped}")
    
    print("\n" + "=" * 80)
    print("MAPPING SUMMARY")
    print("=" * 80)
    print(f"Mapped tests: {len(mapping)}")
    print(f"Unmapped tests: {len(unmapped_tests)}")
    print(f"Sources without tests: {len(unmapped_sources)}")
    
    if unmapped_tests:
        print("\nUnmapped tests:")
        for test in sorted(unmapped_tests):
            print(f"  - {test}")
    
    if unmapped_sources:
        print("\nSources without tests:")
        for src in sorted(unmapped_sources)[:20]:  # Show first 20
            print(f"  - {src}")
        if len(unmapped_sources) > 20:
            print(f"  ... and {len(unmapped_sources) - 20} more")
    
    # Save mapping to JSON
    output = {
        'source_files': {k: str(v) for k, v in src_files.items()},
        'test_files': {k: str(v) for k, v in test_files.items()},
        'mapping': mapping,
        'unmapped_tests': unmapped_tests,
        'unmapped_sources': unmapped_sources,
    }
    
    output_path = Path('data/test_mapping.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nMapping saved to: {output_path}")
    
    return output

if __name__ == '__main__':
    analyze_structure()
