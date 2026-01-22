# Test and Script Inventory

## Executive Summary

This document provides a comprehensive inventory of all test files and scripts in the research-article-writer project.

**Note on Methodology:**
- Files marked with ✓ were read directly (docstrings and key sections analyzed)
- Files marked with ~ were analyzed via docstring extraction and file structure
- All recommendations are based on analysis of purpose, usage patterns, and code structure

**Total Files:**
- **Scripts**: 31 files
- **Test Files**: 75 files
- **Total**: 106 files

**Categories:**
- **Test Infrastructure Scripts**: 4 files
- **Test Execution Scripts**: 8 files
- **Development Tools**: 5 files
- **Data Generation Scripts**: 2 files
- **Workflow Testing Scripts**: 7 files
- **Utility Scripts**: 5 files
- **Unit Tests**: 50+ files
- **Integration Tests**: 20+ files
- **E2E Tests**: 5 files

---

## Scripts Inventory

### Test Infrastructure Scripts

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/analyze_test_structure.py` | Analyzes test structure and creates mapping to source files | **KEEP** | Essential for test organization, generates `data/test_mapping.json` |
| `scripts/test_discovery.py` | Find tests for source files, identify missing tests, generate coverage reports | **KEEP** | Core tool for test discovery and maintenance |
| `scripts/validate_test_mapping.py` | Validates test structure, naming conventions, and mappings | **KEEP** | Used by pre-commit hooks, ensures test quality |
| `scripts/migrate_tests.py` | Helper to migrate tests to new structure mirroring src/ | **CONSOLIDATE** | One-time migration tool, can be archived after migration complete |

### Test Execution Scripts

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/run_prisma_tests.py` | Test runner for PRISMA 2020 tests, generates reports | **KEEP** | Used by `make test-prisma`, recurring usage |
| `scripts/run_e2e_tests.sh` | Bash script for comprehensive E2E test suite | **KEEP** | Useful for CI/CD, runs multiple test suites |
| `scripts/test_full_workflow.py` | Script that runs workflow tests and validates outputs | **KEEP** | Different from `tests/e2e/test_full_workflow.py` - this is a test execution script, not a test file |
| `scripts/test_workflow_e2e_comprehensive.py` | Comprehensive E2E workflow test script | **CONSOLIDATE** | Contains test functions but should be pytest tests in `tests/e2e/` |
| `scripts/test_checkpoint_workflow.py` | Script that tests checkpoint/resume functionality | **KEEP** | Test execution script, useful for manual testing |
| `scripts/test_stage.py` | CLI tool to test individual workflow stages | **KEEP** | Useful development tool, used by `python main.py --test-stage` |
| `scripts/test_database_health.py` | Tests all database connectors and reports status | **KEEP** | Useful utility, used by `python main.py --test-databases` |
| `scripts/test_manuscript_pipeline_e2e.py` | E2E test for manuscript pipeline (Phases 17-18) | **CONSOLIDATE** | Should be in `tests/e2e/` instead |

### Development Tools

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/check_broken_imports.py` | Analyzes Python files for broken imports and circular dependencies | **KEEP** | Useful for code quality checks |
| `scripts/check_test_status.py` | Quick test status check without running full tests | **KEEP** | Used by `make test-status`, recurring usage |
| `scripts/check_workflow_progress.py` | Check workflow progress and verify PRISMA outputs | **KEEP** | Useful utility for monitoring workflows |
| `scripts/analyze_dependencies.py` | Analyzes Python project dependencies and generates visualization | **KEEP** | Useful for understanding project structure |
| `scripts/visualize_project.py` | Generates multiple visualizations of project structure | **KEEP** | Useful for documentation and understanding |

### Data Generation Scripts

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/generate_test_data.py` | Generate test fixtures from checkpoints or create mock data | **KEEP** | Useful for test data generation |
| `scripts/generate_ieee_readiness_report.py` | Comprehensive status report checking IEEE compliance | **KEEP** | Useful for compliance checking |

