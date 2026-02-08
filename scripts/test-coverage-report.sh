#!/bin/bash
# Generate and display test coverage report

set -e

echo "============================================"
echo "Generating Test Coverage Report"
echo "============================================"
echo ""

# Run tests with coverage
echo "[1/3] Running tests with coverage tracking..."
pytest --cov=src --cov-report=html --cov-report=term-missing --quiet

echo ""
echo "[2/3] Coverage report generated at: htmlcov/index.html"
echo ""

# Display coverage summary
echo "[3/3] Coverage Summary:"
echo "----------------------"
pytest --cov=src --cov-report=term --quiet | tail -20

echo ""
echo "============================================"
echo "To view detailed HTML report:"
echo "  open htmlcov/index.html"
echo "============================================"
