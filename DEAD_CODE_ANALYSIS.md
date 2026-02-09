# Dead Code Analysis Report

**Generated:** 2026-02-08  
**Analysis Method:** Combined Runtime Coverage (coverage.py) + Static Analysis (vulture)  
**Command Tested:** `python main.py --debug --log-file logs/test.log --force-fresh`  
**Confidence Level:** Conservative (100% confidence for vulture findings)

---

## Executive Summary

**Total Code Coverage:** 15.17%  
**Unused Code Identified:** 3,938 lines in 51 files (0% coverage)  
**Mostly Unused Code:** 7,136 lines in 25 files (<20% coverage)  
**Total Potential Reduction:** ~11,074 lines (80% of codebase never executed)

---

## High-Confidence Removals

### Category 1: Completely Unused Files (0% Coverage)

These files were never imported or executed during the test run. They represent the safest candidates for removal.

#### Export/Submission Pipeline (1,343 lines)
These files appear to be for manuscript export functionality that wasn't triggered:

- `src/export/latex_exporter.py` (264 lines) - LaTeX export functionality
- `src/export/submission_package.py` (167 lines) - Submission package builder
- `src/export/word_exporter.py` (160 lines) - Word document export
- `src/export/extraction_form_generator.py` (97 lines) - Form generation
- `src/export/pandoc_converter.py` (85 lines) - Pandoc conversion wrapper
- `src/export/manubot_exporter.py` (76 lines) - Manubot integration
- `src/export/submission_checklist.py` (64 lines) - Checklist generator
- `src/export/template_manager.py` (52 lines) - Template management
- `src/export/journal_selector.py` (47 lines) - Journal selection
- `src/export/__init__.py` (9 lines)

**Recommendation:** These are CLI-only features (--manubot-export, --build-package). If you don't need manuscript export, SAFE TO REMOVE. Otherwise, KEEP but exclude from coverage.

#### Quality Assessment (801 lines)
Quality assessment functionality that wasn't used:

- `src/quality/auto_filler.py` (278 lines) - LLM-based quality assessment
- `src/quality/risk_of_bias_assessor.py` (95 lines) - Risk of bias assessment
- `src/quality/study_type_detector.py` (93 lines) - Study type detection
- `src/quality/grade_assessor.py` (72 lines) - GRADE assessment
- `src/quality/template_generator.py` (47 lines) - QA template generation
- `src/quality/casp_prompts.py` (44 lines) - CASP prompts
- `src/quality/quality_assessment_schemas.py` (43 lines) - QA schemas
- `src/quality/__init__.py` (6 lines)

**Recommendation:** Quality assessment is likely a workflow phase that wasn't reached. Check if quality phase is needed. If not, SAFE TO REMOVE.

#### Citations/Bibliography (616 lines)
Citation formatting that wasn't used:

- `src/citations/citation_manager.py` (142 lines) - Citation management
- `src/citations/bibtex_formatter.py` (122 lines) - BibTeX formatting
- `src/citations/ieee_formatter.py` (104 lines) - IEEE citation style
- `src/citations/manubot_resolver.py` (100 lines) - Manubot citation resolver
- `src/citations/csl_formatter.py` (83 lines) - CSL formatting
- `src/citations/ris_formatter.py` (62 lines) - RIS format
- `src/citations/__init__.py` (7 lines)

**Recommendation:** Citation functionality tied to export pipeline. If keeping export features, KEEP. Otherwise SAFE TO REMOVE.

#### Testing/Validation Utilities (405 lines)
Testing infrastructure that's separate from pytest:

- `src/utils/workflow_cleaner.py` (189 lines) - Workflow cleanup utility
- `src/validation/prisma_validator.py` (157 lines) - PRISMA validation
- `src/testing/stage_validators.py` (110 lines) - Stage validation
- `src/testing/stage_loader.py` (61 lines) - Stage loading for tests
- `src/validation/__init__.py` (2 lines)

**Recommendation:** These are CLI utilities (--cleanup, --test-stage). SAFE TO REMOVE if not using these CLI features.

#### Orchestration/Workflow Infrastructure (447 lines)
Workflow features that weren't used:

- `src/orchestration/workflow_graph.py` (180 lines) - Workflow graph/DAG
- `src/state/checkpoint_manager.py` (77 lines) - State checkpoint manager (duplicate?)
- `src/orchestration/phases/screening_phase.py` (83 lines) - Screening phase
- `src/orchestration/phases/search_phase.py` (73 lines) - Search phase
- `src/orchestration/phases/writing_phase.py` (65 lines) - Writing phase  
- `src/orchestration/error_boundary.py` (53 lines) - Error boundary pattern
- `src/orchestration/phases/export_phase.py` (53 lines) - Export phase
- `src/orchestration/phases/__init__.py` (46 lines) - Phase definitions
- `src/orchestration/phases/extraction_phase.py` (23 lines) - Extraction phase
- `src/orchestration/phases/quality_phase.py` (23 lines) - Quality phase
- `src/orchestration/workflow_state.py` (12 lines) - Workflow state
- `src/state/state_store.py` (48 lines) - State storage
- `src/state/__init__.py` (3 lines)

**Recommendation:** These phases exist but weren't executed. This suggests the workflow may have loaded from checkpoints or skipped phases. INVESTIGATE before removing - may be needed for full workflow runs.

#### Version Control/CI (88 lines)
Version control features not used:

- `src/version_control/git_manager.py` (59 lines) - Git integration
- `src/version_control/ci_config.py` (27 lines) - CI configuration
- `src/version_control/__init__.py` (2 lines)

**Recommendation:** If not using git integration features, SAFE TO REMOVE.

#### PRISMA Generation (73 lines)
- `src/prisma/checklist_generator.py` (73 lines) - PRISMA checklist

**Recommendation:** Likely part of export phase. If keeping PRISMA diagram generation, KEEP. Otherwise SAFE TO REMOVE.

#### Base Agent Classes (72 lines)
- `src/agents/base_llm_agent.py` (52 lines) - Base LLM agent
- `src/agents/base_writing_agent.py` (17 lines) - Base writing agent
- `src/agents/__init__.py` (3 lines)

**Recommendation:** INVESTIGATE - These are base classes. They may be imported but not directly executed. DO NOT REMOVE without checking inheritance.

---

### Category 2: Mostly Unused Files (<20% Coverage)

These files have some usage but are largely unused. Review carefully before removal.

#### Critical Files (Keep but Refactor)
- `src/orchestration/workflow_manager.py` (11.3% coverage, 2195 lines) - **CRITICAL: Core workflow - DO NOT REMOVE**
- `src/search/database_connectors.py` (5.6% coverage, 1434 lines) - **CRITICAL: Database search - Refactor unused connectors**
- `src/visualization/charts.py` (6.0% coverage, 531 lines) - Chart generation - mostly unused
- `src/screening/title_abstract_agent.py` (9.5% coverage, 232 lines) - Screening agent - partially used
- `src/prisma/prisma_generator.py` (16.9% coverage, 207 lines) - PRISMA diagram - partially used

**Recommendation:** These are core features. Do NOT remove files, but consider:
1. Removing unused database connectors within database_connectors.py
2. Removing unused chart types from charts.py
3. Reviewing unused methods in screening agents

---

## Static Analysis Findings (Vulture)

### Unused Variables (100% Confidence)

These variables are assigned but never used - safe to remove:

1. `src/citations/csl_formatter.py:190` - unused variable 'style'
2. `src/orchestration/workflow_manager.py:4951` - unused variable 'end_stage'
3. `src/orchestration/workflow_state.py:122` - unused variable 'from_phase'
4. `src/search/rate_limiter.py:133` - unused variable 'retry_state'
5. `src/utils/log_context.py:44` - unused variables 'exc_tb', 'exc_type', 'exc_val' (exception tuple)

**Recommendation:** SAFE TO REMOVE - These are simple variable removals with no side effects.

---

## Actionable Recommendations

### Phase 1: Immediate Safe Removals (Conservative)

Remove these files if you confirm you don't need the features:

**If you don't need manuscript export functionality:**
- Delete entire `src/export/` directory (1,343 lines)
- Delete entire `src/citations/` directory (616 lines)
- **Savings: 1,959 lines (14% of codebase)**

**If you don't need quality assessment:**
- Delete entire `src/quality/` directory (801 lines)
- **Savings: 801 lines (6% of codebase)**

**If you don't need testing utilities:**
- Delete `src/validation/prisma_validator.py`
- Delete `src/testing/stage_validators.py` and `stage_loader.py`
- Delete `src/utils/workflow_cleaner.py`
- **Savings: 405 lines (3% of codebase)**