### Workflow Testing Scripts

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/test_bibtex_acm_features.py` | Manual test script for BibTeX and ACM features | **REMOVE** | Temporary testing script, functionality covered by unit tests |
| `scripts/test_enrichment_and_visualizations.py` | Tests paper enrichment and visualization regeneration | **CONSOLIDATE** | Should be in `tests/integration/` instead |
| `scripts/test_humanization_integration.py` | Verifies humanization integration components | **CONSOLIDATE** | Should be in `tests/integration/` instead |
| `scripts/test_improved_scrapers.py` | Compares data quality before/after scraper improvements | **REMOVE** | Temporary testing script, one-off analysis |
| `scripts/validate_checkpoints.py` | Validates checkpoint files from workflow runs | **KEEP** | Useful utility for checkpoint validation |
| `scripts/validate_prisma_compliance.py` | Validates reports against PRISMA 2020 checklist | **KEEP** | Wrapper around `src.validation.prisma_validator`, useful CLI |
| `scripts/validate_workflow_outputs.py` | Validates outputs from workflow (papers, PRISMA, sections) | **KEEP** | Useful utility for output validation |
| `scripts/verify_enhanced_structure.py` | Tests enhanced code produces expected structure | **REMOVE** | Temporary verification script, one-off |

### Utility Scripts

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `scripts/auto_fill_quality_assessments.py` | Automatically fill quality assessments using LLM | **KEEP** | Useful utility for quality assessment automation |
| `scripts/list_papers.py` | List all papers found in workflow | **KEEP** | Useful CLI tool, recurring usage |
| `scripts/organize_outputs.py` | Organize orphaned output files into workflow directories | **KEEP** | Useful maintenance script |
| `scripts/cleanup_project.py` | Removes unnecessary files (__pycache__, coverage, etc.) | **KEEP** | Useful maintenance script |
| `scripts/remediate_current_paper.py` | One-shot script to fix current final_report.md | **REMOVE** | One-off remediation script, no longer needed |

---

## Tests Inventory

### Unit Tests (`tests/unit/`)

#### Core Infrastructure Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_abstract_agent.py` | AbstractGenerator | PRISMA 2020 abstract format | **KEEP** | Tests abstract generation |
| `test_circuit_breaker.py` | CircuitBreaker | Circuit breaker pattern | **KEEP** | Tests resilience patterns |
| `test_config_loader.py` | ConfigLoader | Configuration loading | **KEEP** | Tests config management |
| `test_debug_config.py` | DebugConfig | Debug configuration | **KEEP** | Tests debug settings |
| `test_handoff_protocol.py` | HandoffProtocol | Agent handoff mechanism | **KEEP** | Tests orchestration |
| `test_log_context.py` | LogContext | Logging context | **KEEP** | Tests logging utilities |
| `test_logging_config.py` | LoggingConfig | Logging setup | **KEEP** | Tests logging configuration |
| `test_rate_limiter.py` | RateLimiter | Rate limiting | **KEEP** | Tests API rate limiting |
| `test_retry_strategies.py` | RetryStrategies | Retry logic | **KEEP** | Tests resilience patterns |
| `test_state_serialization.py` | StateSerializer | State serialization | **KEEP** | Tests state management |
| `test_tool_registry.py` | ToolRegistry | Tool registration | **KEEP** | Tests tool system |
| `test_topic_propagator.py` | TopicContext | Topic propagation | **KEEP** | Tests topic management |

#### Search Module Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_database_connectors.py` | DatabaseConnectors | All database connectors | **KEEP** | Core search functionality |
| `test_search_logger.py` | SearchLogger | Search logging | **KEEP** | Tests search logging |
| `test_search_strategy.py` | SearchStrategyBuilder | Search strategy building | **KEEP** | Tests search strategy |
| `search/test_author_service.py` | AuthorService | Author information | **KEEP** | Tests author services |
| `search/test_citation_network.py` | CitationNetwork | Citation networks | **KEEP** | Tests citation analysis |
| `search/test_google_scholar_connector.py` | GoogleScholarConnector | Google Scholar connector | **KEEP** | Tests specific connector |

