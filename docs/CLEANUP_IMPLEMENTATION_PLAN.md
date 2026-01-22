# Cleanup Implementation Plan

## Overview

This document provides a step-by-step implementation plan for cleaning up the test and script files based on the inventory analysis in `TEST_AND_SCRIPT_INVENTORY.md`.

## Current State

- **Total Files**: 106 (31 scripts + 75 tests)
- **Target State**: 97 files (22 scripts + 75 tests)
- **Files to Remove**: 4
- **Files to Move**: 4
- **Files to Archive**: 1

## Phase 1: Pre-Cleanup Verification

### Step 1.1: Check File Dependencies

Before removing or moving any files, verify they're not imported elsewhere:

```bash
# Check for imports of files to be removed
grep -r "test_bibtex_acm_features" .
grep -r "test_improved_scrapers" .
grep -r "verify_enhanced_structure" .
grep -r "remediate_current_paper" .

# Check for imports of files to be moved
grep -r "test_workflow_e2e_comprehensive" .
grep -r "test_enrichment_and_visualizations" .
grep -r "test_humanization_integration" .
grep -r "test_manuscript_pipeline_e2e" .
```

### Step 1.2: Verify Test Scripts Are Pytest-Compatible

Check if test scripts can be converted to pytest format:

```bash
# Check for pytest markers and test functions
grep -r "def test_" scripts/test_workflow_e2e_comprehensive.py
grep -r "@pytest" scripts/test_workflow_e2e_comprehensive.py
```

### Step 1.3: Create Backup

Create a backup branch before making changes:

```bash
git checkout -b cleanup/test-script-organization
git add .
git commit -m "Pre-cleanup state: backup before file removal and reorganization"
```

## Phase 2: Remove Temporary Scripts

### Step 2.1: Remove test_bibtex_acm_features.py

**File**: `scripts/test_bibtex_acm_features.py`

**Actions**:
1. Verify no imports: `grep -r "test_bibtex_acm_features" .`
2. Delete file: `rm scripts/test_bibtex_acm_features.py`
3. Verify deletion: `ls scripts/test_bibtex_acm_features.py` (should fail)

**Verification**:
- File no longer exists
- No broken imports in codebase

### Step 2.2: Remove test_improved_scrapers.py

**File**: `scripts/test_improved_scrapers.py`

**Actions**:
1. Verify no imports: `grep -r "test_improved_scrapers" .`
2. Delete file: `rm scripts/test_improved_scrapers.py`
3. Verify deletion

**Verification**:
- File no longer exists
- No broken imports

### Step 2.3: Remove verify_enhanced_structure.py

**File**: `scripts/verify_enhanced_structure.py`

**Actions**:
1. Verify no imports: `grep -r "verify_enhanced_structure" .`
2. Delete file: `rm scripts/verify_enhanced_structure.py`
3. Verify deletion

**Verification**:
- File no longer exists
- No broken imports

### Step 2.4: Remove remediate_current_paper.py

**File**: `scripts/remediate_current_paper.py`

**Actions**:
1. Verify no imports: `grep -r "remediate_current_paper" .`
2. Delete file: `rm scripts/remediate_current_paper.py`
3. Verify deletion

**Verification**:
- File no longer exists
- No broken imports

## Phase 3: Move Test Scripts to Proper Locations

### Step 3.1: Move test_workflow_e2e_comprehensive.py

**From**: `scripts/test_workflow_e2e_comprehensive.py`  
**To**: `tests/e2e/test_workflow_comprehensive.py`

**Actions**:
1. Read file to understand structure
2. Convert to pytest format if needed (add pytest imports, markers)
3. Move file: `mv scripts/test_workflow_e2e_comprehensive.py tests/e2e/test_workflow_comprehensive.py`
4. Update any imports in the file
5. Verify pytest can discover it: `pytest --collect-only tests/e2e/test_workflow_comprehensive.py`