**If you don't need version control features:**
- Delete entire `src/version_control/` directory (88 lines)
- **Savings: 88 lines (1% of codebase)**

**Remove unused variables:**
- Fix 7 variable assignments in 5 files
- **Savings: 7 lines**

**Total Phase 1 Savings: Up to 3,260 lines (24% of codebase)**

### Phase 2: Investigative Removals (Requires Review)

1. **Review workflow phases:** Why weren't screening/search/writing/quality phases executed?
   - Check if workflow_manager bypasses these due to checkpoints
   - If phases are truly unused, remove phase files (417 lines)

2. **Review base agent classes:**
   - Check if any concrete agents inherit from these
   - If no inheritance, remove (72 lines)

3. **Review orchestration infrastructure:**
   - `workflow_graph.py` (180 lines) - Is DAG/graph functionality used?
   - `error_boundary.py` (53 lines) - Is error boundary pattern used?
   - If not, remove (233 lines)

**Potential Phase 2 Savings: 722 lines (5% of codebase)**

### Phase 3: Refactoring (Requires Code Changes)

1. **Refactor database_connectors.py:**
   - 94.4% of code unused (1,354 of 1,434 lines)
   - Keep only active connectors
   - Extract unused connectors to separate optional module

2. **Refactor charts.py:**
   - 94% of code unused (499 of 531 lines)  
   - Keep only charts actually generated
   - Consider lazy loading for chart types

3. **Refactor workflow_manager.py:**
   - 88.7% of code unused (1,948 of 2,195 lines)
   - Significant complexity, may have many conditional branches
   - Consider splitting into smaller modules

**Potential Phase 3 Savings: Could reduce another 3,000+ lines through refactoring**

---

## Safety Notes

### Do NOT Remove Without Investigation

1. **Files imported via reflection/dynamic imports:** Check for `importlib.import_module()` usage
2. **CLI-only features:** Features triggered by flags (--manubot-export, --cleanup, etc.)
3. **Checkpoint-skipped code:** Workflow may load from checkpoints, skipping phases
4. **Template files:** Config files, templates that aren't executed but are read
5. **Base classes:** Even with 0% coverage, may be inherited by concrete classes
6. **Exception handlers:** Code in `except` blocks won't show coverage if no errors occurred

### Validation Steps Before Removal

1. **Search for imports:** `rg "from.*<module_name>" --type py`
2. **Search for string references:** `rg "<module_name>" --type py`
3. **Check CLI flags:** Review main.py argument parser
4. **Check config files:** Review YAML configs for references
5. **Run full test suite:** Ensure tests still pass after removal
6. **Test all CLI flags:** Test features like --manubot-export, --build-package

---

## Implementation Plan

### Step 1: Confirm Feature Requirements
Ask yourself:
- Do I need manuscript export? (PDF/Word/LaTeX)
- Do I need quality assessment?  
- Do I need citation formatting?
- Do I need testing utilities (--cleanup, --test-stage)?
- Do I need version control integration?

### Step 2: Remove Confirmed Unused Features
Start with directories that are completely unused (0% coverage):
```bash
# Example: Remove export functionality
rm -rf src/export/
rm -rf src/citations/

# Update imports in remaining files
rg "from.*export" --type py  # Find and fix import statements
rg "from.*citations" --type py
```

### Step 3: Fix Unused Variables
Remove the 7 unused variables identified by vulture:
- Review each file
- Delete or use the variable
- Run tests to confirm no side effects

### Step 4: Run Tests
```bash
# Run full test suite
pytest tests/ -v

# Run coverage again
coverage run -m pytest tests/
coverage report
```

### Step 5: Commit Changes
```bash
git add -A
git commit -m "Remove dead code: export, citations, quality assessment modules"
```

---

## Estimated Impact

**Before Cleanup:**
- Total: 13,821 lines of code
- Coverage: 15.17%
- Unused: ~11,074 lines (80%)

**After Conservative Cleanup (Phase 1):**
- Remove: 3,260 lines
- Remaining: 10,561 lines  
- Expected coverage: ~20%

**After Aggressive Cleanup (Phases 1-3):**
- Remove: 6,000-8,000 lines
- Remaining: 5,800-7,800 lines
- Expected coverage: 30-40%
- **Codebase size reduction: 43-58%**

---

## Next Steps

