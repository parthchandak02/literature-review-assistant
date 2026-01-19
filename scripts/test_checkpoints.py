#!/usr/bin/env python3
"""
Checkpoint-by-checkpoint testing script for visualization improvements.

Run tests systematically to verify each component works correctly.
"""

import sys
import subprocess
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def run_tests(test_pattern: str, description: str) -> bool:
    """Run pytest with specific pattern and return success status."""
    print(f"\n{'='*70}")
    print(f"CHECKPOINT: {description}")
    print(f"{'='*70}\n")
    
    cmd = ["pytest", "-v", test_pattern, "--tb=short"]
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    
    success = result.returncode == 0
    if success:
        print(f"\n✓ {description} - PASSED")
    else:
        print(f"\n✗ {description} - FAILED")
    
    return success


def main():
    """Run all checkpoints in sequence."""
    checkpoints = [
        # Phase 1: Affiliation Extraction
        (
            "tests/unit/test_affiliation_extraction.py::TestPubMedAffiliationExtraction",
            "PubMed Affiliation Extraction"
        ),
        (
            "tests/unit/test_affiliation_extraction.py::TestCrossrefAffiliationExtraction",
            "Crossref Affiliation Extraction"
        ),
        (
            "tests/unit/test_affiliation_extraction.py::TestScopusAffiliationExtraction",
            "Scopus Affiliation Extraction"
        ),
        (
            "tests/unit/test_affiliation_extraction.py::TestSemanticScholarAffiliationExtraction",
            "Semantic Scholar Affiliation Extraction"
        ),
        
        # Phase 2: Country Extraction
        (
            "tests/unit/test_visualization_enhanced.py::TestCountryExtraction",
            "Country Extraction from Affiliations"
        ),
        (
            "tests/unit/test_visualization.py::TestChartGenerator::test_papers_by_country_with_papers",
            "Country Chart Generation"
        ),
        
        # Phase 3: Subject Extraction
        (
            "tests/unit/test_visualization_enhanced.py::TestSubjectExtraction",
            "Subject Extraction and Normalization"
        ),
        (
            "tests/unit/test_visualization.py::TestChartGenerator::test_papers_by_subject_with_papers",
            "Subject Chart Generation"
        ),
        
        # Phase 4: Network Graph
        (
            "tests/unit/test_visualization_enhanced.py::TestNetworkGraphPyvis",
            "Pyvis Network Graph Generation"
        ),
        (
            "tests/unit/test_visualization.py::TestChartGenerator::test_network_graph_with_papers",
            "Network Graph Basic Functionality"
        ),
        
        # Phase 5: Integration Tests
        (
            "tests/e2e/test_workflow_with_visualization.py",
            "End-to-End Workflow with Visualizations"
        ),
    ]
    
    results = []
    
    print("\n" + "="*70)
    print("VISUALIZATION IMPROVEMENTS - CHECKPOINT TESTING")
    print("="*70)
    
    for test_pattern, description in checkpoints:
        success = run_tests(test_pattern, description)
        results.append((description, success))
        
        if not success:
            print(f"\n⚠ WARNING: {description} failed. Review errors above.")
            response = input("\nContinue to next checkpoint? (y/n): ")
            if response.lower() != 'y':
                print("\nStopping checkpoint testing.")
                break
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{status}: {description}")
    
    print(f"\nTotal: {passed}/{total} checkpoints passed")
    
    if passed == total:
        print("\n🎉 All checkpoints passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} checkpoint(s) failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
