"""
Error Boundary

Provides error handling at phase boundaries to gracefully handle failures.
"""

from typing import Any, Callable, Dict, Optional

from ..utils.logging_config import get_logger
from .phases import PhaseResult, PhaseStatus, WorkflowPhase
from .workflow_state import WorkflowState

logger = get_logger(__name__)


class PhaseError(Exception):
    """Base exception for phase errors"""
    pass


class ValidationError(PhaseError):
    """Raised when phase validation fails"""
    pass


class LLMError(PhaseError):
    """Raised when LLM operations fail"""
    pass


class DatabaseError(PhaseError):
    """Raised when database operations fail"""
    pass


class PhaseErrorBoundary:
    """
    Handles errors at phase boundaries.
    
    Provides graceful error handling and recovery for workflow phases.
    """
    
    def __init__(
        self,
        enable_recovery: bool = True,
        max_retries: int = 2
    ):
        """
        Initialize error boundary.
        
        Args:
            enable_recovery: Whether to attempt recovery from errors
            max_retries: Maximum retry attempts for recoverable errors
        """
        self.enable_recovery = enable_recovery
        self.max_retries = max_retries
        self.error_count: Dict[str, int] = {}
    
    def execute_with_boundary(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        **kwargs
    ) -> PhaseResult:
        """
        Execute phase with error boundary protection.
        
        Args:
            phase: WorkflowPhase to execute
            state: Current workflow state
            **kwargs: Additional phase arguments
        
        Returns:
            PhaseResult from phase execution
        """
        phase_name = phase.name
        
        try:
            # Execute phase
            result = phase.execute(**kwargs)
            
            # Reset error count on success
            if result.success:
                self.error_count[phase_name] = 0
            
            return result
            
        except ValidationError as e:
            return self._handle_validation_error(phase, state, e)
        
        except LLMError as e:
            return self._handle_llm_error(phase, state, e)
        
        except DatabaseError as e:
            return self._handle_database_error(phase, state, e)
        
        except Exception as e:
            return self._handle_unknown_error(phase, state, e)
    
    def _handle_validation_error(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        error: ValidationError
    ) -> PhaseResult:
        """Handle validation errors"""
        logger.error(
            f"Validation error in {phase.name}: {str(error)}",
            exc_info=True
        )
        
        return PhaseResult(
            phase_name=phase.name,
            status=PhaseStatus.FAILED,
            error=error,
            message=f"Validation failed: {str(error)}"
        )
    
    def _handle_llm_error(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        error: LLMError
    ) -> PhaseResult:
        """Handle LLM-related errors"""
        logger.error(
            f"LLM error in {phase.name}: {str(error)}",
            exc_info=True
        )
        
        # Check if we should retry
        error_count = self.error_count.get(phase.name, 0)
        
        if self.enable_recovery and error_count < self.max_retries:
            self.error_count[phase.name] = error_count + 1
            logger.info(
                f"Attempting retry {error_count + 1}/{self.max_retries} "
                f"for {phase.name}"
            )
            # Could implement retry logic here
        
        return PhaseResult(
            phase_name=phase.name,
            status=PhaseStatus.FAILED,
            error=error,
            message=f"LLM error: {str(error)}"
        )
    
    def _handle_database_error(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        error: DatabaseError
    ) -> PhaseResult:
        """Handle database-related errors"""
        logger.error(
            f"Database error in {phase.name}: {str(error)}",
            exc_info=True
        )
        
        return PhaseResult(
            phase_name=phase.name,
            status=PhaseStatus.FAILED,
            error=error,
            message=f"Database error: {str(error)}"
        )
    
    def _handle_unknown_error(
        self,
        phase: WorkflowPhase,
        state: WorkflowState,
        error: Exception
    ) -> PhaseResult:
        """Handle unexpected errors"""
        logger.error(
            f"Unexpected error in {phase.name}: {str(error)}",
            exc_info=True
        )
        
        return PhaseResult(
            phase_name=phase.name,
            status=PhaseStatus.FAILED,
            error=error,
            message=f"Unexpected error: {str(error)}"
        )
    
    def reset_error_count(self, phase_name: Optional[str] = None):
        """
        Reset error count for a phase or all phases.
        
        Args:
            phase_name: Specific phase to reset, or None for all
        """
        if phase_name:
            self.error_count[phase_name] = 0
        else:
            self.error_count.clear()
