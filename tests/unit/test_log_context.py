"""
Unit tests for log context.
"""

from src.utils.log_context import LogContext, agent_log_context, workflow_phase_context


class TestLogContext:
    """Test LogContext class."""

    def test_log_context_initialization(self):
        """Test LogContext initialization."""
        context = LogContext(agent="test_agent", operation="test_op")

        assert context.context["agent"] == "test_agent"
        assert context.context["operation"] == "test_op"

    def test_log_context_enter_exit(self):
        """Test LogContext as context manager."""
        with LogContext(agent="test_agent") as ctx:
            assert ctx.start_time is not None
            assert ctx.context["agent"] == "test_agent"

    def test_log_context_add_event(self):
        """Test adding event to log context."""
        context = LogContext(agent="test_agent")

        # Should not raise
        context.add_event("test_event", key="value")


class TestAgentLogContext:
    """Test agent_log_context function."""

    def test_agent_log_context(self):
        """Test agent log context manager."""
        # agent_log_context is a context manager that yields nothing
        with agent_log_context("test_agent", "test_operation", extra="value"):
            # Should not raise
            pass


class TestWorkflowPhaseContext:
    """Test workflow_phase_context function."""

    def test_workflow_phase_context(self):
        """Test workflow phase context manager."""
        # workflow_phase_context is a context manager that yields nothing
        with workflow_phase_context("search", query="test query"):
            # Should not raise
            pass
