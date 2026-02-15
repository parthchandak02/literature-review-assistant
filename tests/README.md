# Testing Strategy

## Overview

This project uses a comprehensive testing strategy for LLM-based applications,
emphasizing fast feedback, zero API costs, and robust error handling.

## Quick Start

### Initial Setup

```bash
# One-time setup
./scripts/setup-dev-env.sh
```

This installs dependencies, sets up pre-commit hooks, and runs initial tests.

### Run All Tests

```bash
pytest
```

### Run Tests in Parallel (Fast)

```bash
pytest -n auto
```

Uses all available CPU cores for parallel execution.

### Run Only Fast Tests

```bash
pytest -m "fast"
```

Runs tests marked as `fast` (< 1 second each). Good for quick validation.

### Auto-Run Tests on File Changes

```bash
./scripts/test-watch.sh
```

Uses `pytest-watch` to automatically re-run tests when you save files.
Perfect for development - provides <3s feedback loop.

## Test Categories

### Unit Tests (`tests/unit/`)

- Test individual components in isolation
- Mock all external dependencies (LLM, database, etc.)
- Should run in <5 seconds total
- Target: 90%+ coverage
- **Run on every file save**

Key files:
- `test_llm_response_parsing.py` - Comprehensive LLM response handling tests
- `test_fulltext_agent.py` - Full-text screening agent tests
- `test_title_abstract_agent.py` - Title/abstract screening tests

### Integration Tests (`tests/integration/`)

- Test component interactions
- Use recorded LLM fixtures (zero API cost)
- Should run in <30 seconds
- Target: 80%+ coverage
- **Run before commits (via pre-commit hooks)**

Key files:
- `test_screening_with_fixtures.py` - Tests using recorded problematic responses

### E2E Tests (`tests/e2e/`)

- Full workflow testing
- Mock LLM responses for determinism
- May be slower (30s - 2min)
- Target: 70%+ coverage
- **Run before releases/merges**

Key files:
- `test_screening_resilience.py` - Regression tests for historical failures
- `test_full_workflow.py` - Complete workflow validation

### Regression Tests (marked with `@pytest.mark.regression`)

- Tests for historical bugs that caused crashes
- Uses recorded responses from actual production failures
- **Must always pass** - any failure indicates regression

Example: Paper 4 crash (2026-02-07) - plain text response causing `AttributeError`

## Test Markers

Use markers to categorize and filter tests:

- `@pytest.mark.fast` - Fast tests (< 1 second)
- `@pytest.mark.slow` - Slow tests (> 1 second)
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.regression` - Regression tests for historical bugs
- `@pytest.mark.requires_llm` - Tests requiring real LLM API (expensive!)

### Running Specific Test Types

```bash
# Only fast tests
pytest -m "fast"

# Only unit tests
pytest -m "unit"

# Only regression tests
pytest -m "regression"

# Exclude slow and LLM-requiring tests
pytest -m "not slow and not requires_llm"

# Specific file
pytest tests/unit/test_llm_response_parsing.py

# Specific test
pytest tests/unit/test_llm_response_parsing.py::TestLLMResponseParsing::test_response_parsed_returns_none
```

## Working with LLM Tests

### Recording New Fixtures

When you encounter a new problematic LLM response:

1. **Copy the response** to `tests/fixtures/recorded_llm_responses.py`
2. **Add a descriptive name** (e.g., `NEW_FAILURE_MODE_20260207`)
3. **Document the context** (date, paper, issue)
4. **Create a regression test** in `tests/integration/` or `tests/unit/`
5. **Verify the fix** handles it gracefully

Example:

```python
# In recorded_llm_responses.py
NEW_BUG_RESPONSE = """DECISION: include but confidence low
REASONING: unclear response format"""

# In test file
def test_new_bug_response():
    screener = FullTextScreener(...)
    with patch(...) as mock:
        mock.return_value = NEW_BUG_RESPONSE
        result = screener.screen(...)
        assert result is not None  # Should not crash
```

### Cost-Free Testing

All tests use mocked or recorded responses - **zero API costs**.

Benefits:
- No API keys needed for testing
- Fast execution (no network calls)
- Deterministic results (same input, same output)
- Can test error scenarios without triggering real errors

### Optional Real API Testing

Only run when validating actual LLM behavior (not recommended for regular testing):

```bash
# Set your API key
export OPENAI_API_KEY="your-key"
export GEMINI_API_KEY="your-key"

