#!/usr/bin/env python3
"""
Test Health Dashboard

Quick overview of test suite health and performance.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd):
    """Run shell command and return output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


def count_tests():
    """Count total tests"""
    code, stdout, _ = run_command("pytest --collect-only -q 2>/dev/null | tail -1")
    if code == 0 and stdout:
        try:
            # Parse "X passed, Y skipped, ..." format
            parts = stdout.strip().split()
            if len(parts) > 0:
                return int(parts[0])
        except:
            pass
    return 0


def get_test_categories():
    """Count tests by category"""
    categories = {}
    
    # Fast tests
    code, stdout, _ = run_command("pytest -m 'fast' --collect-only -q 2>/dev/null | tail -1")
    if code == 0 and stdout:
        try:
            categories['fast'] = int(stdout.strip().split()[0])
        except:
            categories['fast'] = 0
    
    # Unit tests
    code, stdout, _ = run_command("pytest tests/unit --collect-only -q 2>/dev/null | tail -1")
    if code == 0 and stdout:
        try:
            categories['unit'] = int(stdout.strip().split()[0])
        except:
            categories['unit'] = 0
    
    # Integration tests
    code, stdout, _ = run_command("pytest tests/integration --collect-only -q 2>/dev/null | tail -1")
    if code == 0 and stdout:
        try:
            categories['integration'] = int(stdout.strip().split()[0])
        except:
            categories['integration'] = 0
    
    # E2E tests
    code, stdout, _ = run_command("pytest tests/e2e --collect-only -q 2>/dev/null | tail -1")
    if code == 0 and stdout:
        try:
            categories['e2e'] = int(stdout.strip().split()[0])
        except:
            categories['e2e'] = 0
    
    return categories


def run_fast_tests():
    """Run fast tests and get results"""
    code, stdout, stderr = run_command("pytest -m 'fast' -v --tb=no 2>&1")
    
    passed = stdout.count(" PASSED")
    failed = stdout.count(" FAILED")
    skipped = stdout.count(" SKIPPED")
    
    return {
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
        'exit_code': code
    }


def check_file_sizes():
    """Check for large files that should be split"""
    large_files = []
    
    src_path = Path("src")
    if src_path.exists():
        for py_file in src_path.rglob("*.py"):
            if py_file.is_file():
                line_count = len(py_file.read_text().splitlines())
                if line_count > 1000:
                    large_files.append({
                        'path': str(py_file),
                        'lines': line_count
                    })
    
    return sorted(large_files, key=lambda x: x['lines'], reverse=True)


def main():
    print("=" * 60)
    print("TEST HEALTH DASHBOARD")
    print("=" * 60)
    print()
    
    # Total tests
    print("[1/4] Counting tests...")
    total = count_tests()
    categories = get_test_categories()
    
    print(f"  Total Tests: {total}")
    print(f"  Fast Tests:  {categories.get('fast', 0)}")
    print(f"  Unit Tests:  {categories.get('unit', 0)}")
    print(f"  Integration: {categories.get('integration', 0)}")
    print(f"  E2E Tests:   {categories.get('e2e', 0)}")
    print()
    
    # Run fast tests
    print("[2/4] Running fast tests...")
    results = run_fast_tests()
    
    status = "PASS" if results['exit_code'] == 0 else "FAIL"
    print(f"  Status:  {status}")
    print(f"  Passed:  {results['passed']}")
    print(f"  Failed:  {results['failed']}")
    print(f"  Skipped: {results['skipped']}")
    print()
    
    # Check file sizes
    print("[3/4] Checking file sizes...")
    large_files = check_file_sizes()
    
    if large_files:
        print(f"  Found {len(large_files)} files >1000 lines:")
        for f in large_files[:5]:  # Show top 5
            print(f"    {f['path']}: {f['lines']} lines")
    else:
        print("  All files <1000 lines (good!)")
    print()
    
    # Health summary
    print("[4/4] Health Summary")
    print("-" * 60)
    
    health_score = 100
    issues = []
    
    if results['failed'] > 0:
        health_score -= 30
        issues.append(f"  WARNING: {results['failed']} fast tests failing")
    
    if len(large_files) > 0:
        health_score -= 20
        issues.append(f"  WARNING: {len(large_files)} large files need splitting")
    
    if categories.get('fast', 0) < 10:
        health_score -= 10
        issues.append(f"  WARNING: Only {categories.get('fast', 0)} fast tests (should have 20+)")
    
    if issues:
        for issue in issues:
            print(issue)
        print()
    
    print(f"Overall Health Score: {health_score}/100")
    print()
    
    if health_score >= 90:
        print("Status: EXCELLENT - Test suite is healthy!")
    elif health_score >= 70:
        print("Status: GOOD - Minor issues to address")
    elif health_score >= 50:
        print("Status: FAIR - Several issues need attention")
    else:
        print("Status: NEEDS WORK - Significant issues found")
    
    print("=" * 60)
    print(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if health_score >= 70 else 1)


if __name__ == "__main__":
    main()