#### Screening & Extraction Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_fulltext_agent.py` | FullTextScreener | Full-text screening | **KEEP** | Tests screening agent |
| `test_deduplication.py` | Deduplicator | Paper deduplication | **KEEP** | Tests deduplication logic |
| `test_extraction_form_generator.py` | ExtractionFormGenerator | Extraction forms | **KEEP** | Tests form generation |

#### Citations Module Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `citations/test_bibtex_formatter.py` | BibTeXFormatter | BibTeX formatting | **KEEP** | Tests citation formatting |
| `citations/test_citation_manager.py` | CitationManager | Citation management | **KEEP** | Core citation functionality |
| `citations/test_citation_manager_integration.py` | CitationManager | Integration tests | **KEEP** | Integration tests |
| `citations/test_csl_formatter.py` | CSLFormatter | CSL formatting | **KEEP** | Tests CSL format |
| `citations/test_ieee_formatter.py` | IEEEFormatter | IEEE formatting | **KEEP** | Tests IEEE format |
| `citations/test_manubot_resolver.py` | ManubotCitationResolver | Manubot resolution | **KEEP** | Tests citation resolution |

#### Export Module Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `export/test_journal_selector.py` | JournalSelector | Journal selection | **KEEP** | Tests journal matching |
| `export/test_manubot_exporter.py` | ManubotExporter | Manubot export | **KEEP** | Tests export functionality |
| `export/test_pandoc_converter.py` | PandocConverter | Pandoc conversion | **KEEP** | Tests document conversion |
| `export/test_submission_checklist.py` | SubmissionChecklist | Submission checklist | **KEEP** | Tests checklist generation |
| `export/test_submission_package.py` | SubmissionPackageBuilder | Submission packages | **KEEP** | Tests package creation |
| `export/test_template_manager.py` | TemplateManager | Template management | **KEEP** | Tests template system |

#### Orchestration Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `orchestration/test_checkpoint_manager.py` | CheckpointManager | Checkpoint management | **KEEP** | Tests orchestration checkpoints |
| `orchestration/test_phase_executor.py` | PhaseExecutor | Phase execution | **KEEP** | Tests phase execution |
| `orchestration/test_phase_registry.py` | PhaseRegistry | Phase registry | **KEEP** | Tests phase system |

#### Quality & Assessment Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_prisma_checklist_generator.py` | PRISMAChecklistGenerator | PRISMA checklist | **KEEP** | Tests checklist generation |
| `test_prisma_validator.py` | PRISMAValidator | PRISMA validation | **KEEP** | Tests PRISMA compliance |
| `test_quality_assessment.py` | QualityAssessment | Quality assessment | **KEEP** | Tests quality modules |
| `test_paper_enricher.py` | PaperEnricher | Paper enrichment | **KEEP** | Tests enrichment |

#### Writing & Visualization Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_writing_agents.py` | WritingAgents | All writing agents | **KEEP** | Tests writing functionality |
| `test_visualization.py` | ChartGenerator | Visualization charts | **KEEP** | Tests visualization |
| `test_manuscript_error_handling.py` | ManuscriptErrorHandling | Error handling | **KEEP** | Cross-module error tests |

#### Schema & Validation Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_schemas.py` | ExtractionSchemas | Pydantic schemas | **KEEP** | Tests data schemas |
| `test_stage_validators.py` | StageValidators | Stage validation | **KEEP** | Tests validation |

#### Observability Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_observability.py` | MetricsCollector, CostTracker | Observability | **KEEP** | Tests metrics and costs |
| `test_llm_providers.py` | LLMProviders | LLM integrations | **KEEP** | Tests LLM providers |

#### State Management Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_state_management.py` | CheckpointManager (state), FileStateStore | State management | **KEEP** | Tests src/state modules |

