"""
Unit tests for CheckpointManager.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock
from src.orchestration.checkpoint_manager import CheckpointManager


def test_checkpoint_manager_initialization():
    """Test CheckpointManager initialization."""
    workflow_manager = Mock()
    workflow_manager.checkpoint_dir = Path("/tmp/test")
    workflow_manager.save_checkpoints = True
    
    manager = CheckpointManager(workflow_manager)
    assert manager.workflow_manager == workflow_manager
    assert manager.checkpoint_dir == Path("/tmp/test")
    assert manager.save_checkpoints is True


def test_save_phase_disabled():
    """Test that saving is skipped when disabled."""
    workflow_manager = Mock()
    workflow_manager.checkpoint_dir = Path("/tmp/test")
    workflow_manager.save_checkpoints = False
    workflow_manager.workflow_id = "test_id"
    workflow_manager.topic_context = Mock()
    workflow_manager.topic_context.to_dict.return_value = {"topic": "test"}
    workflow_manager.prisma_counter = Mock()
    workflow_manager.prisma_counter.get_counts.return_value = {}
    workflow_manager.prisma_counter.get_database_breakdown.return_value = {}
    workflow_manager._serialize_phase_data = Mock(return_value={})
    workflow_manager.phase_registry = Mock()
    workflow_manager.phase_registry.get_phase.return_value = None
    workflow_manager._get_phase_dependencies = Mock(return_value=[])
    
    manager = CheckpointManager(workflow_manager)
    result = manager.save_phase("test_phase")
    assert result is None


def test_load_phase():
    """Test loading a phase checkpoint."""
    workflow_manager = Mock()
    workflow_manager.checkpoint_dir = Path("/tmp/test")
    workflow_manager.save_checkpoints = True
    
    manager = CheckpointManager(workflow_manager)
    
    # Create temporary checkpoint file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        checkpoint_data = {
            "phase": "test_phase",
            "timestamp": "2024-01-01T00:00:00",
            "data": {"test": "data"}
        }
        json.dump(checkpoint_data, f)
        checkpoint_path = f.name
    
    try:
        result = manager.load_phase(checkpoint_path)
        assert result is not None
        assert result["phase"] == "test_phase"
        assert result["data"]["test"] == "data"
    finally:
        Path(checkpoint_path).unlink()


def test_load_phase_not_found():
    """Test loading non-existent checkpoint."""
    workflow_manager = Mock()
    workflow_manager.checkpoint_dir = Path("/tmp/test")
    workflow_manager.save_checkpoints = True
    
    manager = CheckpointManager(workflow_manager)
    result = manager.load_phase("/nonexistent/path.json")
    assert result is None


def test_find_by_topic_no_checkpoints():
    """Test finding checkpoint when directory doesn't exist."""
    workflow_manager = Mock()
    workflow_manager.checkpoint_dir = Path("/tmp/nonexistent")
    workflow_manager.save_checkpoints = True
    
    manager = CheckpointManager(workflow_manager)
    result = manager.find_by_topic("test topic")
    assert result is None
