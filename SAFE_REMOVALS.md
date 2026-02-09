# Safe Code Removals - Quick Reference

**Analysis Date:** 2026-02-08  
**Confidence:** High (based on 0% coverage + conservative analysis)

---

## Quick Decision Guide

Answer these questions to determine what to remove:

1. **Do you need manuscript export (PDF/Word/LaTeX)?** NO -> Remove Export & Citations
2. **Do you need quality assessment features?** NO -> Remove Quality module
3. **Do you use --cleanup or --test-stage CLI flags?** NO -> Remove Testing utilities
4. **Do you need git integration?** NO -> Remove Version Control
5. **Do you use all database connectors?** NO -> Refactor database_connectors.py

---

## Immediate Safe Removals

### Option A: Minimal Cleanup (Most Conservative)

Remove only unused variables (7 lines, 0 risk):

**Files to edit:**
1. `src/citations/csl_formatter.py:190` - remove unused 'style' variable
2. `src/orchestration/workflow_manager.py:4951` - remove unused 'end_stage' variable  
3. `src/orchestration/workflow_state.py:122` - remove unused 'from_phase' variable
4. `src/search/rate_limiter.py:133` - remove unused 'retry_state' variable
5. `src/utils/log_context.py:44` - remove unused 'exc_tb', 'exc_type', 'exc_val' variables

**Impact:** Negligible size reduction, but cleaner code
**Risk:** None
**Time:** 5 minutes

---

### Option B: Remove Manuscript Export Pipeline

If you don't need PDF/Word/LaTeX export functionality:

**Directories to delete:**
```bash
rm -rf src/export/          # 1,343 lines
rm -rf src/citations/       # 616 lines
```

**Files to delete:**
- src/export/latex_exporter.py
- src/export/submission_package.py
- src/export/word_exporter.py
- src/export/extraction_form_generator.py
- src/export/pandoc_converter.py
- src/export/manubot_exporter.py
- src/export/submission_checklist.py
- src/export/template_manager.py
- src/export/journal_selector.py
- src/export/__init__.py
- src/citations/citation_manager.py
- src/citations/bibtex_formatter.py
- src/citations/ieee_formatter.py
- src/citations/manubot_resolver.py
- src/citations/csl_formatter.py
- src/citations/ris_formatter.py
- src/citations/__init__.py

**After deletion, fix imports in:**
- `main.py` (lines 266, 449, 457, 491, 524)
- Any other files importing from export/citations

**Impact:** Remove 1,959 lines (14% of codebase)
**Risk:** Low (these are CLI features --manubot-export, --build-package)
**Time:** 15 minutes + testing

**How to verify it's safe:**
```bash
# Search for imports
rg "from.*export" src/ --type py
rg "from.*citations" src/ --type py
rg "import.*export" src/ --type py
rg "import.*citations" src/ --type py
```

---

### Option C: Remove Quality Assessment

If you don't need quality assessment features:

**Directory to delete:**
```bash
rm -rf src/quality/         # 801 lines
```

**Files to delete:**
- src/quality/auto_filler.py
- src/quality/risk_of_bias_assessor.py
- src/quality/study_type_detector.py
- src/quality/grade_assessor.py
- src/quality/template_generator.py
- src/quality/casp_prompts.py
- src/quality/quality_assessment_schemas.py
- src/quality/__init__.py

**After deletion, fix imports in:**
- `main.py` (if any)
- `src/orchestration/phases/quality_phase.py` (may need to delete this too)
- Any workflow config files

**Impact:** Remove 801 lines (6% of codebase)
**Risk:** Low (phase-based feature)
**Time:** 15 minutes + testing

**How to verify it's safe:**
```bash
rg "from.*quality" src/ --type py
rg "import.*quality" src/ --type py
rg "quality" config/ --type yaml
```

---

### Option D: Remove Testing Utilities

If you don't use --cleanup, --test-stage, or --validate-submission CLI flags:

**Files to delete:**
```bash
rm src/utils/workflow_cleaner.py              # 189 lines
rm src/validation/prisma_validator.py         # 157 lines
rm src/testing/stage_validators.py            # 110 lines
rm src/testing/stage_loader.py                # 61 lines
rm src/validation/__init__.py                 # 2 lines
```

**After deletion, fix:**
- `main.py` (lines 243, 369, 521)

**Impact:** Remove 519 lines (4% of codebase)
**Risk:** Very Low (CLI utilities only)
**Time:** 10 minutes

---

### Option E: Remove Version Control Integration

If you don't need git integration:

**Directory to delete:**
```bash
rm -rf src/version_control/    # 88 lines
```

**Files to delete:**
- src/version_control/git_manager.py
- src/version_control/ci_config.py
- src/version_control/__init__.py

**Impact:** Remove 88 lines (1% of codebase)
**Risk:** Very Low
**Time:** 5 minutes

---

## Recommended Approach

### Phase 1: Quick Wins (30 minutes)

```bash
# 1. Fix unused variables (edit 5 files)
# 2. Remove version control (if not needed)
rm -rf src/version_control/

# 3. Remove testing utilities (if not needed)
rm src/utils/workflow_cleaner.py
rm -rf src/validation/
rm -rf src/testing/

# 4. Fix imports in main.py
# Comment out or remove import statements for deleted modules
```

**Result:** ~600 lines removed, minimal risk

### Phase 2: Major Cleanup (1 hour)

