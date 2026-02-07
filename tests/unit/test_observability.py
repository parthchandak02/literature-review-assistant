"""
Unit tests for observability (metrics, cost tracker, tracing).
"""

from src.observability.cost_tracker import CostTracker
from src.observability.metrics import MetricsCollector


class TestMetricsCollector:
    """Test MetricsCollector class."""

    def test_metrics_collector_initialization(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()

        assert len(collector.metrics) == 0

    def test_record_successful_call(self):
        """Test recording a successful call."""
        collector = MetricsCollector()

        collector.record_call("test_agent", duration=1.5, success=True)

        assert "test_agent" in collector.metrics
        metrics = collector.metrics["test_agent"]
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0
        assert metrics.total_duration == 1.5
        assert metrics.average_duration == 1.5

    def test_record_failed_call(self):
        """Test recording a failed call."""
        collector = MetricsCollector()

        collector.record_call("test_agent", duration=0.5, success=False, error_type="ValueError")

        metrics = collector.metrics["test_agent"]
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 1
        assert metrics.error_counts["ValueError"] == 1

    def test_record_multiple_calls(self):
        """Test recording multiple calls."""
        collector = MetricsCollector()

        collector.record_call("test_agent", duration=1.0, success=True)
        collector.record_call("test_agent", duration=2.0, success=True)
        collector.record_call("test_agent", duration=1.5, success=False)

        metrics = collector.metrics["test_agent"]
        assert metrics.total_calls == 3
        assert metrics.successful_calls == 2
        assert metrics.failed_calls == 1
        assert metrics.total_duration == 4.5
        assert metrics.average_duration == 1.5
        assert metrics.min_duration == 1.0
        assert metrics.max_duration == 2.0

    def test_get_metrics_specific_agent(self):
        """Test getting metrics for specific agent."""
        collector = MetricsCollector()

        collector.record_call("agent1", duration=1.0)
        collector.record_call("agent2", duration=2.0)

        metrics = collector.get_metrics("agent1")
        assert len(metrics) == 1
        assert "agent1" in metrics

    def test_get_metrics_all_agents(self):
        """Test getting metrics for all agents."""
        collector = MetricsCollector()

        collector.record_call("agent1", duration=1.0)
        collector.record_call("agent2", duration=2.0)

        metrics = collector.get_metrics()
        assert len(metrics) == 2
        assert "agent1" in metrics
        assert "agent2" in metrics

    def test_reset_metrics(self):
        """Test resetting metrics."""
        collector = MetricsCollector()

        collector.record_call("test_agent", duration=1.0)
        assert len(collector.metrics) == 1

        collector.reset_metrics("test_agent")
        # reset_metrics deletes the agent from metrics
        assert "test_agent" not in collector.metrics


class TestCostTracker:
    """Test CostTracker class."""

    def test_cost_tracker_initialization(self):
        """Test CostTracker initialization."""
        tracker = CostTracker()

        assert len(tracker.entries) == 0
        assert tracker.total_cost == 0.0

    def test_record_gemini_call(self):
        """Test recording Gemini call."""
        tracker = CostTracker()

        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        tracker.record_call("gemini", "gemini-2.5-pro", mock_usage, agent_name="test_agent")

        assert len(tracker.entries) == 1
        assert tracker.total_cost > 0
        assert tracker.by_provider["gemini"] > 0
        assert tracker.by_model["gemini-2.5-pro"] > 0
        assert tracker.by_agent["test_agent"] > 0

    def test_get_summary(self):
        """Test getting cost summary."""
        tracker = CostTracker()

        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        tracker.record_call("gemini", "gemini-2.5-pro", mock_usage)

        summary = tracker.get_summary()
        assert "total_cost_usd" in summary
        assert "by_provider" in summary
        assert "by_model" in summary
        assert summary["total_cost_usd"] > 0

    def test_get_agent_costs(self):
        """Test getting costs by agent."""
        tracker = CostTracker()

        mock_usage1 = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        mock_usage2 = type(
            "Usage", (), {"prompt_tokens": 500, "completion_tokens": 250, "total_tokens": 750}
        )()

        tracker.record_call("gemini", "gemini-2.5-pro", mock_usage1, agent_name="agent1")
        tracker.record_call("gemini", "gemini-2.5-flash", mock_usage2, agent_name="agent2")

        # Use by_agent dict directly
        assert "agent1" in tracker.by_agent
        assert "agent2" in tracker.by_agent
        assert tracker.by_agent["agent1"] > tracker.by_agent["agent2"]

    def test_unknown_model_cost(self):
        """Test handling unknown model."""
        tracker = CostTracker()

        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        # Should handle gracefully
        tracker.record_call("gemini", "unknown-model", mock_usage)
        assert len(tracker.entries) == 1
        # Cost should be 0 for unknown model
        assert tracker.entries[0].cost == 0.0