1. **Review this report** and confirm which features you actually need
2. **Start with Phase 1** - safe, conservative removals
3. **Update documentation** to reflect removed features
4. **Update tests** to remove tests for deleted features
5. **Run coverage again** to validate improvements
6. **Consider Phase 2/3** for deeper refactoring

---

## Appendix: Full File List

### Files with 0% Coverage (51 files)

```
src/quality/auto_filler.py                        278 lines
src/export/latex_exporter.py                      264 lines
src/utils/workflow_cleaner.py                     189 lines
src/orchestration/workflow_graph.py               180 lines
src/export/submission_package.py                  167 lines
src/export/word_exporter.py                       160 lines
src/validation/prisma_validator.py                157 lines
src/citations/citation_manager.py                 142 lines
src/observability/llm_metrics.py                  128 lines
src/citations/bibtex_formatter.py                 122 lines
src/testing/stage_validators.py                   110 lines
src/citations/ieee_formatter.py                   104 lines
src/citations/manubot_resolver.py                 100 lines
src/export/extraction_form_generator.py            97 lines
src/quality/risk_of_bias_assessor.py               95 lines
src/quality/study_type_detector.py                 93 lines
src/export/pandoc_converter.py                     85 lines
src/citations/csl_formatter.py                     83 lines
src/orchestration/phases/screening_phase.py        83 lines
src/state/checkpoint_manager.py                    77 lines
src/export/manubot_exporter.py                     76 lines
src/orchestration/phases/search_phase.py           73 lines
src/prisma/checklist_generator.py                  73 lines
src/quality/grade_assessor.py                      72 lines
src/orchestration/phases/writing_phase.py          65 lines
src/export/submission_checklist.py                 64 lines
src/citations/ris_formatter.py                     62 lines
src/testing/stage_loader.py                        61 lines
src/version_control/git_manager.py                 59 lines
src/orchestration/error_boundary.py                53 lines
src/orchestration/phases/export_phase.py           53 lines
src/agents/base_llm_agent.py                       52 lines
src/export/template_manager.py                     52 lines
src/state/state_store.py                           48 lines
src/export/journal_selector.py                     47 lines
src/quality/template_generator.py                  47 lines
src/orchestration/phases/__init__.py               46 lines
src/quality/casp_prompts.py                        44 lines
src/quality/quality_assessment_schemas.py          43 lines
src/version_control/ci_config.py                   27 lines
src/orchestration/phases/extraction_phase.py       23 lines
src/orchestration/phases/quality_phase.py          23 lines
src/agents/base_writing_agent.py                   17 lines
src/orchestration/workflow_state.py               12 lines
src/export/__init__.py                              9 lines
src/citations/__init__.py                           7 lines
src/quality/__init__.py                             6 lines
src/agents/__init__.py                              3 lines
src/state/__init__.py                               3 lines
src/validation/__init__.py                          2 lines
src/version_control/__init__.py                     2 lines

TOTAL: 3,938 lines
```

### Files with <20% Coverage (Top 20)

```
src/orchestration/workflow_manager.py            11.3%  2195 lines
src/search/database_connectors.py                 5.6%  1434 lines
src/visualization/charts.py                       6.0%   531 lines
src/screening/title_abstract_agent.py             9.5%   232 lines
src/prisma/prisma_generator.py                   16.9%   207 lines
src/search/search_strategy.py                    19.4%   186 lines
src/orchestration/checkpoint_manager.py          10.8%   167 lines
src/utils/pdf_retriever.py                       11.6%   164 lines
src/extraction/data_extractor_agent.py           14.5%   159 lines
src/deduplication.py                             11.6%   138 lines
src/search/proxy_manager.py                      18.8%   138 lines
src/search/connectors/google_scholar_connector.py 13.1%  137 lines
src/tools/table_generator_tool.py                10.3%   136 lines
src/orchestration/database_connector_factory.py  13.4%   127 lines
src/search/search_logger.py                      17.6%   125 lines
src/screening/fulltext_agent.py                  13.9%   115 lines
src/writing/results_agent.py                      9.8%   112 lines
src/search/author_service.py                     11.7%   111 lines
src/enrichment/paper_enricher.py                 16.3%    98 lines
src/writing/style_pattern_extractor.py           18.4%    98 lines
```

---

**Report Generated by Dead Code Analysis Tool**  
**Coverage Report:** [htmlcov/index.html](htmlcov/index.html)  
**Raw Coverage Data:** coverage.json  
**Vulture Report:** vulture_report.txt
