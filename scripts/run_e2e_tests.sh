#!/bin/bash
# Comprehensive End-to-End Test Runner for Phase Registry Refactoring

set -e  # Exit on error

echo "=========================================="
echo "Phase Registry Refactoring - E2E Tests"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results tracking
PASSED=0
FAILED=0
TOTAL=0

# Function to run tests and track results
run_test_suite() {
    local suite_name=$1
    local test_command=$2
    
    echo -e "${YELLOW}Running: ${suite_name}${NC}"
    echo "Command: ${test_command}"
    echo ""
    
    if eval "${test_command}"; then
        echo -e "${GREEN}✓ ${suite_name} PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ ${suite_name} FAILED${NC}"
        ((FAILED++))
    fi
    ((TOTAL++))
    echo ""
}

# 1. Unit Tests
echo "=========================================="
echo "Phase 1: Unit Tests"
echo "=========================================="
echo ""

run_test_suite "PhaseRegistry Tests" "pytest tests/unit/orchestration/test_phase_registry.py -v"
run_test_suite "CheckpointManager Tests" "pytest tests/unit/orchestration/test_checkpoint_manager.py -v"
run_test_suite "PhaseExecutor Tests" "pytest tests/unit/orchestration/test_phase_executor.py -v"

# 2. Integration Tests
echo "=========================================="
echo "Phase 2: Integration Tests"
echo "=========================================="
echo ""

run_test_suite "Workflow Registry Integration" "pytest tests/integration/test_workflow_registry_integration.py -v"
run_test_suite "Backward Compatibility" "pytest tests/integration/test_backward_compatibility.py -v"

# 3. Syntax and Linting
echo "=========================================="
echo "Phase 3: Code Quality Checks"
echo "=========================================="
echo ""

echo -e "${YELLOW}Checking Python syntax...${NC}"
if python -c "import ast; [ast.parse(open(f).read()) for f in ['src/orchestration/workflow_manager.py', 'src/orchestration/phase_registry.py', 'src/orchestration/checkpoint_manager.py', 'src/orchestration/phase_executor.py']]" 2>/dev/null; then
    echo -e "${GREEN}✓ Syntax check PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Syntax check FAILED${NC}"
    ((FAILED++))
fi
((TOTAL++))
echo ""

echo -e "${YELLOW}Checking imports...${NC}"
if python -c "from src.orchestration import PhaseRegistry, PhaseDefinition, CheckpointManager, PhaseExecutor" 2>/dev/null; then
    echo -e "${GREEN}✓ Import check PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Import check FAILED${NC}"
    ((FAILED++))
fi
((TOTAL++))
echo ""

# 4. Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
if [ ${FAILED} -gt 0 ]; then
    echo -e "${RED}Failed: ${FAILED}${NC}"
else
    echo -e "${GREEN}Failed: ${FAILED}${NC}"
fi
echo ""

if [ ${FAILED} -eq 0 ]; then
    echo -e "${GREEN}=========================================="
    echo "All tests PASSED! Ready for commit."
    echo "==========================================${NC}"
    exit 0
else
    echo -e "${RED}=========================================="
    echo "Some tests FAILED. Please fix before committing."
    echo "==========================================${NC}"
    exit 1
fi
