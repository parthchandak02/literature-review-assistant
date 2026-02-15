"""LangGraph-first orchestration decision model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestrationProfile:
    """Policy that decides whether Temporal-level durability is needed."""

    default_backend: str = "langgraph"
    temporal_max_runtime_hours: int = 24
    temporal_max_human_wait_hours: int = 24
    temporal_requires_cross_service: bool = True


@dataclass(frozen=True)
class OrchestrationDecision:
    """Decision result for backend selection."""

    backend: str
    reason: str
    should_introduce_temporal: bool


def choose_orchestration_backend(
    estimated_runtime_hours: float,
    max_human_wait_hours: float,
    uses_cross_service_workers: bool,
    profile: OrchestrationProfile | None = None,
) -> OrchestrationDecision:
    """Returns LangGraph baseline and a clear trigger for Temporal adoption."""
    profile = profile or OrchestrationProfile()

    temporal_triggered = (
        estimated_runtime_hours > profile.temporal_max_runtime_hours
        or max_human_wait_hours > profile.temporal_max_human_wait_hours
        or (
            profile.temporal_requires_cross_service
            and uses_cross_service_workers
        )
    )

    if temporal_triggered:
        return OrchestrationDecision(
            backend="temporal",
            reason=(
                "runtime/human-wait/cross-service threshold exceeded; "
                "switching from LangGraph-only to Temporal-backed execution"
            ),
            should_introduce_temporal=True,
        )

    return OrchestrationDecision(
        backend=profile.default_backend,
        reason="LangGraph checkpointer is sufficient for this workload",
        should_introduce_temporal=False,
    )