**Changes Needed**:
- Add `import pytest` if missing
- Add `@pytest.mark.e2e` markers if needed
- Ensure test functions follow pytest naming (`test_*`)
- Update any relative imports

**Verification**:
- File exists in new location
- Pytest can discover tests
- Tests run successfully

### Step 3.2: Move test_enrichment_and_visualizations.py

**From**: `scripts/test_enrichment_and_visualizations.py`  
**To**: `tests/integration/test_enrichment_and_visualizations.py`

**Actions**:
1. Read file to understand structure
2. Convert to pytest format if needed
3. Move file: `mv scripts/test_enrichment_and_visualizations.py tests/integration/test_enrichment_and_visualizations.py`
4. Update imports
5. Verify pytest discovery

**Changes Needed**:
- Add pytest imports and markers
- Ensure pytest-compatible format
- Update relative imports

**Verification**:
- File exists in new location
- Pytest can discover tests
- Tests run successfully

### Step 3.3: Move test_humanization_integration.py

**From**: `scripts/test_humanization_integration.py`  
**To**: `tests/integration/test_humanization_integration.py`

**Actions**:
1. Read file to understand structure
2. Convert to pytest format if needed
3. Move file: `mv scripts/test_humanization_integration.py tests/integration/test_humanization_integration.py`
4. Update imports
5. Verify pytest discovery

**Changes Needed**:
- Add pytest imports and markers
- Ensure pytest-compatible format
- Update relative imports

**Verification**:
- File exists in new location
- Pytest can discover tests
- Tests run successfully

### Step 3.4: Move test_manuscript_pipeline_e2e.py

**From**: `scripts/test_manuscript_pipeline_e2e.py`  
**To**: `tests/e2e/test_manuscript_pipeline_e2e.py`

**Actions**:
1. Read file to understand structure
2. Convert to pytest format if needed
3. Move file: `mv scripts/test_manuscript_pipeline_e2e.py tests/e2e/test_manuscript_pipeline_e2e.py`
4. Update imports
5. Verify pytest discovery

**Changes Needed**:
- Add pytest imports and markers
- Ensure pytest-compatible format
- Update relative imports

**Verification**:
- File exists in new location
- Pytest can discover tests
- Tests run successfully

## Phase 4: Archive Migration Script

### Step 4.1: Create Archive Directory

**Actions**:
1. Create archive directory: `mkdir -p scripts/archive`
2. Add `.gitkeep` to preserve directory: `touch scripts/archive/.gitkeep`

### Step 4.2: Move migrate_tests.py

**From**: `scripts/migrate_tests.py`  
**To**: `scripts/archive/migrate_tests.py`

**Actions**:
1. Verify no active imports: `grep -r "migrate_tests" . --exclude-dir=scripts/archive`
2. Move file: `mv scripts/migrate_tests.py scripts/archive/migrate_tests.py`
3. Add README in archive explaining why it's archived

**Verification**:
- File exists in archive location
- No broken imports in active code

## Phase 5: Update Test Mapping

### Step 5.1: Regenerate Test Mapping

After moving files, regenerate the test mapping:

```bash
python scripts/analyze_test_structure.py
```

### Step 5.2: Validate Test Structure

Run validation to ensure structure is correct:

```bash
python scripts/validate_test_mapping.py
```

### Step 5.3: Update Test Discovery

Verify test discovery works:

```bash
python scripts/test_discovery.py --orphaned
python scripts/test_discovery.py --coverage
```

## Phase 6: Validation and Testing

### Step 6.1: Check for Broken Imports

```bash
python scripts/check_broken_imports.py
```

### Step 6.2: Verify Test Discovery

```bash
# Check all tests are discoverable
pytest --collect-only

# Check specific moved tests
pytest --collect-only tests/e2e/test_workflow_comprehensive.py
pytest --collect-only tests/integration/test_enrichment_and_visualizations.py
pytest --collect-only tests/integration/test_humanization_integration.py
pytest --collect-only tests/e2e/test_manuscript_pipeline_e2e.py
```

