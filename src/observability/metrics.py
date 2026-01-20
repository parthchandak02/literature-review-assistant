"""
Metrics Collection for Agent Performance Monitoring

Tracks agent performance metrics including task duration, success rates, etc.
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Metrics for a single agent."""

    agent_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration: float = 0.0
    average_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0
    last_call_time: Optional[datetime] = None
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


class MetricsCollector:
    """Collects and aggregates metrics for agents."""

    def __init__(self):
        self.metrics: Dict[str, AgentMetrics] = {}
        self._lock = False  # Simple lock flag (use threading.Lock in production)

    def record_call(
        self,
        agent_name: str,
        duration: float,
        success: bool = True,
        error_type: Optional[str] = None,
    ):
        """
        Record an agent call.

        Args:
            agent_name: Name of the agent
            duration: Call duration in seconds
            success: Whether the call was successful
            error_type: Type of error if failed
        """
        if agent_name not in self.metrics:
            self.metrics[agent_name] = AgentMetrics(agent_name=agent_name)

        metrics = self.metrics[agent_name]
        metrics.total_calls += 1
        metrics.total_duration += duration
        metrics.last_call_time = datetime.now()

        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1
            if error_type:
                metrics.error_counts[error_type] += 1

        # Update statistics
        metrics.average_duration = metrics.total_duration / metrics.total_calls
        metrics.min_duration = min(metrics.min_duration, duration)
        metrics.max_duration = max(metrics.max_duration, duration)

    def get_metrics(self, agent_name: Optional[str] = None) -> Dict[str, AgentMetrics]:
        """
        Get metrics for agent(s).

        Args:
            agent_name: Specific agent name, or None for all

        Returns:
            Dictionary of agent metrics
        """
        if agent_name:
            return {agent_name: self.metrics.get(agent_name)} if agent_name in self.metrics else {}
        return self.metrics.copy()

    def get_success_rate(self, agent_name: str) -> float:
        """
        Get success rate for an agent.

        Args:
            agent_name: Agent name

        Returns:
            Success rate (0.0 to 1.0)
        """
        if agent_name not in self.metrics:
            return 0.0

        metrics = self.metrics[agent_name]
        if metrics.total_calls == 0:
            return 0.0

        return metrics.successful_calls / metrics.total_calls

    def reset_metrics(self, agent_name: Optional[str] = None):
        """
        Reset metrics for agent(s).

        Args:
            agent_name: Specific agent name, or None for all
        """
        if agent_name:
            if agent_name in self.metrics:
                del self.metrics[agent_name]
        else:
            self.metrics.clear()

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics across all agents.

        Returns:
            Summary dictionary
        """
        if not self.metrics:
            return {
                "total_agents": 0,
                "total_calls": 0,
                "total_successful": 0,
                "total_failed": 0,
                "overall_success_rate": 0.0,
                "agents": {},  # Always include agents key, even if empty
            }

        total_calls = sum(m.total_calls for m in self.metrics.values())
        total_successful = sum(m.successful_calls for m in self.metrics.values())
        total_failed = sum(m.failed_calls for m in self.metrics.values())

        return {
            "total_agents": len(self.metrics),
            "total_calls": total_calls,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "overall_success_rate": total_successful / total_calls if total_calls > 0 else 0.0,
            "agents": {
                name: {
                    "total_calls": m.total_calls,
                    "success_rate": m.successful_calls / m.total_calls
                    if m.total_calls > 0
                    else 0.0,
                    "average_duration": m.average_duration,
                    "error_counts": dict(m.error_counts),
                }
                for name, m in self.metrics.items()
            },
        }


# Global metrics collector instance
_global_metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _global_metrics
