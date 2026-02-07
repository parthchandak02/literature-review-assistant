"""
Integration tests for observability (metrics and cost tracking).
"""

from src.observability.cost_tracker import CostTracker
from src.observability.metrics import MetricsCollector


class TestObservabilityIntegration:
    """Test observability integration."""

    def test_metrics_and_cost_tracking_integration(self):
        """Test metrics and cost tracking together."""
        metrics_collector = MetricsCollector()
        cost_tracker = CostTracker()

        # Simulate agent call
        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        # Record metrics
        metrics_collector.record_call("test_agent", duration=1.5, success=True)

        # Record cost
        cost_tracker.record_call("openai", "gpt-4", mock_usage, agent_name="test_agent")

        # Verify both tracked
        agent_metrics = metrics_collector.get_metrics("test_agent")
        assert "test_agent" in agent_metrics
        assert agent_metrics["test_agent"].total_calls == 1

        agent_costs = cost_tracker.get_agent_costs()
        assert "test_agent" in agent_costs
        assert agent_costs["test_agent"] > 0