#### Version Control Tests

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `version_control/test_git_manager.py` | GitManager | Git operations | **KEEP** | Tests version control |

### Integration Tests (`tests/integration/`)

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_agent_extraction.py` | DataExtractorAgent | Extraction workflow | **KEEP** | Tests extraction integration |
| `test_agent_llm_providers.py` | LLMProviders | LLM provider integration | **KEEP** | Tests LLM integration |
| `test_agent_screening.py` | ScreeningAgents | Screening workflow | **KEEP** | Tests screening integration |
| `test_backward_compatibility.py` | BackwardCompatibility | API compatibility | **KEEP** | Tests compatibility |
| `test_bibliometric_integration.py` | BibliometricEnricher | Bibliometric features | **KEEP** | Tests bibliometric integration |
| `test_checkpoint_manuscript_phases.py` | CheckpointManuscriptPhases | Manuscript checkpoints | **KEEP** | Tests manuscript checkpoints |
| `test_checkpoint_resumption.py` | CheckpointResumption | Checkpoint resumption | **KEEP** | Tests resumption |
| `test_cli_manuscript.py` | CLIManuscript | CLI manuscript features | **KEEP** | Tests CLI integration |
| `test_manuscript_pipeline.py` | ManuscriptPipeline | Manuscript pipeline | **KEEP** | Tests pipeline |
| `test_observability_integration.py` | ObservabilityIntegration | Observability | **KEEP** | Tests observability |
| `test_prisma_checklist_generation.py` | PRISMAChecklistGeneration | PRISMA checklist | **KEEP** | Tests checklist generation |
| `test_prisma_with_real_data.py` | PRISMAWithRealData | PRISMA with real data | **KEEP** | Tests with real data |
| `test_real_database_connectors.py` | RealDatabaseConnectors | Real connectors | **KEEP** | Tests real connectors |
| `test_search_strategy_export.py` | SearchStrategyExport | Search strategy export | **KEEP** | Tests export |
| `test_search_workflow.py` | SearchWorkflow | Search workflow | **KEEP** | Tests search workflow |
| `test_state_persistence.py` | StatePersistence | State persistence | **KEEP** | Tests persistence |
| `test_tool_execution.py` | ToolExecution | Tool execution | **KEEP** | Tests tool system |
| `test_workflow_manuscript_integration.py` | WorkflowManuscriptIntegration | Workflow integration | **KEEP** | Tests workflow |
| `test_workflow_phases.py` | WorkflowPhases | Workflow phases | **KEEP** | Tests phases |
| `test_workflow_registry_integration.py` | WorkflowRegistryIntegration | Workflow registry | **KEEP** | Tests registry |
| `test_writing_workflow.py` | WritingWorkflow | Writing workflow | **KEEP** | Tests writing |

### E2E Tests (`tests/e2e/`)

| File | Tests | Coverage | Status | Notes |
|------|-------|----------|--------|-------|
| `test_error_recovery.py` | ErrorRecovery | Error handling E2E | **KEEP** | Tests error recovery |
| `test_full_workflow.py` | FullWorkflow | Complete workflow | **KEEP** | Core E2E test |
| `test_full_workflow_real_databases.py` | FullWorkflowRealDatabases | Real database E2E | **KEEP** | Tests with real APIs |
| `test_manuscript_workflow.py` | ManuscriptWorkflow | Manuscript E2E | **KEEP** | Tests manuscript E2E |
| `test_workflow_with_state_persistence.py` | WorkflowStatePersistence | State persistence E2E | **KEEP** | Tests persistence E2E |

---

## Recommendations Summary

### Scripts to Remove (4 files)

1. **`scripts/test_bibtex_acm_features.py`** - Temporary testing script, functionality covered by unit tests
2. **`scripts/test_improved_scrapers.py`** - Temporary testing script, one-off analysis
3. **`scripts/verify_enhanced_structure.py`** - Temporary verification script, one-off
4. **`scripts/remediate_current_paper.py`** - One-off remediation script, no longer needed

### Scripts to Consolidate (5 files)

1. **`scripts/migrate_tests.py`** - Archive after migration complete
2. **`scripts/test_workflow_e2e_comprehensive.py`** - Move to `tests/e2e/test_workflow_comprehensive.py`
3. **`scripts/test_enrichment_and_visualizations.py`** - Move to `tests/integration/test_enrichment_and_visualizations.py`
4. **`scripts/test_humanization_integration.py`** - Move to `tests/integration/test_humanization_integration.py`
5. **`scripts/test_manuscript_pipeline_e2e.py`** - Move to `tests/e2e/test_manuscript_pipeline_e2e.py`

**Note**: `scripts/test_full_workflow.py` and `scripts/test_checkpoint_workflow.py` are test execution scripts (not test files), so they should be KEPT as utility scripts.

### Tests to Keep (All 75 files)

All test files are recommended to **KEEP** as they provide valuable coverage:
- Unit tests provide isolated component testing
- Integration tests verify component interactions
- E2E tests validate complete workflows
- No redundant test files identified (after recent cleanup)

### Scripts to Keep (21 files)

All remaining scripts serve important purposes:
- Test infrastructure scripts support test organization
- Test execution scripts provide test running capabilities
- Development tools aid in code quality and debugging
- Utility scripts provide useful maintenance functions

---

## Action Plan

### Phase 1: Verification (Complete File Review)

**Goal**: Verify all 106 files and update inventory with accurate information

**Steps**:
1. Read remaining unverified script files (~5-6 files)
2. Read remaining unverified test files (~10-15 files)
3. Update inventory document with:
   - Verification status (✓ Verified / ~ Analyzed / ? Needs Review)
   - Line counts
   - Test function counts (for test files)
   - Dependencies
   - Usage indicators

**Output**: Updated inventory document with 100% verified information

### Phase 2: Immediate Cleanup Actions

#### 2.1 Remove Temporary Scripts (4 files)
**Confidence**: High - These are clearly temporary/one-off scripts

1. `scripts/test_bibtex_acm_features.py` - Temporary testing script
2. `scripts/test_improved_scrapers.py` - Temporary testing script
3. `scripts/verify_enhanced_structure.py` - Temporary verification script
4. `scripts/remediate_current_paper.py` - One-off remediation script

#### 2.2 Move Test Scripts to Proper Locations (4 files)
**Confidence**: High - These contain test logic and should be pytest tests

1. `scripts/test_workflow_e2e_comprehensive.py` → `tests/e2e/test_workflow_comprehensive.py`
2. `scripts/test_enrichment_and_visualizations.py` → `tests/integration/test_enrichment_and_visualizations.py`
3. `scripts/test_humanization_integration.py` → `tests/integration/test_humanization_integration.py`
4. `scripts/test_manuscript_pipeline_e2e.py` → `tests/e2e/test_manuscript_pipeline_e2e.py`

#### 2.3 Archive Migration Script (1 file)
**Confidence**: Medium - May still be useful for reference

1. `scripts/migrate_tests.py` → `scripts/archive/migrate_tests.py`

### Phase 3: Validation

**After cleanup, verify**:
1. Run `pytest --collect-only` - All tests should be discoverable
2. Run `scripts/validate_test_mapping.py` - Should show improved structure
3. Run `scripts/test_discovery.py --orphaned` - Should show fewer orphaned tests
4. Check for broken imports: `python scripts/check_broken_imports.py`
5. Run a sample of tests to ensure they still work

### Phase 4: Documentation Updates

1. **Update README.md**: Add section on available scripts
2. **Update tests/README.md**: Document moved test files
3. **Create scripts/archive/README.md**: Explain archived scripts

## Detailed Implementation Plan

See `CLEANUP_IMPLEMENTATION_PLAN.md` for step-by-step instructions with:
- Pre-cleanup verification steps
- Detailed removal procedures
- File movement procedures with import updates
- Validation commands
- Rollback procedures
- Success criteria

### Future Considerations

1. **Consolidate test execution scripts**: Consider creating a unified test runner that handles all test types
2. **Document script usage**: Add usage examples to README for each script
3. **Create script categories**: Organize scripts into subdirectories by category
4. **Add script tests**: Consider adding tests for utility scripts to ensure they work correctly

---

## File Count Summary

**Current State:**
- Scripts: 31 files
- Tests: 75 files
- **Total**: 106 files

**After Cleanup:**
- Scripts: 31 → 22 (remove 4, move 4, archive 1)
- Tests: 75 → 79 (75 existing + 4 moved from scripts)
- **Total**: 106 → 101 files

**Note**: The 4 test scripts moved from `scripts/` to `tests/` are counted in both before and after, but they change location, not total count.

**Script Categories (Final):**
- Test Infrastructure: 3 files
- Test Execution: 6 files (includes test execution scripts)
- Development Tools: 5 files
- Data Generation: 2 files
- Workflow Testing: 3 files
- Utility Scripts: 3 files

## Next Steps and Roadmap

### Immediate Next Steps

1. **Review Documents**:
   - Read `TEST_AND_SCRIPT_INVENTORY.md` (this document) for complete file catalog
   - Read `CLEANUP_IMPLEMENTATION_PLAN.md` for step-by-step execution guide
   - Read `CLEANUP_SUMMARY.md` for quick reference

2. **Decide on Approach**:
   - **Option A**: Execute cleanup immediately (follow implementation plan)
   - **Option B**: Review each file individually first (complete verification phase)
   - **Option C**: Start with low-risk removals only

3. **Execute Cleanup** (if proceeding):
   - Follow `CLEANUP_IMPLEMENTATION_PLAN.md` phase by phase
   - Validate after each phase
   - Document any deviations

### Recommended Approach

**Phase 1: Verification** (1-2 hours)
- Complete reading of remaining unverified files
- Update inventory with 100% verified information
- Finalize recommendations

**Phase 2: Low-Risk Cleanup** (1 hour)
- Remove 4 temporary scripts (high confidence, low risk)
- Verify no broken imports
- Commit changes

**Phase 3: Test Script Migration** (2-3 hours)
- Move 4 test scripts to proper locations
- Convert to pytest format if needed
- Update imports
- Verify pytest discovery
- Commit changes

**Phase 4: Archive** (30 minutes)
- Create archive directory
- Move migration script
- Add archive README
- Commit changes

**Phase 5: Validation** (1 hour)
- Run full test suite
- Verify test discovery
- Check for issues
- Fix any problems

**Phase 6: Documentation** (1 hour)
- Update README files
- Document changes
- Update inventory document
- Commit changes

**Total Estimated Time**: 6-8 hours

### Risk Assessment

**Low Risk** (High confidence, minimal impact):
- Removing temporary scripts (4 files)
- Archiving migration script (1 file)

**Medium Risk** (Requires careful execution):
- Moving test scripts (4 files) - Need to update imports and verify pytest compatibility

**Mitigation**:
- Create backup branch before starting
- Test after each major change
- Keep git history for rollback
- Validate thoroughly before finalizing

### Success Criteria

- [ ] All 106 files verified and documented
- [ ] 4 temporary scripts removed
- [ ] 4 test scripts moved to proper test directories
- [ ] 1 migration script archived
- [ ] All tests discoverable by pytest
- [ ] No broken imports
- [ ] Test suite passes
- [ ] Documentation updated
- [ ] File counts match expectations

### Related Documents

- **`docs/TEST_AND_SCRIPT_INVENTORY.md`** - Complete file catalog (this document)
- **`docs/CLEANUP_IMPLEMENTATION_PLAN.md`** - Detailed step-by-step execution guide
- **`docs/CLEANUP_SUMMARY.md`** - Quick reference summary
- **`tests/README.md`** - Test organization guide
