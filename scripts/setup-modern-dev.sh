#!/bin/bash
# Modern development environment setup using uv and ruff
# 10-100x faster than traditional pip/poetry setup

set -e

echo "========================================"
echo "Modern Python Development Setup"
echo "Using: uv + ruff + pytest + mypy"
echo "========================================"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "[1/5] Installing uv (fast Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    
    echo "SUCCESS: uv installed"
    echo "Note: Restart your shell or run: source ~/.bashrc (or ~/.zshrc)"
else
    echo "[1/5] uv is already installed"
fi
echo ""

echo "[2/5] Installing dependencies with uv..."
# Install project dependencies
if [ -f "requirements.txt" ]; then
    uv pip install -r requirements.txt
fi

# Install dev dependencies from pyproject.toml
uv pip install pytest pytest-xdist pytest-watch pytest-cov ruff mypy pre-commit
echo "SUCCESS: Dependencies installed"
echo ""

echo "[3/5] Setting up pre-commit hooks..."
pre-commit install
echo "SUCCESS: Pre-commit hooks installed"
echo ""

echo "[4/5] Running ruff to check code quality..."
# Format code
uvx ruff format src/ tests/ || echo "Some formatting applied"

# Check for linting issues
uvx ruff check src/ tests/ --fix || echo "Some linting issues found"
echo ""

echo "[5/5] Running fast tests..."
pytest -m "fast" --tb=short || echo "WARNING: Some tests failed"
echo ""

echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Quick Commands:"
echo "  Format code:       uvx ruff format ."
echo "  Check linting:     uvx ruff check ."
echo "  Type check:        uvx mypy src/"
echo "  Run tests:         pytest"
echo "  Fast tests only:   pytest -m 'fast'"
echo "  Auto-run tests:    ./scripts/test-watch.sh"
echo "  Run with coverage: pytest --cov=src"
echo ""
echo "Why this is better:"
echo "  - uv: 10-100x faster than pip"
echo "  - ruff: Replaces black, isort, flake8 (100x faster)"
echo "  - All config in pyproject.toml (single source of truth)"
echo "  - Pre-commit hooks run automatically"
echo ""
