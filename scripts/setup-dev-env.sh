#!/bin/bash
# Setup development environment with testing tools
# Run this once to configure your local development environment

set -e

echo "========================================"
echo "Setting up development environment"
echo "========================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 is not installed or not in PATH"
    exit 1
fi

echo "[1/4] Installing development dependencies..."
if [ -f "requirements-dev.txt" ]; then
    pip install -r requirements-dev.txt
    echo "SUCCESS: Development dependencies installed"
else
    echo "WARNING: requirements-dev.txt not found, skipping dependency installation"
fi
echo ""

echo "[2/4] Installing pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "SUCCESS: Pre-commit hooks installed"
else
    echo "WARNING: pre-commit not found, skipping hook installation"
fi
echo ""

echo "[3/4] Running initial test suite..."
if command -v pytest &> /dev/null; then
    echo "Running fast unit tests..."
    pytest tests/unit -v -m "fast" --tb=short || echo "WARNING: Some tests failed"
    echo ""
else
    echo "WARNING: pytest not found, skipping test run"
fi
echo ""

echo "[4/4] Setup complete!"
echo ""
echo "========================================"
echo "Development environment ready!"
echo "========================================"
echo ""
echo "Quick start:"
echo "  - Run all tests:              pytest"
echo "  - Run fast tests:             pytest -m 'fast'"
echo "  - Run with auto-watch:        ./scripts/test-watch.sh"
echo "  - Run with coverage:          pytest --cov=src"
echo "  - Run specific test:          pytest tests/unit/test_llm_response_parsing.py"
echo ""
echo "Pre-commit hooks are now active and will run fast tests before each commit."
echo ""
