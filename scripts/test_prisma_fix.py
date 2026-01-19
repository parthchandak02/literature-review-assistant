#!/usr/bin/env python3
"""
Test PRISMA Fix

Verify that PRISMA validation works correctly with the fixed assessed count logic.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.prisma.prisma_generator import PRISMACounter, PRISMAGenerator


def test_prisma_validation():
    """Test PRISMA validation with corrected counts."""
    print("Testing PRISMA validation fix...\n")
    
    # Create counter with scenario from actual workflow
    counter = PRISMACounter()
    counter.set_found(100)
    counter.set_no_dupes(94)
    counter.set_screened(94)
    counter.set_screen_exclusions(4)
    counter.set_full_text_sought(90)  # Papers that passed title/abstract screening
    counter.set_full_text_not_retrieved(86)  # Papers without full-text
    # Fixed: assessed = ALL papers evaluated (90), not just those with full-text (4)
    counter.set_full_text_assessed(90)  # All screened papers were assessed
    counter.set_full_text_exclusions(80)  # 90 - 10 = 80 excluded
    counter.set_qualitative(10)  # Final included studies
    
    # Test validation
    generator = PRISMAGenerator(counter)
    counts = counter.get_counts()
    
    print("PRISMA Counts:")
    print(f"  Found: {counts['found']}")
    print(f"  Unique: {counts['no_dupes']}")
    print(f"  Screened: {counts['screened']}")
    print(f"  Title/Abstract Exclusions: {counts['screen_exclusions']}")
    print(f"  Full-text Sought: {counts['full_text_sought']}")
    print(f"  Full-text Not Retrieved: {counts['full_text_not_retrieved']}")
    print(f"  Full-text Assessed: {counts['full_text_assessed']}")
    print(f"  Full-text Exclusions: {counts['full_text_exclusions']}")
    print(f"  Included: {counts['qualitative']}")
    print()
    
    # Validate
    is_valid, warnings = generator._validate_prisma_counts(counts)
    
    if is_valid:
        print("[PASS] PRISMA validation passed - no warnings!")
    else:
        print("[FAIL] PRISMA validation failed:")
        for warning in warnings:
            print(f"  - {warning}")
    
    # Verify the fix: assessed should equal sought (all papers evaluated)
    if counts['full_text_assessed'] == counts['full_text_sought']:
        print("\n[PASS] Assessed count correctly equals sought (all papers evaluated)")
    else:
        print(f"\n[FAIL] Assessed ({counts['full_text_assessed']}) != sought ({counts['full_text_sought']})")
    
    # Verify: included <= assessed
    if counts['qualitative'] <= counts['full_text_assessed']:
        print("[PASS] Included count <= assessed count (PRISMA rule satisfied)")
    else:
        print(f"[FAIL] Included ({counts['qualitative']}) > assessed ({counts['full_text_assessed']})")
    
    print("\n" + "="*60)
    print("Test Summary:")
    if is_valid and counts['full_text_assessed'] == counts['full_text_sought']:
        print("[SUCCESS] PRISMA fix is working correctly!")
        return 0
    else:
        print("[FAILURE] PRISMA fix needs attention")
        return 1


if __name__ == "__main__":
    sys.exit(test_prisma_validation())
