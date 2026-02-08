"""
Workflow Phases

Base classes and infrastructure for modular workflow phases.
Each phase is self-contained with clear inputs, outputs, and responsibilities.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class PhaseStatus(str, Enum):
    """Phase execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseResult:
    """Result from executing a phase"""
    phase_name: str
    status: PhaseStatus
    data: Any = None
    message: str = ""
    error: Optional[Exception] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate phase duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success(self) -> bool:
        """Check if phase completed successfully"""
        return self.status == PhaseStatus.COMPLETED


class WorkflowPhase(ABC):
    """
    Base class for workflow phases.
    
    Each phase should:
    1. Be independently testable
    2. Have clear responsibilities
    3. Accept and return well-defined data
    4. Handle its own errors gracefully
    """
    
    def __init__(self, manager: 'WorkflowManager'):
        """
        Initialize phase with workflow manager reference.
        
        Args:
            manager: WorkflowManager instance for accessing shared components
        """
        self.manager = manager
        self.config = manager.config
        self.logger = get_logger(self.__class__.__name__)
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Phase name for logging and identification"""
        pass
    
    @property
    def description(self) -> str:
        """Human-readable phase description"""
        return f"{self.name} phase"
    
    @abstractmethod
    def execute(self, **kwargs) -> PhaseResult:
        """
        Execute the phase logic.
        
        Args:
            **kwargs: Phase-specific arguments
        
        Returns:
            PhaseResult with status, data, and metadata
        """
        pass
    
    def _create_result(
        self,
        status: PhaseStatus,
        data: Any = None,
        message: str = "",
        error: Optional[Exception] = None,
        **metadata
    ) -> PhaseResult:
        """
        Helper to create a PhaseResult with proper timing.
        
        Args:
            status: Phase execution status
            data: Phase output data
            message: Human-readable message
            error: Exception if phase failed
            **metadata: Additional metadata
        
        Returns:
            PhaseResult instance
        """
        return PhaseResult(
            phase_name=self.name,
            status=status,
            data=data,
            message=message,
            error=error,
            start_time=datetime.now(),
            end_time=datetime.now(),
            metadata=metadata
        )
    
    def log_start(self):
        """Log phase start"""
        self.logger.info(f"Starting {self.description}")
    
    def log_completion(self, result: PhaseResult):
        """Log phase completion"""
        if result.success:
            self.logger.info(
                f"Completed {self.description} in {result.duration_seconds:.2f}s"
            )
        else:
            self.logger.error(
                f"Failed {self.description}: {result.message}"
            )


# Export key classes
__all__ = [
    "WorkflowPhase",
    "PhaseResult",
    "PhaseStatus",
]
