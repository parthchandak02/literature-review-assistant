"""
Phase Registry

Declarative phase registration system for workflow orchestration.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PhaseDefinition:
    """Definition of a workflow phase."""

    name: str
    phase_number: int
    dependencies: List[str]  # Names of phases that must complete first
    handler: Callable  # Function to execute this phase
    checkpoint: bool = True  # Whether to checkpoint after completion
    required: bool = True  # Whether phase is required or optional
    description: str = ""  # Human-readable description
    config_key: Optional[str] = None  # Config key to check if enabled (e.g., "manubot.enabled")


class PhaseRegistry:
    """Registry for workflow phases with dependency management."""

    def __init__(self):
        """Initialize phase registry."""
        self.phases: Dict[str, PhaseDefinition] = {}
        self._phase_order: List[str] = []

    def register(self, phase: PhaseDefinition) -> "PhaseRegistry":
        """
        Register a phase.

        Args:
            phase: Phase definition to register

        Returns:
            Self for method chaining
        """
        if phase.name in self.phases:
            logger.warning(f"Phase '{phase.name}' already registered, overwriting")

        self.phases[phase.name] = phase
        if phase.name not in self._phase_order:
            self._phase_order.append(phase.name)

        return self

    def get_phase(self, name: str) -> Optional[PhaseDefinition]:
        """
        Get phase definition by name.

        Args:
            name: Phase name

        Returns:
            Phase definition or None if not found
        """
        return self.phases.get(name)

    def get_dependencies(self, phase_name: str) -> List[str]:
        """
        Get dependencies for a phase.

        Args:
            phase_name: Phase name

        Returns:
            List of dependency phase names
        """
        phase = self.get_phase(phase_name)
        return phase.dependencies if phase else []

    def get_execution_order(self) -> List[str]:
        """
        Get phases in execution order (topological sort based on dependencies).

        Returns:
            List of phase names in execution order
        """
        # Build dependency graph
        in_degree: Dict[str, int] = dict.fromkeys(self.phases.keys(), 0)
        graph: Dict[str, List[str]] = {name: [] for name in self.phases.keys()}

        for phase_name, phase in self.phases.items():
            for dep in phase.dependencies:
                if dep in self.phases:
                    graph[dep].append(phase_name)
                    in_degree[phase_name] += 1

        # Topological sort using Kahn's algorithm
        queue: List[str] = [name for name, degree in in_degree.items() if degree == 0]
        result: List[str] = []

        while queue:
            # Sort queue by phase_number for deterministic ordering
            queue.sort(key=lambda name: self.phases[name].phase_number)
            current = queue.pop(0)
            result.append(current)

            for dependent in graph[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Check for circular dependencies
        if len(result) != len(self.phases):
            missing = set(self.phases.keys()) - set(result)
            raise ValueError(
                f"Circular dependency detected or missing dependencies. "
                f"Phases not in execution order: {missing}"
            )

        return result

    def get_all_dependencies(
        self, phase_name: str, visited: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Recursively get all dependencies for a phase (transitive closure).

        Args:
            phase_name: Phase name
            visited: Set of already visited phases (for cycle detection)

        Returns:
            List of all dependency phase names (including transitive)
        """
        if visited is None:
            visited = set()

        if phase_name in visited:
            return []  # Cycle detected, return empty

        visited.add(phase_name)

        phase = self.get_phase(phase_name)
        if not phase:
            return []

        all_deps = []
        for dep in phase.dependencies:
            # Get transitive dependencies
            all_deps.extend(self.get_all_dependencies(dep, visited.copy()))
            if dep not in all_deps:
                all_deps.append(dep)

        return all_deps

    def validate_dependencies(self) -> List[str]:
        """
        Validate that all dependencies exist.

        Returns:
            List of errors (empty if valid)
        """
        errors = []
        for phase_name, phase in self.phases.items():
            for dep in phase.dependencies:
                if dep not in self.phases:
                    errors.append(
                        f"Phase '{phase_name}' depends on '{dep}' which is not registered"
                    )
        return errors

    def __len__(self) -> int:
        """Return number of registered phases."""
        return len(self.phases)

    def __contains__(self, phase_name: str) -> bool:
        """Check if phase is registered."""
        return phase_name in self.phases
