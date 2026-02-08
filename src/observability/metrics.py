"""
Metrics Collection for Agent Performance Monitoring

Tracks agent performance metrics including task duration, success rates, etc.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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


@dataclass
class Phase2Metrics:
    """
    Metrics for Phase 2 implementation (Pydantic structured outputs + parallel execution).

    Tracks improvements from implementing:
    - Pydantic structured outputs for all LLM calls (Phase 2A)
    - Parallel execution for phases 8-11 (Phase 2B)
    """

    # Parsing improvements (Phase 2A)
    llm_calls_total: int = 0
    json_parse_errors_before: int = 0  # Baseline from logs (before implementation)
    json_parse_errors_after: int = 0   # Should be 0 with Pydantic schemas!
    validation_errors: int = 0  # Pydantic validation errors (triggering retries)
    validation_retries_total: int = 0  # Total retry attempts

    # Performance improvements (Phase 2B)
    phases_8_11_time_sequential: float = 0.0  # Baseline: sequential execution time
    phases_8_11_time_parallel: float = 0.0     # New: parallel execution time
    time_savings_seconds: float = 0.0
    time_savings_percent: float = 0.0

    # Overall workflow metrics
    total_workflow_time_before: float = 0.0  # Baseline workflow time
    total_workflow_time_after: float = 0.0   # New workflow time
    workflow_speedup_percent: float = 0.0

    # Cost tracking (using existing cost tracker)
    total_cost_before: float = 0.0
    total_cost_after: float = 0.0
    cost_difference: float = 0.0  # May increase slightly due to retries

    # Quality metrics
    schema_compliance_rate: float = 1.0  # Should be 100% with Pydantic
    retry_success_rate: float = 1.0      # % of retries that eventually succeed

    # Timestamp
    measured_at: Optional[datetime] = None

    def calculate_improvements(self):
        """Calculate improvement percentages based on collected metrics."""
        # Time savings
        if self.phases_8_11_time_sequential > 0:
            self.time_savings_seconds = (
                self.phases_8_11_time_sequential - self.phases_8_11_time_parallel
            )
            self.time_savings_percent = (
                self.time_savings_seconds / self.phases_8_11_time_sequential * 100
            )

        # Overall workflow speedup
        if self.total_workflow_time_before > 0:
            time_diff = self.total_workflow_time_before - self.total_workflow_time_after
            self.workflow_speedup_percent = (
                time_diff / self.total_workflow_time_before * 100
            )

        # Cost difference
        self.cost_difference = self.total_cost_after - self.total_cost_before

        # Retry success rate
        if self.validation_retries_total > 0:
            successful_retries = self.validation_retries_total - self.validation_errors
            self.retry_success_rate = successful_retries / self.validation_retries_total

        self.measured_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for reporting."""
        return {
            "parsing_improvements": {
                "llm_calls_total": self.llm_calls_total,
                "json_parse_errors_before": self.json_parse_errors_before,
                "json_parse_errors_after": self.json_parse_errors_after,
                "validation_errors": self.validation_errors,
                "schema_compliance_rate": f"{self.schema_compliance_rate * 100:.1f}%",
            },
            "performance_improvements": {
                "phases_8_11_time_sequential": f"{self.phases_8_11_time_sequential:.2f}s",
                "phases_8_11_time_parallel": f"{self.phases_8_11_time_parallel:.2f}s",
                "time_savings": f"{self.time_savings_seconds:.2f}s ({self.time_savings_percent:.1f}%)",
                "workflow_speedup": f"{self.workflow_speedup_percent:.1f}%",
            },
            "cost_impact": {
                "total_cost_before": f"${self.total_cost_before:.4f}",
                "total_cost_after": f"${self.total_cost_after:.4f}",
                "cost_difference": f"${self.cost_difference:.4f}",
            },
            "quality_metrics": {
                "validation_retries_total": self.validation_retries_total,
                "retry_success_rate": f"{self.retry_success_rate * 100:.1f}%",
            },
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
        }


class MetricsCollector:
    """Collects and aggregates metrics for agents."""

    def __init__(self):
        self.metrics: Dict[str, AgentMetrics] = {}
        self._lock = False  # Simple lock flag (use threading.Lock in production)

        # Historical metrics (loaded from audit trail)
        self.historical_metrics: Dict[str, AgentMetrics] = {}

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

    def load_from_audit_trail(self, audit_file_path: Path) -> Dict[str, Any]:
        """
        Load historical agent metrics from audit trail.

        Args:
            audit_file_path: Path to audit trail JSON file

        Returns:
            Dictionary with loaded metrics summary
        """
        try:
            if not audit_file_path.exists():
                logger.debug(f"No audit trail found at {audit_file_path}")
                return {
                    "historical_agents": 0,
                    "historical_calls": 0,
                }

            with open(audit_file_path) as f:
                audit_entries = json.load(f)

            if not audit_entries:
                logger.debug("Audit trail is empty")
                return {
                    "historical_agents": 0,
                    "historical_calls": 0,
                }

            # Count calls per agent from audit trail
            self.historical_metrics = {}
            agent_call_counts = defaultdict(int)

            for entry in audit_entries:
                agent_name = entry.get("agent", "Unknown")
                agent_call_counts[agent_name] += 1

            # Create AgentMetrics for historical data
            for agent_name, call_count in agent_call_counts.items():
                self.historical_metrics[agent_name] = AgentMetrics(
                    agent_name=agent_name,
                    total_calls=call_count,
                    successful_calls=call_count,  # Assume all historical calls succeeded
                    failed_calls=0,
                )

            logger.info(
                f"Loaded historical metrics for {len(self.historical_metrics)} agents "
                f"({sum(agent_call_counts.values())} total calls) from audit trail"
            )

            return {
                "historical_agents": len(self.historical_metrics),
                "historical_calls": sum(agent_call_counts.values()),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted audit trail JSON: {e}")
            return {
                "historical_agents": 0,
                "historical_calls": 0,
            }
        except Exception as e:
            logger.error(f"Failed to load agent metrics from audit trail: {e}")
            return {
                "historical_agents": 0,
                "historical_calls": 0,
            }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics across all agents with historical and current breakdown.

        Returns:
            Summary dictionary
        """
        # Current session metrics
        if not self.metrics:
            current_summary = {
                "total_agents": 0,
                "total_calls": 0,
                "total_successful": 0,
                "total_failed": 0,
                "overall_success_rate": 0.0,
                "agents": {},  # Always include agents key, even if empty
            }
        else:
            total_calls = sum(m.total_calls for m in self.metrics.values())
            total_successful = sum(m.successful_calls for m in self.metrics.values())
            total_failed = sum(m.failed_calls for m in self.metrics.values())

            current_summary = {
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

        # Historical metrics
        historical_total_calls = sum(m.total_calls for m in self.historical_metrics.values())
        historical_summary = {
            "historical_agents": len(self.historical_metrics),
            "historical_calls": historical_total_calls,
            "historical_agents_breakdown": {
                name: m.total_calls
                for name, m in self.historical_metrics.items()
            },
        }

        # Merge and return
        return {**current_summary, **historical_summary}


# Global metrics collector instance
_global_metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _global_metrics
