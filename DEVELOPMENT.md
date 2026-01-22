# Development Guide

Developer-focused documentation for the Literature Review Assistant project.

## Table of Contents

- [Development Setup](#development-setup)
- [Code Style and Linting](#code-style-and-linting)
- [Testing Strategy](#testing-strategy)
- [Test Organization](#test-organization)
- [Bibliometric Features Testing](#bibliometric-features-testing)
- [Development Workflow](#development-workflow)
- [Contributing Guidelines](#contributing-guidelines)
- [Debugging](#debugging)
- [Release Process](#release-process)

## Development Setup

### Prerequisites

- Python >=3.8
- `uv` package manager (install from [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv))
- Git

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd research-article-writer

# Create virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
uv pip install -e .

# Install optional dependencies
uv pip install -e ".[manubot-full]"  # For citation resolution
uv pip install -e ".[bibliometrics]"  # For bibliometric features
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required API keys:
- At least one LLM API key (OpenAI, Anthropic, Google GenAI, or Perplexity)
- Optional: Scopus API key (`SCOPUS_API_KEY`) for bibliometric features
- Optional: ScraperAPI key (`SCRAPERAPI_KEY`) for Google Scholar

## Code Style and Linting

### Ruff Configuration

The project uses `ruff` for linting and formatting. Configuration is in `pyproject.toml`.

### Formatting Code

```bash
# Format code
ruff format src/ main.py scripts/

# Check formatting
ruff format --check src/ main.py scripts/
```

### Linting

```bash
# Run linter
ruff check src/ main.py scripts/

# Auto-fix issues
ruff check --fix src/ main.py scripts/

# Or use Makefile
make lint
```

### Code Style Guidelines

- Follow PEP 8 style guide
- Use `ruff` for automatic formatting and linting
- Type hints are encouraged for new code
- Document complex functions and classes with docstrings
- Use Google-style or NumPy-style docstrings for complex functions

### Pre-commit Hooks

The project includes pre-commit hooks for:
- Test structure validation
- Test naming convention checks

Install pre-commit hooks:

```bash
pre-commit install
```

## Testing Strategy

### Test Structure

Tests are organized to mirror the source code structure:

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

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test type
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m e2e          # End-to-end tests only

# Run tests for a specific module
pytest tests/unit/search/

# Run fast tests only
pytest -m fast

# Run with coverage
pytest --cov=src --cov-report=html
```

### Test Markers

Tests are marked with pytest markers for categorization:

**Type Markers:**
- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.e2e` - End-to-end test

**Module Markers:**
- `@pytest.mark.module_citations` - Tests for citations module
- `@pytest.mark.module_search` - Tests for search module
- `@pytest.mark.module_orchestration` - Tests for orchestration module

**Speed Markers:**
- `@pytest.mark.fast` - Fast test (< 1 second)
- `@pytest.mark.slow` - Slow test (> 1 second)

**Dependency Markers:**
- `@pytest.mark.requires_api` - Requires external API
- `@pytest.mark.requires_db` - Requires database
- `@pytest.mark.requires_llm` - Requires LLM API
- `@pytest.mark.requires_network` - Requires network access

See `pytest.ini` for complete marker definitions.

### Test Coverage Goals

- **Overall Coverage**: > 80%
- **Per Module Coverage**: > 80% for critical modules
- **Critical Modules**: orchestration, search, citations, export, writing

Current coverage: 45.7% (42/92 files tested)

Well-tested modules: citations (83%), config (100%), enrichment (100%)

Needs tests: extraction (0%), observability (0%), many orchestration files

## Test Organization

### Test Discovery Tools

**Find tests for a source file:**
```bash
python scripts/test_discovery.py --source src/search/database_connectors.py
```

**Find source file for a test:**
```bash
python scripts/test_discovery.py --test tests/unit/search/test_database_connectors.py
```

**Find all tests for a module:**
```bash
python scripts/test_discovery.py --module search
```

**List missing tests:**
```bash
python scripts/test_discovery.py --missing-tests
```

**Generate coverage report:**
```bash
python scripts/test_discovery.py --coverage
```

### Test Validation

Validate test structure and naming conventions:

```bash
python scripts/validate_test_mapping.py
```

This checks:
- Tests are in correct locations
- Test naming conventions are followed
- Source files have corresponding tests
- No orphaned tests

### Test Naming Conventions

- **Test files**: `test_<module_name>.py` for `<module_name>.py`
- **Test classes**: `Test<ClassName>`
- **Test functions**: `test_<functionality>`

Examples:
- Source: `src/search/database_connectors.py`
- Test: `tests/unit/search/test_database_connectors.py`

### Adding New Tests

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

### Key Test Infrastructure Files

1. `pytest.ini` - Pytest configuration with markers
2. `.coveragerc` - Coverage configuration
3. `.pre-commit-config.yaml` - Pre-commit hooks
4. `tests/README.md` - Test organization guide
5. `scripts/test_discovery.py` - Test discovery tool
6. `scripts/validate_test_mapping.py` - Test validation tool
7. `scripts/analyze_test_structure.py` - Structure analysis tool
8. `data/test_mapping.json` - Test-to-source mapping

## Bibliometric Features Testing

### Overview

Comprehensive testing for bibliometric features:
- Google Scholar Connector
- Enhanced Scopus Connector (with pybliometrics)
- Author Service
- Citation Network Builder
- Bibliometric Enricher

### Prerequisites

**Required Dependencies:**
```bash
uv pip install -e ".[bibliometrics]"
# or
uv pip install pybliometrics scholarly
```

**Required API Keys/Configuration:**
- **Scopus API Key**: `SCOPUS_API_KEY` (for enhanced Scopus features)
- **ScraperAPI Key**: `SCRAPERAPI_KEY` (recommended for Google Scholar to avoid CAPTCHAs)
- **Proxy Configuration**: Configure in `config/workflow.yaml` if using Google Scholar

### Test Categories

#### 1. Google Scholar Connector Tests

- Basic search functionality
- Author search
- Proxy integration
- Error handling

#### 2. Enhanced Scopus Connector Tests

- Author retrieval by ID
- Affiliation retrieval
- Author search using Scopus query syntax
- Enhanced search results with bibliometric fields
- Fallback without pybliometrics

#### 3. Author Service Tests

- Unified author retrieval interface
- Author profile aggregation from multiple sources
- Author metrics retrieval
- Coauthor retrieval

#### 4. Citation Network Builder Tests

- Network building from papers
- Citation edge addition
- Network statistics calculation
- NetworkX export
- Paper ID generation

#### 5. Bibliometric Enricher Tests

- Paper enrichment with bibliometric data
- Author metrics enrichment
- Citation network building

#### 6. Configuration Tests

- Bibliometrics configuration parsing
- Google Scholar configuration

#### 7. Integration Tests

- Workflow integration with bibliometrics enabled
- Database connector factory integration
- Multi-database author retrieval

### Running Bibliometric Tests

```bash
# Run bibliometric integration tests
pytest tests/integration/test_bibliometric_integration.py -v

# Run with API keys (requires real API access)
pytest tests/integration/test_bibliometric_integration.py -v --requires-api
```

## Development Workflow

### Making Changes

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following code style guidelines

3. **Write tests** for new functionality

4. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

5. **Format and lint:**
   ```bash
   ruff format src/ main.py scripts/
   ruff check --fix src/ main.py scripts/
   ```

6. **Validate test structure:**
   ```bash
   python scripts/validate_test_mapping.py
   ```

7. **Commit changes:**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

### Testing Database Connectors

```bash
# Test all database connectors
python main.py --test-databases
# or
python scripts/test_database_health.py
```

### Testing Workflow Stages

```bash
# Test individual workflow stage
python main.py --test-stage <stage_name>
# or
python scripts/test_stage.py <stage_name>
```

### Testing Full Workflow

```bash
# Test complete workflow
python scripts/test_full_workflow.py
```

### Testing Checkpoint Functionality

```bash
# Run workflow once to create checkpoints
python main.py

# Run again - should resume from latest checkpoint
python main.py
```

## Contributing Guidelines

### Reporting Issues

Use the GitHub issue tracker to report bugs or request features. Include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details (Python version, OS, etc.)
- Relevant error messages or logs

### Submitting Pull Requests

1. **Fork the repository** and create a feature branch

2. **Follow code style**: The project uses `ruff` for linting and formatting
   ```bash
   ruff check --fix src/ main.py
   ruff format src/ main.py
   ```

3. **Write tests**: Add tests for new features or bug fixes
   ```bash
   pytest tests/ -v
   ```

4. **Update documentation**: Update README.md or relevant docs if needed

5. **Test your changes**: Ensure all tests pass before submitting

6. **Submit pull request** with clear description of changes

### Code Review Process

- All pull requests require review
- Ensure tests pass and coverage is maintained
- Follow existing code patterns and conventions
- Update documentation for user-facing changes

## Debugging

### Enable Debug Logging

```bash
# Verbose output with logging
python main.py --verbose --log-to-file
```

### Debug Configuration

Debug levels can be configured in `src/config/debug_config.py`:
- `NONE` - No debug output
- `BASIC` - Basic debug information
- `DETAILED` - Detailed debug information
- `VERBOSE` - Maximum verbosity

### Common Debugging Scenarios

**Check workflow progress:**
```bash
python scripts/check_workflow_progress.py
```

**Validate checkpoints:**
```bash
python scripts/validate_checkpoints.py
```

**Check test status:**
```bash
python scripts/check_test_status.py
```

**Analyze dependencies:**
```bash
python scripts/analyze_dependencies.py
```

**Check for broken imports:**
```bash
python scripts/check_broken_imports.py
```

## Release Process

### Version Management

Version is managed in `pyproject.toml`:
```toml
[project]
version = "0.1.0"
```

### Pre-Release Checklist

- [ ] All tests pass
- [ ] Test coverage meets goals (>80% for critical modules)
- [ ] Documentation is up to date
- [ ] Changelog/Recent Changes section updated
- [ ] Version number updated
- [ ] No broken imports or circular dependencies
- [ ] Code formatted and linted

### Release Steps

1. Update version in `pyproject.toml`
2. Update `README.md` Recent Changes section
3. Run full test suite: `pytest tests/ -v`
4. Generate coverage report: `pytest --cov=src --cov-report=html`
5. Validate test structure: `python scripts/validate_test_mapping.py`
6. Create git tag: `git tag v0.1.0`
7. Push changes and tags: `git push origin main --tags`

## Maintenance

### Regular Tasks

- Run `python scripts/analyze_test_structure.py` periodically to update mappings
- Run `python scripts/validate_test_mapping.py` before committing
- Use `python scripts/test_discovery.py --coverage` to track progress
- Update `tests/README.md` as patterns evolve

### Test Maintenance

- Keep test structure aligned with source structure
- Update test docstrings when source modules change
- Add markers to new tests appropriately
- Maintain test coverage goals

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [PEP 8 Style Guide](https://pep8.org/)
