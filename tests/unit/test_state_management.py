"""
Unit tests for state management (checkpoint manager and state store).
"""

from pathlib import Path
from src.state.checkpoint_manager import CheckpointManager, WorkflowCheckpoint
from src.state.state_store import FileStateStore


class TestWorkflowCheckpoint:
    """Test WorkflowCheckpoint dataclass."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = WorkflowCheckpoint(
            checkpoint_id="test_123",
            workflow_id="workflow_1",
            phase="screening",
            state={"papers": 10},
            timestamp="2024-01-01T00:00:00",
            metadata={"version": "1.0"},
        )

        assert checkpoint.checkpoint_id == "test_123"
        assert checkpoint.workflow_id == "workflow_1"
        assert checkpoint.phase == "screening"
        assert checkpoint.state["papers"] == 10

    def test_checkpoint_to_dict(self):
        """Test checkpoint serialization."""
        checkpoint = WorkflowCheckpoint(
            checkpoint_id="test_123",
            workflow_id="workflow_1",
            phase="screening",
            state={"papers": 10},
            timestamp="2024-01-01T00:00:00",
            metadata={},
        )

        data = checkpoint.to_dict()
        assert data["checkpoint_id"] == "test_123"
        assert data["state"]["papers"] == 10

    def test_checkpoint_from_dict(self):
        """Test checkpoint deserialization."""
        data = {
            "checkpoint_id": "test_123",
            "workflow_id": "workflow_1",
            "phase": "screening",
            "state": {"papers": 10},
            "timestamp": "2024-01-01T00:00:00",
            "metadata": {},
        }

        checkpoint = WorkflowCheckpoint.from_dict(data)
        assert checkpoint.checkpoint_id == "test_123"
        assert checkpoint.state["papers"] == 10


class TestCheckpointManager:
    """Test CheckpointManager class."""

    def test_checkpoint_manager_initialization(self, tmp_path):
        """Test CheckpointManager initialization."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        assert manager.checkpoint_dir == Path(tmp_path)
        assert manager.checkpoint_dir.exists()

    def test_create_checkpoint(self, tmp_path):
        """Test creating a checkpoint."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        checkpoint = manager.create_checkpoint(
            workflow_id="workflow_1",
            phase="screening",
            state={"papers": 10, "screened": 5},
            metadata={"version": "1.0"},
        )

        assert checkpoint.workflow_id == "workflow_1"
        assert checkpoint.phase == "screening"
        assert checkpoint.state["papers"] == 10
        assert checkpoint.checkpoint_id in manager.checkpoints

    def test_save_checkpoint(self, tmp_path):
        """Test saving checkpoint to disk."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        checkpoint = manager.create_checkpoint(
            workflow_id="workflow_1", phase="screening", state={"papers": 10}
        )

        # create_checkpoint automatically saves
        # Check file exists
        checkpoint_file = tmp_path / f"{checkpoint.checkpoint_id}.json"
        assert checkpoint_file.exists()

    def test_load_checkpoint(self, tmp_path):
        """Test loading checkpoint from disk."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        checkpoint = manager.create_checkpoint(
            workflow_id="workflow_1", phase="screening", state={"papers": 10}
        )

        # create_checkpoint automatically saves
        # Use get_checkpoint to load
        loaded = manager.get_checkpoint(checkpoint.checkpoint_id)
        assert loaded is not None
        assert loaded.workflow_id == "workflow_1"
        assert loaded.state["papers"] == 10

    def test_get_latest_checkpoint(self, tmp_path):
        """Test getting latest checkpoint for workflow."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        _checkpoint1 = manager.create_checkpoint(
            workflow_id="workflow_1", phase="search", state={"papers": 5}
        )

        _checkpoint2 = manager.create_checkpoint(
            workflow_id="workflow_1", phase="screening", state={"papers": 10}
        )

        latest = manager.get_latest_checkpoint("workflow_1")
        assert latest is not None
        assert latest.phase == "screening"

    def test_list_checkpoints(self, tmp_path):
        """Test listing checkpoints."""
        manager = CheckpointManager(checkpoint_dir=str(tmp_path))

        manager.create_checkpoint("workflow_1", "phase1", {"data": 1})
        manager.create_checkpoint("workflow_1", "phase2", {"data": 2})
        manager.create_checkpoint("workflow_2", "phase1", {"data": 3})

        # Use get_latest_checkpoint to verify checkpoints exist
        latest1 = manager.get_latest_checkpoint("workflow_1")
        assert latest1 is not None

        latest2 = manager.get_latest_checkpoint("workflow_2")
        assert latest2 is not None


class TestFileStateStore:
    """Test FileStateStore class."""

    def test_file_state_store_initialization(self, tmp_path):
        """Test FileStateStore initialization."""
        store = FileStateStore(state_dir=str(tmp_path))

        assert store.state_dir == Path(tmp_path)
        assert store.state_dir.exists()

    def test_save_state(self, tmp_path):
        """Test saving state."""
        store = FileStateStore(state_dir=str(tmp_path))

        state = {"papers": 10, "screened": 5}
        result = store.save("test_key", state)

        assert result is True
        state_file = tmp_path / "test_key.json"
        assert state_file.exists()

    def test_load_state(self, tmp_path):
        """Test loading state."""
        store = FileStateStore(state_dir=str(tmp_path))

        state = {"papers": 10, "screened": 5}
        store.save("test_key", state)

        loaded = store.load("test_key")
        assert loaded is not None
        assert loaded["papers"] == 10
        assert loaded["screened"] == 5

    def test_load_nonexistent_state(self, tmp_path):
        """Test loading nonexistent state."""
        store = FileStateStore(state_dir=str(tmp_path))

        loaded = store.load("nonexistent")
        assert loaded is None

    def test_delete_state(self, tmp_path):
        """Test deleting state."""
        store = FileStateStore(state_dir=str(tmp_path))

        store.save("test_key", {"data": 1})
        assert store.exists("test_key")

        result = store.delete("test_key")
        assert result is True
        assert not store.exists("test_key")

    def test_exists(self, tmp_path):
        """Test checking if state exists."""
        store = FileStateStore(state_dir=str(tmp_path))

        assert not store.exists("test_key")

        store.save("test_key", {"data": 1})
        assert store.exists("test_key")

    def test_list_keys(self, tmp_path):
        """Test listing state keys."""
        store = FileStateStore(state_dir=str(tmp_path))

        store.save("key1", {"data": 1})
        store.save("key2", {"data": 2})
        store.save("key3", {"data": 3})

        keys = store.list_keys()
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys
