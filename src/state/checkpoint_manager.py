"""
Checkpoint Manager for Workflow State

Enables checkpoint/resume functionality for workflows.
"""

import json
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCheckpoint:
    """Represents a workflow checkpoint."""

    checkpoint_id: str
    workflow_id: str
    phase: str
    state: Dict[str, Any]
    timestamp: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowCheckpoint":
        """Create from dictionary."""
        return cls(**data)


class CheckpointManager:
    """Manages workflow checkpoints."""

    def __init__(self, checkpoint_dir: str = "data/checkpoints"):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoints
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints: Dict[str, WorkflowCheckpoint] = {}

    def create_checkpoint(
        self,
        workflow_id: str,
        phase: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowCheckpoint:
        """
        Create a checkpoint.

        Args:
            workflow_id: Workflow identifier
            phase: Current workflow phase
            state: Workflow state dictionary
            metadata: Optional metadata

        Returns:
            Created checkpoint
        """
        checkpoint_id = f"{workflow_id}_{phase}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            phase=phase,
            state=state,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
        )

        self.checkpoints[checkpoint_id] = checkpoint
        self._save_checkpoint(checkpoint)

        logger.info(f"Created checkpoint: {checkpoint_id} at phase: {phase}")
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[WorkflowCheckpoint]:
        """
        Get checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint or None
        """
        if checkpoint_id in self.checkpoints:
            return self.checkpoints[checkpoint_id]

        # Try to load from disk
        return self._load_checkpoint(checkpoint_id)

    def get_latest_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        """
        Get latest checkpoint for a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Latest checkpoint or None
        """
        workflow_checkpoints = [
            cp for cp in self.checkpoints.values() if cp.workflow_id == workflow_id
        ]

        if not workflow_checkpoints:
            # Try loading from disk
            workflow_checkpoints = self._load_workflow_checkpoints(workflow_id)

        if not workflow_checkpoints:
            return None

        # Sort by timestamp and return latest
        workflow_checkpoints.sort(key=lambda x: x.timestamp, reverse=True)
        return workflow_checkpoints[0]

    def _save_checkpoint(self, checkpoint: WorkflowCheckpoint):
        """Save checkpoint to disk."""
        checkpoint_file = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"

        try:
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}", exc_info=True)

    def _load_checkpoint(self, checkpoint_id: str) -> Optional[WorkflowCheckpoint]:
        """Load checkpoint from disk."""
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file, "r") as f:
                data = json.load(f)
                checkpoint = WorkflowCheckpoint.from_dict(data)
                self.checkpoints[checkpoint_id] = checkpoint
                return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}", exc_info=True)
            return None

    def _load_workflow_checkpoints(self, workflow_id: str) -> list:
        """Load all checkpoints for a workflow from disk."""
        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob(f"{workflow_id}_*.json"):
            try:
                with open(checkpoint_file, "r") as f:
                    data = json.load(f)
                    checkpoint = WorkflowCheckpoint.from_dict(data)
                    checkpoints.append(checkpoint)
                    self.checkpoints[checkpoint.checkpoint_id] = checkpoint
            except Exception as e:
                logger.error(f"Failed to load checkpoint file {checkpoint_file}: {e}")

        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str):
        """
        Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
        """
        if checkpoint_id in self.checkpoints:
            del self.checkpoints[checkpoint_id]

        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info(f"Deleted checkpoint: {checkpoint_id}")
