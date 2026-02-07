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
        cost_tracker.record_call("gemini", "gemini-2.5-pro", mock_usage, agent_name="test_agent")

        # Verify both tracked
        agent_metrics = metrics_collector.get_metrics("test_agent")
        assert "test_agent" in agent_metrics
        assert agent_metrics["test_agent"].total_calls == 1

        summary = cost_tracker.get_summary()
        assert "test_agent" in summary["by_agent"]
        assert summary["by_agent"]["test_agent"] > 0

    def test_all_agents_track_costs(self):
        """Test that all agents that make LLM calls track costs."""
        cost_tracker = CostTracker()

        # List of agents that should track costs
        expected_agents = [
            "Full-text Screening Specialist",
            "Title/Abstract Screening Specialist",
            "Data Extraction Specialist",
            "Quality Assessment Auto-Filler",
            "Study Type Detector",
            "Introduction Writer",
            "Methods Writer",
            "Results Writer",
            "Discussion Writer",
            "Abstract Generator",
            "Research Agent",
        ]

        # Simulate calls from each agent
        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        for agent in expected_agents:
            cost_tracker.record_call("gemini", "gemini-2.5-pro", mock_usage, agent_name=agent)

        # Verify all agents are tracked
        summary = cost_tracker.get_summary()
        for agent in expected_agents:
            assert agent in summary["by_agent"], f"Agent '{agent}' not tracked in costs"

        # Verify total calls match
        assert summary["total_calls"] == len(expected_agents)

    def test_audit_trail_integration(self, tmp_path):
        """Test audit trail integration with cost tracker."""
        import json

        cost_tracker = CostTracker()

        # Enable audit trail
        output_dir = tmp_path / "workflow_output"
        output_dir.mkdir()
        cost_tracker.enable_audit_trail(str(output_dir))

        # Simulate multiple LLM calls from different agents
        agents = [
            ("Quality Assessment Auto-Filler", "gemini-2.5-pro"),
            ("Study Type Detector", "gemini-2.5-flash"),
            ("Data Extraction Specialist", "gemini-2.5-pro"),
        ]

        mock_usage = type(
            "Usage", (), {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        )()

        for agent_name, model in agents:
            cost_tracker.record_call("gemini", model, mock_usage, agent_name=agent_name)

        # Verify audit file exists
        audit_file = output_dir / "llm_calls_audit.json"
        assert audit_file.exists()

        # Verify audit entries
        with open(audit_file) as f:
            audit_entries = json.load(f)

        assert len(audit_entries) == len(agents)

        # Verify each entry has required fields
        for entry in audit_entries:
            assert "timestamp" in entry
            assert "agent" in entry
            assert "model" in entry
            assert "provider" in entry
            assert "prompt_tokens" in entry
            assert "completion_tokens" in entry
            assert "total_tokens" in entry
            assert "cost_usd" in entry

        # Verify agent names match
        agent_names = [entry["agent"] for entry in audit_entries]
        expected_names = [agent for agent, _ in agents]
        assert sorted(agent_names) == sorted(expected_names)

        # Verify costs are calculated
        for entry in audit_entries:
            assert entry["cost_usd"] > 0
