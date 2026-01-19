"""
Integration tests for state persistence.
"""

from src.state.checkpoint_manager import CheckpointManager
from src.state.state_store import FileStateStore


class TestStatePersistence:
    """Test state persistence integration."""

    def test_checkpoint_and_state_store_integration(self, tmp_path):
        """Test checkpoint manager with state store."""
        checkpoint_dir = tmp_path / "checkpoints"
        state_dir = tmp_path / "state"

        checkpoint_manager = CheckpointManager(checkpoint_dir=str(checkpoint_dir))
        state_store = FileStateStore(state_dir=str(state_dir))

        # Create checkpoint
        checkpoint = checkpoint_manager.create_checkpoint(
            workflow_id="workflow_1", phase="screening", state={"papers": 10, "screened": 5}
        )

        checkpoint_manager.save_checkpoint(checkpoint)

        # Save state separately
        state_store.save("workflow_1_state", checkpoint.state)

        # Load both
        loaded_checkpoint = checkpoint_manager.load_checkpoint(checkpoint.checkpoint_id)
        loaded_state = state_store.load("workflow_1_state")

        assert loaded_checkpoint is not None
        assert loaded_state is not None
        assert loaded_checkpoint.state["papers"] == 10
        assert loaded_state["papers"] == 10
