"""
Unit tests for workflow graph.
"""

import pytest

try:
    from src.orchestration.workflow_graph import WorkflowState  # noqa: F401

    WORKFLOW_GRAPH_AVAILABLE = True
except ImportError:
    WORKFLOW_GRAPH_AVAILABLE = False


@pytest.mark.skipif(not WORKFLOW_GRAPH_AVAILABLE, reason="WorkflowGraph requires langgraph")
class TestWorkflowGraph:
    """Test WorkflowGraph class."""

    def test_workflow_state_typedict(self):
        """Test that WorkflowState TypedDict is valid."""
        # Test that WorkflowState TypedDict is valid
        state: WorkflowState = {
            "topic_context": {},
            "phase": "search",
            "papers": [],
            "unique_papers": [],
            "screened_papers": [],
            "eligible_papers": [],
            "final_papers": [],
            "extracted_data": [],
            "prisma_counts": {},
            "outputs": {},
            "errors": [],
        }

        assert state["phase"] == "search"
        assert isinstance(state["papers"], list)
