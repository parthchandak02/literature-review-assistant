# Test Organization Guide

This document describes the test organization strategy for the research-article-writer project.

## Test Structure

Tests are organized to mirror the source code structure for easy discoverability and maintenance.

```
tests/
├── unit/              # Unit tests (mirror src/ structure)
│   ├── citations/     # Tests for src/citations/
│   ├── search/        # Tests for src/search/
│   ├── orchestration/ # Tests for src/orchestration/
│   └── ...
├── integration/       # Integration tests (by feature/workflow)
│   ├── search/        # Search workflow tests
│   ├── workflow/      # Workflow integration tests
│   └── ...
├── e2e/              # End-to-end tests (by user journey)
│   ├── test_full_workflow.py
│   └── ...
└── fixtures/         # Shared test data and utilities
    ├── mock_papers.py
    └── ...
```

## Naming Conventions

- **Test files**: `test_<module_name>.py` for `<module_name>.py`
- **Test classes**: `Test<ClassName>`
- **Test functions**: `test_<functionality>`

### Examples

- Source: `src/search/database_connectors.py`
- Test: `tests/unit/search/test_database_connectors.py`

- Source: `src/citations/citation_manager.py`
- Test: `tests/unit/citations/test_citation_manager.py`

## Test Types

### Unit Tests (`tests/unit/`)

Test individual components in isolation. These tests:
- Mirror the `src/` directory structure exactly
- Test one module at a time
- Use mocks for external dependencies
- Run quickly (< 1 second each)

### Integration Tests (`tests/integration/`)

Test component interactions and workflows. These tests:
- Test multiple components working together
- May use real (but isolated) external services
- Test workflows and feature combinations
- May run slower than unit tests

### End-to-End Tests (`tests/e2e/`)

Test complete user journeys. These tests:
- Test the full workflow from start to finish
- May require external services (APIs, databases)
- Validate complete system behavior
- Can be slow and may require setup

## Finding Tests

### Find Tests for a Source File

```bash
python scripts/test_discovery.py --source src/search/database_connectors.py
```

### Find Source File for a Test

```bash
python scripts/test_discovery.py --test tests/unit/search/test_database_connectors.py
```

### Find All Tests for a Module

```bash
python scripts/test_discovery.py --module search
```

### Find Source Files Without Tests

```bash
python scripts/test_discovery.py --missing-tests
```

### Generate Coverage Report

```bash
python scripts/test_discovery.py --coverage
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Tests for a Specific Module

```bash
pytest tests/unit/search/
```

### Run Tests by Marker

```bash
# Run only unit tests
pytest -m unit

# Run only fast tests
pytest -m fast

# Run tests for a specific component
pytest -m "component(citations)"

# Run tests excluding slow tests
pytest -m "not slow"
```

### Run Tests for Changed Files

```bash
python scripts/run_tests_for_changed.py
```

## Test Markers

Tests are marked with pytest markers for categorization:

### Type Markers
- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.e2e` - End-to-end test

### Module Markers
- `@pytest.mark.module_citations` - Tests for citations module
- `@pytest.mark.module_search` - Tests for search module
- `@pytest.mark.module_orchestration` - Tests for orchestration module
- (See `pytest.ini` for complete list)

### Speed Markers
- `@pytest.mark.fast` - Fast test (< 1 second)
- `@pytest.mark.slow` - Slow test (> 1 second)

### Dependency Markers
- `@pytest.mark.requires_api` - Requires external API
- `@pytest.mark.requires_db` - Requires database
- `@pytest.mark.requires_llm` - Requires LLM API
- `@pytest.mark.requires_network` - Requires network access

## Test Coverage Goals

- **Overall Coverage**: > 80%
- **Per Module Coverage**: > 80% for critical modules
- **Critical Modules**: orchestration, search, citations, export, writing

## Adding New Tests

When adding a new source file:

1. **Create corresponding test file** in the same relative location:
   - Source: `src/new_module/new_file.py`
   - Test: `tests/unit/new_module/test_new_file.py`

2. **Add appropriate markers**:
   ```python
   import pytest
   
   @pytest.mark.unit
   @pytest.mark.module_new_module
   @pytest.mark.fast
   def test_new_functionality():
       ...
   ```

3. **Document the source module** in the test file docstring:
   ```python
   """
   Tests for src/new_module/new_file.py
   
   This module tests the NewFile class and its methods.
   """
   ```

4. **Run validation**:
   ```bash
   python scripts/validate_test_mapping.py
   ```

## Maintaining Tests

### Validate Test Structure

```bash
python scripts/validate_test_mapping.py
```

This checks:
- Tests are in correct locations
- Test naming conventions are followed
- Source files have corresponding tests
- No orphaned tests

### Update Test Mapping

When source structure changes, update the mapping:

```bash
python scripts/analyze_test_structure.py
```

This regenerates `data/test_mapping.json` with current mappings.

## Best Practices

1. **Mirror Source Structure**: Always mirror `src/` structure in `tests/unit/`
2. **One Test File Per Module**: One test file per source module (unless module is very large)
3. **Document Source Module**: Each test file should document which source module it tests
4. **Use Markers**: Mark tests appropriately for filtering and categorization
5. **Keep Tests Fast**: Unit tests should run quickly; use mocks for slow operations
6. **Test Edge Cases**: Test both happy paths and error conditions
7. **Maintain Mapping**: Keep test-to-source mapping up to date