### Step 6.3: Run Sample Tests

Run a sample of tests to ensure they still work:

```bash
# Run moved tests
pytest tests/e2e/test_workflow_comprehensive.py -v
pytest tests/integration/test_enrichment_and_visualizations.py -v

# Run a sample of other tests
pytest tests/unit/test_database_connectors.py -v
pytest tests/integration/test_workflow_phases.py -v
```

### Step 6.4: Verify Script Functionality

Ensure remaining scripts still work:

```bash
# Test key scripts
python scripts/test_discovery.py --help
python scripts/validate_test_mapping.py
python scripts/list_papers.py --help
```

## Phase 7: Documentation Updates

### Step 7.1: Update Main README

Add section documenting available scripts:

```markdown
## Available Scripts

### Test Infrastructure
- `scripts/test_discovery.py` - Find tests for source files
- `scripts/validate_test_mapping.py` - Validate test structure
- `scripts/analyze_test_structure.py` - Analyze test organization

### Test Execution
- `scripts/run_prisma_tests.py` - Run PRISMA 2020 tests
- `scripts/test_stage.py` - Test individual workflow stages
- `scripts/test_database_health.py` - Test database connectors

### Development Tools
- `scripts/check_broken_imports.py` - Check for broken imports
- `scripts/check_test_status.py` - Quick test status check
- `scripts/visualize_project.py` - Generate project visualizations

### Utility Scripts
- `scripts/list_papers.py` - List papers from workflow
- `scripts/organize_outputs.py` - Organize output files
- `scripts/cleanup_project.py` - Clean up temporary files
```

### Step 7.2: Update tests/README.md

Document moved test files and update test discovery instructions.

### Step 7.3: Create Archive README

Create `scripts/archive/README.md` explaining archived scripts:

```markdown
# Archived Scripts

This directory contains scripts that are no longer actively used but kept for reference.

## migrate_tests.py

One-time migration tool used to reorganize tests. Archived after migration complete.
Kept for reference in case similar migration is needed in the future.
```

## Phase 8: Final Verification

### Step 8.1: Count Files

Verify file counts match expectations:

```bash
# Count scripts
find scripts -name "*.py" -type f | wc -l  # Should be 22

# Count tests
find tests -name "test_*.py" -type f | wc -l  # Should be 79 (75 + 4 moved)
```

### Step 8.2: Run Full Test Suite

Run full test suite to ensure nothing broke:

```bash
pytest tests/ -v --tb=short
```

### Step 8.3: Update Inventory Document

Update `TEST_AND_SCRIPT_INVENTORY.md` with final state:
- Mark removed files as REMOVED
- Update file counts
- Document cleanup completion

## Rollback Plan

If issues are discovered:

1. **Restore from backup branch**:
   ```bash
   git checkout main
   git branch -D cleanup/test-script-organization
   ```

2. **Or restore individual files**:
   ```bash
   git checkout HEAD~1 -- scripts/test_bibtex_acm_features.py
   ```

3. **Verify functionality restored**:
   ```bash
   pytest --collect-only
   python scripts/check_broken_imports.py
   ```

## Success Criteria

- [ ] 4 temporary scripts removed
- [ ] 4 test scripts moved to proper test directories
- [ ] 1 migration script archived
- [ ] All tests discoverable by pytest
- [ ] No broken imports
- [ ] Test suite passes
- [ ] Test mapping regenerated and accurate
- [ ] Documentation updated
- [ ] File counts match expectations (22 scripts, 79 tests)

## Post-Cleanup Tasks

1. **Monitor for issues**: Watch for any import errors or missing functionality
2. **Update CI/CD**: Ensure CI/CD pipelines work with new structure
3. **Team communication**: Notify team of changes
4. **Update onboarding docs**: Update any onboarding documentation

## Notes

- Keep git history for reference (don't use `git rm --cached`)
- All changes should be committed incrementally
- Test after each major change
- Document any deviations from plan
