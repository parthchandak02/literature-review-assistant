#!/bin/bash
# Auto-run tests on file changes for rapid feedback
# Uses pytest-watch for continuous testing during development

set -e

echo "=================================="
echo "Starting pytest-watch"
echo "=================================="
echo ""
echo "Tests will run automatically when you save files."
echo "Press Ctrl+C to stop."
echo ""
echo "Running tests with the following settings:"
echo "  - Test paths: tests/unit tests/integration"
echo "  - Excluded: slow tests, requires_llm tests"
echo "  - Max failures: 3 (stops after 3 failures)"
echo ""

# Run pytest-watch with optimized settings
ptw -- tests/unit tests/integration \
    -v \
    --tb=short \
    -m "not slow and not requires_llm" \
    --maxfail=3 \
    --disable-warnings