## Troubleshooting

### Test Not Found

If pytest can't find your test:
1. Check the test file name starts with `test_`
2. Check the test function name starts with `test_`
3. Verify the file is in the correct location
4. Run `pytest --collect-only` to see what pytest finds

### Import Errors

If you get import errors:
1. Check that `src/` is in Python path (handled by `conftest.py`)
2. Verify imports use relative imports when appropriate
3. Check that `__init__.py` files exist in package directories

### Test Structure Validation Fails

If validation fails:
1. Run `python scripts/validate_test_mapping.py` to see specific issues
2. Check that tests mirror source structure
3. Verify test naming conventions
4. Update test mapping if needed: `python scripts/analyze_test_structure.py`

## Implementation Summary

This section summarizes what was implemented for test organization and maintenance.

### What Was Implemented

#### 1. Test Structure Analysis
- Created `scripts/analyze_test_structure.py` to analyze current test organization
- Generated mapping between source files and test files
- Identified 92 source files and 80 test files
- Created `data/test_mapping.json` with current mappings

#### 2. Test Directory Structure
- Created new test directory structure mirroring `src/` in `tests/unit/`
- All source module directories now have corresponding test directories
- Structure is ready for test migration

#### 3. Pytest Configuration
- Created `pytest.ini` with comprehensive marker definitions
- Configured test discovery patterns
- Added markers for:
  - Test types (unit, integration, e2e)
  - Modules (citations, search, orchestration, etc.)
  - Components (citations, search, workflow, etc.)
  - Speed (fast, slow)
  - Dependencies (requires_api, requires_db, etc.)

#### 4. Test Discovery Tool
- Created `scripts/test_discovery.py` with features:
  - Find tests for a source file: `--source src/module/file.py`
  - Find source for a test: `--test tests/unit/module/test_file.py`
  - Find tests for a module: `--module search`
  - List missing tests: `--missing-tests`
  - List orphaned tests: `--orphaned`
  - Generate coverage report: `--coverage`

#### 5. Test Validation Tool
- Created `scripts/validate_test_mapping.py` to validate:
  - Test structure matches source structure
  - Test naming conventions
  - Missing tests for important modules
  - Orphaned tests

#### 6. Test Migration Helper
- Created `scripts/migrate_tests.py` to assist with:
  - Migrating individual test files
  - Migrating all mappable tests
  - Dry-run mode to preview changes

#### 7. Coverage Configuration
- Created `.coveragerc` for module-level coverage reporting
- Configured coverage exclusions
- Set up HTML coverage reports

#### 8. Pre-commit Hooks
- Created `.pre-commit-config.yaml` with:
  - Test structure validation
  - Test naming convention checks

#### 9. Test Docstring Updates
- Updated example test files with proper docstrings documenting source modules:
  - `tests/unit/test_deduplication.py`
  - `tests/unit/test_visualization.py`
  - `tests/unit/test_schemas.py`
  - `tests/unit/citations/test_citation_manager.py`
  - `tests/unit/search/test_author_service.py`

### Current Test Coverage

- **Overall Coverage**: 45.7% (42/92 files tested)
- **Well-Tested Modules**: citations (83%), config (100%), enrichment (100%)
- **Needs Tests**: extraction (0%), observability (0%), many orchestration files

### Key Files Created

1. `pytest.ini` - Pytest configuration with markers
2. `.coveragerc` - Coverage configuration
3. `.pre-commit-config.yaml` - Pre-commit hooks
4. `tests/README.md` - Test organization guide
5. `scripts/test_discovery.py` - Test discovery tool
6. `scripts/validate_test_mapping.py` - Test validation tool
7. `scripts/migrate_tests.py` - Test migration helper
8. `scripts/analyze_test_structure.py` - Structure analysis tool
9. `data/test_mapping.json` - Test-to-source mapping

### Benefits Achieved

1. **Discoverability**: Easy to find tests for any source file (< 30 seconds)
2. **Maintainability**: Clear relationship between code and tests
3. **Scalability**: Structure grows naturally with source code
4. **Onboarding**: New developers understand organization quickly
5. **Automation**: Tools for discovery, validation, and migration

### Next Steps

#### Immediate
1. **Migrate Tests**: Use `scripts/migrate_tests.py` to gradually migrate tests to new structure
2. **Update Docstrings**: Add source module documentation to all test files
3. **Add Missing Tests**: Focus on critical modules (orchestration, search, etc.)

#### Short Term
1. **Add Pytest Markers**: Mark all tests with appropriate markers
2. **Improve Coverage**: Increase coverage to > 80% for critical modules
3. **CI Integration**: Add test structure validation to CI/CD

#### Long Term
1. **Automated Migration**: Complete migration of all tests to new structure
2. **Coverage Gates**: Set up coverage gates in CI/CD
3. **Test Documentation**: Keep test documentation up to date

### Maintenance

- Run `python scripts/analyze_test_structure.py` periodically to update mappings
- Run `python scripts/validate_test_mapping.py` before committing
- Use `python scripts/test_discovery.py --coverage` to track progress
- Update `tests/README.md` as patterns evolve

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Test Organization Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- Project test discovery tool: `scripts/test_discovery.py`
- Test validation tool: `scripts/validate_test_mapping.py`
