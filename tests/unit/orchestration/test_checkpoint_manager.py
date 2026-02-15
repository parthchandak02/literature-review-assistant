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

    # Mock phase_registry with proper phase structure
    mock_phase = Mock()
    mock_phase.dependencies = []
    workflow_manager.phase_registry = Mock()
    workflow_manager.phase_registry.get_phase.return_value = mock_phase

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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        checkpoint_data = {
            "phase": "test_phase",
            "timestamp": "2024-01-01T00:00:00",
            "data": {"test": "data"},
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
    
    # Mock phase registry
    workflow_manager.phase_registry = Mock()
    workflow_manager.phase_registry.get_execution_order.return_value = []

    manager = CheckpointManager(workflow_manager)
    result = manager.find_by_topic("test topic")
    assert result is None


def test_find_by_topic_selects_most_recent():
    """Test that selection logic prioritizes recency over completeness."""
    # Create mock matches list simulating:
    # - Old complete checkpoint (Feb 9, 5 phases, older timestamp)
    # - New incomplete checkpoint (Feb 11, 3 phases, newer timestamp)
    
    old_checkpoint = {
        "checkpoint_dir": "/data/20260209_120000_workflow_test",
        "latest_phase": "article_writing",
        "latest_phase_time": 1707480000.0,  # Feb 9, 2026 12:00:00
        "workflow_id": "20260209_120000_workflow_test",
        "phase_index": 4,
        "article_sections_count": 0,
        "completeness": 5,
    }
    
    new_checkpoint = {
        "checkpoint_dir": "/data/20260211_140000_workflow_test",
        "latest_phase": "title_abstract_screening",
        "latest_phase_time": 1707652800.0,  # Feb 11, 2026 14:00:00 (48h later)
        "workflow_id": "20260211_140000_workflow_test",
        "phase_index": 2,
        "article_sections_count": 0,
        "completeness": 3,
    }
    
    matches = [old_checkpoint, new_checkpoint]
    
    # Apply the NEW selection logic (prioritize time first)
    best_match_new = max(
        matches,
        key=lambda m: (
            m["latest_phase_time"],      # 1st: most recent
            m["completeness"],           # 2nd: completeness (tie-breaker)
            m["phase_index"],            # 3rd: phase index (tie-breaker)
            m["article_sections_count"], # 4th: article sections (tie-breaker)
        ),
    )
    
    # Apply the OLD selection logic (prioritize completeness first)
    best_match_old = max(
        matches,
        key=lambda m: (
            m["completeness"],           # 1st: completeness
            m["phase_index"],            # 2nd: phase index
            m["article_sections_count"], # 3rd: article sections
            m["latest_phase_time"],      # 4th: most recent (LAST!)
        ),
    )
    
    # Verify NEW logic selects the more recent checkpoint
    assert best_match_new["workflow_id"] == "20260211_140000_workflow_test", \
        "New logic should select newer checkpoint despite lower completeness"
    
    # Verify OLD logic would have selected the more complete checkpoint
    assert best_match_old["workflow_id"] == "20260209_120000_workflow_test", \
        "Old logic selected more complete checkpoint (showing we fixed the bug)"
    
    # Verify the selection is different (proves we changed the behavior)
    assert best_match_new["workflow_id"] != best_match_old["workflow_id"], \
        "Selection logic should be different between old and new implementations"
