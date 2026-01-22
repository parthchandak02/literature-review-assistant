#!/usr/bin/env python3
"""
Test Discovery and Mapping Tool

Find tests for source files, identify missing tests, and generate test coverage reports.
"""

import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

def load_test_mapping() -> Dict:
    """Load test mapping from JSON file."""
    mapping_path = Path('data/test_mapping.json')
    if mapping_path.exists():
        with open(mapping_path, 'r') as f:
            return json.load(f)
    return {}

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

def find_tests_for_source(source_path: str, mapping: Dict) -> List[str]:
    """Find test files for a given source file."""
    # Normalize path
    if source_path.startswith('src/'):
        source_path = source_path[4:]
    
    tests = []
    for test_rel, src_rel in mapping.get('mapping', {}).items():
        if src_rel == source_path:
            tests.append(test_rel)
    
    return tests

def find_source_for_test(test_path: str, mapping: Dict) -> Optional[str]:
    """Find source file for a given test file."""
    # Normalize path
    if test_path.startswith('tests/'):
        test_path = test_path[6:]
    
    return mapping.get('mapping', {}).get(test_path)

def find_missing_tests(mapping: Dict) -> List[str]:
    """Find source files without tests."""
    return mapping.get('unmapped_sources', [])

def find_orphaned_tests(mapping: Dict) -> List[str]:
    """Find test files that don't map to any source."""
    unmapped = mapping.get('unmapped_tests', [])
    # Filter out e2e and integration tests (they test workflows, not modules)
    return [t for t in unmapped if not t.startswith('e2e/') and not t.startswith('integration/')]

def generate_coverage_report(mapping: Dict) -> Dict:
    """Generate test coverage report."""
    src_files = get_source_files()
    test_files = get_test_files()
    mapping_dict = mapping.get('mapping', {})
    
    # Count by directory
    coverage_by_dir = defaultdict(lambda: {'total': 0, 'tested': 0, 'files': []})
    
    for src_rel, src_path in src_files.items():
        dir_name = str(Path(src_rel).parent) if '/' in src_rel else '.'
        coverage_by_dir[dir_name]['total'] += 1
        
        # Check if has test
        has_test = src_rel in mapping_dict.values()
        if has_test:
            coverage_by_dir[dir_name]['tested'] += 1
        
        coverage_by_dir[dir_name]['files'].append({
            'file': src_rel,
            'has_test': has_test,
            'tests': [t for t, s in mapping_dict.items() if s == src_rel]
        })
    
    return {
        'by_directory': {k: {
            'total': v['total'],
            'tested': v['tested'],
            'coverage_percent': (v['tested'] / v['total'] * 100) if v['total'] > 0 else 0,
            'files': v['files']
        } for k, v in coverage_by_dir.items()},
        'overall': {
            'total_files': len(src_files),
            'tested_files': len(set(mapping_dict.values())),
            'coverage_percent': (len(set(mapping_dict.values())) / len(src_files) * 100) if src_files else 0
        }
    }

def main():
    parser = argparse.ArgumentParser(description='Test discovery and mapping tool')
    parser.add_argument('--source', help='Find tests for a source file')
    parser.add_argument('--test', help='Find source file for a test file')
    parser.add_argument('--module', help='Find all tests for a module (directory)')
    parser.add_argument('--missing-tests', action='store_true', help='List source files without tests')
    parser.add_argument('--orphaned', action='store_true', help='List orphaned test files')
    parser.add_argument('--coverage', action='store_true', help='Generate coverage report')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    mapping = load_test_mapping()
    
    if args.source:
        tests = find_tests_for_source(args.source, mapping)
        if args.json:
            print(json.dumps({'source': args.source, 'tests': tests}, indent=2))
        else:
            if tests:
                print(f"Tests for {args.source}:")
                for test in tests:
                    print(f"  - tests/{test}")
            else:
                print(f"No tests found for {args.source}")
    
    elif args.test:
        source = find_source_for_test(args.test, mapping)
        if args.json:
            print(json.dumps({'test': args.test, 'source': source}, indent=2))
        else:
            if source:
                print(f"Source file for {args.test}: src/{source}")
            else:
                print(f"No source file found for {args.test}")
    
    elif args.module:
        src_files = get_source_files()
        tests = []
        for src_rel, src_path in src_files.items():
            if src_rel.startswith(args.module + '/'):
                test_list = find_tests_for_source(src_rel, mapping)
                tests.extend(test_list)
        
        if args.json:
            print(json.dumps({'module': args.module, 'tests': tests}, indent=2))
        else:
            if tests:
                print(f"Tests for module {args.module}:")
                for test in sorted(set(tests)):
                    print(f"  - tests/{test}")
            else:
                print(f"No tests found for module {args.module}")
    
    elif args.missing_tests:
        missing = find_missing_tests(mapping)
        if args.json:
            print(json.dumps({'missing_tests': missing}, indent=2))
        else:
            print(f"Source files without tests ({len(missing)}):")
            for src in sorted(missing)[:50]:
                print(f"  - src/{src}")
            if len(missing) > 50:
                print(f"  ... and {len(missing) - 50} more")
    
    elif args.orphaned:
        orphaned = find_orphaned_tests(mapping)
        if args.json:
            print(json.dumps({'orphaned_tests': orphaned}, indent=2))
        else:
            print(f"Orphaned test files ({len(orphaned)}):")
            for test in sorted(orphaned):
                print(f"  - tests/{test}")
    
    elif args.coverage:
        report = generate_coverage_report(mapping)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print("=" * 80)
            print("TEST COVERAGE REPORT")
            print("=" * 80)
            print(f"\nOverall Coverage: {report['overall']['coverage_percent']:.1f}%")
            print(f"  Total files: {report['overall']['total_files']}")
            print(f"  Tested files: {report['overall']['tested_files']}")
            
            print("\nCoverage by Directory:")
            for dir_name in sorted(report['by_directory'].keys()):
                dir_data = report['by_directory'][dir_name]
                print(f"\n  {dir_name}/: {dir_data['coverage_percent']:.1f}% ({dir_data['tested']}/{dir_data['total']})")
                if dir_data['coverage_percent'] < 50:
                    print("    Files without tests:")
                    for file_info in dir_data['files']:
                        if not file_info['has_test']:
                            print(f"      - {file_info['file']}")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