```bash
# Only if you confirmed you don't need these features:

# Remove export pipeline
rm -rf src/export/
rm -rf src/citations/

# Remove quality assessment
rm -rf src/quality/

# Fix imports in main.py and other files
# Run tests to verify
```

**Result:** ~2,700 lines removed (20% reduction)

### Phase 3: Deep Refactoring (Later)

After Phase 1 & 2, consider refactoring:
1. `src/search/database_connectors.py` - remove unused connectors
2. `src/visualization/charts.py` - remove unused chart types
3. `src/orchestration/workflow_manager.py` - split into smaller modules

**Result:** Could remove another 2,000-4,000 lines

---

## Step-by-Step Removal Process

### 1. Backup First
```bash
git checkout -b cleanup/remove-dead-code
git commit -am "Backup before dead code removal"
```

### 2. Remove Files
```bash
# Example: Remove export pipeline
rm -rf src/export/
rm -rf src/citations/
```

### 3. Find and Fix Imports
```bash
# Find all imports
rg "from src.export" src/ --type py
rg "from src.citations" src/ --type py

# Edit files to remove or comment out imports
```

### 4. Update main.py
Remove or comment out:
- CLI flags for removed features
- Import statements
- Handler code for removed features

### 5. Run Tests
```bash
# Run all tests
pytest tests/ -v

# If tests fail, fix or remove tests for deleted features
```

### 6. Run Coverage Again
```bash
coverage run -m pytest tests/
coverage report

# Check that coverage improved
```

### 7. Commit Changes
```bash
git add -A
git commit -m "Remove dead code: export, citations, quality, testing utils

- Removed src/export/ (1,343 lines)
- Removed src/citations/ (616 lines)  
- Removed src/quality/ (801 lines)
- Removed src/testing/ and src/validation/ (405 lines)
- Fixed imports in main.py
- Removed CLI flags: --manubot-export, --build-package, --cleanup, --test-stage

Total reduction: 3,165 lines (23% of codebase)
Coverage improved from 15% to ~20%"
```

---

## Safety Checklist

Before removing any code, verify:

- [ ] Feature is not used in any CLI flags
- [ ] Feature is not referenced in config files
- [ ] No imports found in remaining code
- [ ] Tests still pass after removal
- [ ] Application runs without errors
- [ ] Coverage report doesn't show new missing imports

---

## What NOT to Remove

**DO NOT REMOVE these files even though they have 0% coverage:**

1. **Base classes** (may be inherited):
   - `src/agents/base_llm_agent.py`
   - `src/agents/base_writing_agent.py`
   - Check for subclasses before removing

2. **Phase definitions** (may be used via registry):
   - `src/orchestration/phases/*.py`
   - These may be loaded dynamically

3. **Observability** (may be used conditionally):
   - `src/observability/llm_metrics.py`
   - May be enabled via config

4. **State management** (may be used in other workflows):
   - `src/state/checkpoint_manager.py`
   - `src/state/state_store.py`

**INVESTIGATE FIRST before removing these.**

---

## Expected Results

### After Conservative Cleanup (Options A-E)
- **Lines removed:** ~3,300 (24%)
- **New codebase size:** ~10,500 lines
- **Coverage improvement:** 15% -> 20%
- **Maintenance burden:** Significantly reduced

### After Aggressive Cleanup (+ Refactoring)
- **Lines removed:** ~6,000-8,000 (43-58%)
- **New codebase size:** ~5,800-7,800 lines  
- **Coverage improvement:** 15% -> 30-40%
- **Maintenance burden:** Much lighter, cleaner architecture

---

## Files Reference

### Export Pipeline (1,343 lines total)
```
src/export/latex_exporter.py              264
src/export/submission_package.py          167
src/export/word_exporter.py               160
src/export/extraction_form_generator.py    97
src/export/pandoc_converter.py             85
src/export/manubot_exporter.py             76
src/export/submission_checklist.py         64
src/export/template_manager.py             52
src/export/journal_selector.py             47
src/export/__init__.py                      9
```

### Citations (616 lines total)
```
src/citations/citation_manager.py         142
src/citations/bibtex_formatter.py         122
src/citations/ieee_formatter.py           104
src/citations/manubot_resolver.py         100
src/citations/csl_formatter.py             83
src/citations/ris_formatter.py             62
src/citations/__init__.py                   7
```

### Quality Assessment (801 lines total)
```
src/quality/auto_filler.py                278
src/quality/risk_of_bias_assessor.py      95
src/quality/study_type_detector.py        93
src/quality/grade_assessor.py             72
src/quality/template_generator.py         47
src/quality/casp_prompts.py               44
src/quality/quality_assessment_schemas.py  43
src/quality/__init__.py                     6
```

### Testing/Validation (519 lines total)
```
src/utils/workflow_cleaner.py             189
src/validation/prisma_validator.py        157
src/testing/stage_validators.py           110
src/testing/stage_loader.py                61
src/validation/__init__.py                  2
```

### Version Control (88 lines total)
```
src/version_control/git_manager.py         59
src/version_control/ci_config.py           27
src/version_control/__init__.py             2
```

---

**Total Safe Removals: 3,367 lines (24% of codebase)**

---

## Questions?

If unsure about any removal:
1. Search for usage: `rg "module_name" src/ --type py`
2. Check git history: `git log -- path/to/file.py`
3. Review when it was last modified
4. Check if referenced in documentation
5. When in doubt, DON'T remove - mark as TODO for later investigation

---

**See DEAD_CODE_ANALYSIS.md for full detailed analysis**
