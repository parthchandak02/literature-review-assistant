#!/usr/bin/env python3
"""
Validate Test Structure and Mapping

Validates that test structure matches source structure and checks for:
- Tests in correct locations (mirroring src/)
- Test naming conventions
- Missing tests
- Orphaned tests
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Tuple, Dict
from collections import defaultdict

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
        # Skip fixtures directory
        if 'fixtures' in root:
            continue
        for f in files:
            if f.startswith('test_') and f.endswith('.py'):
                full_path = Path(root) / f
                rel_path = str(full_path.relative_to('tests'))
                test_files[rel_path] = full_path
    return test_files

def validate_test_structure() -> Tuple[List[str], List[str], List[str]]:
    """
    Validate test structure.
    
    Returns:
        Tuple of (errors, warnings, info)
    """
    errors = []
    warnings = []
    info = []
    
    src_files = get_source_files()
    test_files = get_test_files()
    
    # Check: Unit tests should mirror src/ structure
    unit_tests = {k: v for k, v in test_files.items() if k.startswith('unit/')}
    
    for test_rel, test_path in unit_tests.items():
        # Remove 'unit/' prefix and 'test_' prefix
        test_name = test_rel[5:]  # Remove 'unit/'
        test_name = test_name.replace('test_', '')
        
        # Expected location: tests/unit/<same_path_as_src>/test_<module>.py
        # Check if there's a corresponding source file
        found_source = False
        for src_rel, src_path in src_files.items():
            src_name = src_path.stem
            # Check if test name matches source name
            if test_name == src_name:
                # Check if path matches
                expected_test_dir = Path('tests/unit') / src_path.parent.relative_to('src')
                actual_test_dir = test_path.parent
                
                if expected_test_dir != actual_test_dir:
                    warnings.append(
                        f"Test {test_rel} should be in {expected_test_dir.relative_to('tests')}/ "
                        f"to mirror src/{src_rel}"
                    )
                found_source = True
                break
        
        if not found_source and not test_rel.startswith('unit/e2e') and not test_rel.startswith('unit/integration'):
            # This might be okay for integration/e2e tests
            pass
    
    # Check: Test naming convention
    for test_rel, test_path in test_files.items():
        test_name = test_path.stem
        if not test_name.startswith('test_'):
            errors.append(f"Test file {test_rel} does not start with 'test_'")
    
    # Check: Tests should have corresponding source files (for unit tests)
    for test_rel, test_path in unit_tests.items():
        test_name = test_path.stem.replace('test_', '')
        found = False
        for src_rel, src_path in src_files.items():
            if src_path.stem == test_name:
                found = True
                break
        if not found and not any(x in test_rel for x in ['integration', 'e2e', 'workflow']):
            warnings.append(f"Test {test_rel} doesn't seem to map to any source file")
    
    # Check: Source files should have tests (for important modules)
    important_modules = ['orchestration', 'search', 'citations', 'export', 'writing']
    for src_rel, src_path in src_files.items():
        module_dir = str(Path(src_rel).parent)
        if any(imp in module_dir for imp in important_modules):
            # Check if there's a test
            has_test = False
            for test_rel, test_path in test_files.items():
                test_name = test_path.stem.replace('test_', '')
                if test_name == src_path.stem:
                    has_test = True
                    break
            
            if not has_test:
                info.append(f"Source file src/{src_rel} has no corresponding test")
    
    return errors, warnings, info

def main():
    """Run validation."""
    print("=" * 80)
    print("TEST STRUCTURE VALIDATION")
    print("=" * 80)
    print()
    
    errors, warnings, info = validate_test_structure()
    
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for error in errors:
            print(f"  [ERROR] {error}")
        print()
    
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for warning in warnings[:20]:  # Show first 20
            print(f"  [WARN] {warning}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more warnings")
        print()
    
    if info:
        print(f"INFO ({len(info)}):")
        for item in info[:20]:  # Show first 20
            print(f"  [INFO] {item}")
        if len(info) > 20:
            print(f"  ... and {len(info) - 20} more items")
        print()
    
    print("=" * 80)
    if errors:
        print("VALIDATION FAILED: Fix errors above")
        sys.exit(1)
    elif warnings:
        print("VALIDATION PASSED WITH WARNINGS: Review warnings above")
        sys.exit(0)
    else:
        print("VALIDATION PASSED")
        sys.exit(0)

if __name__ == '__main__':
    main()
