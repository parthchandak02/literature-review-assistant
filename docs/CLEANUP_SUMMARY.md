# Test and Script Cleanup Summary

## Overview

This document provides a quick reference summary of the test and script cleanup plan. For detailed information, see:
- **Inventory**: `TEST_AND_SCRIPT_INVENTORY.md` - Complete catalog of all files
- **Implementation Plan**: `CLEANUP_IMPLEMENTATION_PLAN.md` - Step-by-step execution guide

## Current State

- **Total Files**: 106 (31 scripts + 75 tests)
- **Issues Identified**: 
  - 4 temporary scripts that should be removed
  - 4 test scripts that should be in test directories
  - 1 migration script that should be archived

## Quick Action Summary

### Remove (4 files)
1. `scripts/test_bibtex_acm_features.py`
2. `scripts/test_improved_scrapers.py`
3. `scripts/verify_enhanced_structure.py`
4. `scripts/remediate_current_paper.py`

### Move to Tests (4 files)
1. `scripts/test_workflow_e2e_comprehensive.py` → `tests/e2e/test_workflow_comprehensive.py`
2. `scripts/test_enrichment_and_visualizations.py` → `tests/integration/test_enrichment_and_visualizations.py`
3. `scripts/test_humanization_integration.py` → `tests/integration/test_humanization_integration.py`
4. `scripts/test_manuscript_pipeline_e2e.py` → `tests/e2e/test_manuscript_pipeline_e2e.py`

### Archive (1 file)
1. `scripts/migrate_tests.py` → `scripts/archive/migrate_tests.py`

## Expected Outcome

**After Cleanup:**
- Scripts: 31 → 22 files
- Tests: 75 → 79 files (4 moved from scripts)
- **Total**: 106 → 101 files

## Implementation Phases

### Phase 1: Verification ✓
- Complete file review
- Update inventory with verified information

### Phase 2: Cleanup Execution
- Remove 4 temporary scripts
- Move 4 test scripts
- Archive 1 migration script

### Phase 3: Validation
- Verify all tests discoverable
- Check for broken imports
- Run test suite

### Phase 4: Documentation
- Update README files
- Document changes

## Key Files

- **Inventory**: `docs/TEST_AND_SCRIPT_INVENTORY.md`
- **Implementation Plan**: `docs/CLEANUP_IMPLEMENTATION_PLAN.md`
- **This Summary**: `docs/CLEANUP_SUMMARY.md`

## Next Steps

1. Review the inventory document
2. Follow the implementation plan
3. Execute cleanup phase by phase
4. Validate after each phase
5. Update documentation
