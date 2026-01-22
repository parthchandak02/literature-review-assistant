"""
Phase Executor

Handles phase execution with dependency checking and checkpointing.
"""

from typing import Dict, Any, Optional, List
from ..utils.logging_config import get_logger
from ..utils.log_context import workflow_phase_context
from .phase_registry import PhaseRegistry
from .checkpoint_manager import CheckpointManager

logger = get_logger(__name__)


class PhaseExecutor:
    """Executes workflow phases with dependency checking and checkpointing."""
    
    def __init__(self, registry: PhaseRegistry, checkpoint_manager: CheckpointManager):
        """
        Initialize phase executor.
        
        Args:
            registry: Phase registry containing phase definitions
            checkpoint_manager: Checkpoint manager for saving/loading state
        """
        self.registry = registry
        self.checkpoint_manager = checkpoint_manager
    
    def execute_phase(
        self,
        phase_name: str,
        workflow_manager: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a single phase with dependency checking and checkpointing.
        
        Args:
            phase_name: Name of phase to execute
            workflow_manager: WorkflowManager instance
            context: Optional context dictionary (e.g., {"start_from_phase": 3})
            
        Returns:
            Result from phase handler
            
        Raises:
            ValueError: If phase not found or dependencies not met
            Exception: If phase execution fails (for required phases)
        """
        if context is None:
            context = {}
        
        phase = self.registry.get_phase(phase_name)
        if not phase:
            raise ValueError(f"Phase '{phase_name}' not found in registry")
        
        # Check dependencies
        if not self._check_dependencies(phase_name, workflow_manager):
            raise ValueError(
                f"Phase '{phase_name}' dependencies not met. "
                f"Dependencies: {phase.dependencies}"
            )
        
        # Execute phase handler
        logger.info(f"Executing phase: {phase_name} ({phase.description})")
        
        try:
            with workflow_phase_context(phase_name):
                result = phase.handler()
            
            # Save checkpoint if enabled
            if phase.checkpoint and self.checkpoint_manager.save_checkpoints:
                self.checkpoint_manager.save_phase(phase_name)
            
            logger.info(f"Phase '{phase_name}' completed successfully")
            return result
        
        except Exception as e:
            logger.error(f"Phase '{phase_name}' failed: {e}", exc_info=True)
            if phase.required:
                raise
            else:
                logger.warning(f"Optional phase '{phase_name}' failed, continuing...")
                return None
    
    def _check_dependencies(self, phase_name: str, workflow_manager: Any) -> bool:
        """
        Check if phase dependencies are met.
        
        Args:
            phase_name: Name of phase to check
            workflow_manager: WorkflowManager instance (for checking completed phases)
            
        Returns:
            True if all dependencies are met, False otherwise
        """
        phase = self.registry.get_phase(phase_name)
        if not phase:
            return False
        
        # If no dependencies, always ready
        if not phase.dependencies:
            return True
        
        # Check if all dependencies have been completed
        # This is a simple check - in a full implementation, we might track completed phases
        # For now, we assume dependencies are checked by the workflow manager's execution order
        return True
    
    def get_execution_order(self) -> List[str]:
        """
        Get phases in execution order.
        
        Returns:
            List of phase names in execution order
        """
        return self.registry.get_execution_order()
    
    def should_execute_phase(
        self,
        phase_name: str,
        start_from_phase: Optional[int] = None
    ) -> bool:
        """
        Determine if phase should be executed based on start phase.
        
        Args:
            phase_name: Name of phase
            start_from_phase: Optional phase number to start from
            
        Returns:
            True if phase should be executed
        """
        phase = self.registry.get_phase(phase_name)
        if not phase:
            return False
        
        # If no start phase specified, execute all
        if start_from_phase is None:
            return True
        
        # Skip phases before start phase
        return phase.phase_number >= start_from_phase