# Run LLM-requiring tests
pytest -m "requires_llm" --maxfail=5
```

**WARNING:** This costs money and is slow! Only use for validation, not regular testing.

## Coverage Requirements

### Generating Coverage Reports

```bash
# Run with coverage
pytest --cov=src --cov-report=html

# Open report
open htmlcov/index.html
```

### Coverage Targets

- Unit tests: >90% coverage
- Integration tests: >80% coverage  
- E2E tests: >70% coverage
- Overall: >85% coverage

### Critical Files (100% Coverage Required)

- `src/screening/base_agent.py`
- `src/screening/fulltext_agent.py`
- `src/screening/title_abstract_agent.py`
- Any file handling LLM responses

## Adding New Tests

### 1. Choose Test Type

- **Unit test**: Testing single function/class in isolation
- **Integration test**: Testing interactions between components
- **E2E test**: Testing full workflow

### 2. Use Fixtures

```python
from tests.fixtures.llm_response_factory import LLMResponseFactory
from tests.fixtures.recorded_llm_responses import PLAIN_TEXT_RESPONSE_PAPER4

# Create mock response
mock_response = LLMResponseFactory.plain_text_response(PLAIN_TEXT_RESPONSE_PAPER4)
```

### 3. Add Markers

```python
@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.regression
def test_my_new_test():
    # Test code
    pass
```

### 4. Run pytest-watch During Development

```bash
./scripts/test-watch.sh
```

This gives you immediate feedback as you write tests.

## Pre-Commit Hooks

Pre-commit hooks automatically run before each commit:

1. **Fast unit tests** - Ensures basic functionality works
2. **No debug prints** - Prevents committing debug code
3. **No breakpoints** - Prevents committing debugging breakpoints
4. **Code formatting** - Ensures consistent style

### Installing Hooks

```bash
pre-commit install
```

### Bypassing Hooks (NOT Recommended)

```bash
git commit --no-verify -m "message"
```

Only use when absolutely necessary!

### Updating Hooks

```bash
pre-commit autoupdate
```

## Troubleshooting

### Tests are Slow

```bash
# Enable parallel execution
pytest -n auto

# Run only fast tests
pytest -m "fast"
```

### Need to Debug a Specific Test

```bash
# Verbose output with prints
pytest tests/unit/test_name.py::test_function -v -s

# Stop at first failure
pytest -x

# Use PDB debugger
pytest --pdb
```

### Pre-Commit Hook Failing

```bash
# Run what pre-commit runs
pytest -m "fast" --tb=short

# See detailed output
pre-commit run --all-files
```

### Import Errors

Make sure you're in the project root and have installed dependencies:

```bash
# Using uv (recommended)
uv pip install -e .
uv sync --group dev

# Or using pip
pip install -e .
```

### Fixture Not Found

Ensure fixtures are properly imported:

```python
from tests.fixtures.recorded_llm_responses import PLAIN_TEXT_RESPONSE_PAPER4
```

## Test Performance Tips

1. **Use pytest-xdist** for parallel execution: `-n auto`
2. **Mark slow tests** appropriately: `@pytest.mark.slow`
3. **Use recorded fixtures** instead of real API calls
4. **Mock external dependencies** at the boundary
5. **Keep unit tests focused** - one concept per test
6. **Use pytest-watch** for instant feedback during development

## Continuous Improvement

### After Finding a Bug

1. **Record the failure** - Add response to `recorded_llm_responses.py`
2. **Write regression test** - Ensure it won't happen again
3. **Fix the code** - Make the test pass
4. **Verify with all tests** - Run full test suite
5. **Document the fix** - Update relevant comments/docs

### Monthly Review

- Check test execution time - keep fast tests fast
- Review coverage reports - identify gaps
- Update fixtures with new edge cases
- Remove obsolete tests

## Best Practices

1. **Test behavior, not implementation** - Focus on what, not how
2. **Use descriptive test names** - `test_screen_handles_plain_text_response`
3. **Arrange-Act-Assert pattern** - Clear test structure
4. **Mock at boundaries** - Mock external systems, not internal logic
5. **Keep tests independent** - Each test can run alone
6. **Fast feedback loop** - Use pytest-watch during development
7. **Zero API costs** - Always use fixtures for LLM responses
8. **Regression tests for all bugs** - Every bug becomes a test

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-xdist](https://github.com/pytest-dev/pytest-xdist)
- [pytest-watch](https://github.com/joeyespo/pytest-watch)
- [pre-commit](https://pre-commit.com/)

## Questions?

Check the [main README](../README.md) or contact the development team.
