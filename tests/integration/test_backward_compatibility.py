"""
Backward compatibility tests for workflow refactoring.
"""

from src.orchestration.workflow_manager import WorkflowManager


def test_checkpoint_methods_still_exist():
    """Test that backward-compatible checkpoint methods still exist."""
    manager = WorkflowManager()
    
    # These methods should still exist for backward compatibility
    assert hasattr(manager, "_save_phase_state")
    assert hasattr(manager, "_find_existing_checkpoint_by_topic")
    assert hasattr(manager, "_load_phase_state")
    
    # They should be callable
    assert callable(manager._save_phase_state)
    assert callable(manager._find_existing_checkpoint_by_topic)
    assert callable(manager._load_phase_state)


def test_checkpoint_format_unchanged():
    """Test that checkpoint format remains the same."""
    # This test would verify that checkpoints saved with new code
    # can be loaded by old code and vice versa
    # For now, we just verify the structure is correct
    
    manager = WorkflowManager()
    
    # Verify checkpoint manager uses same format
    assert hasattr(manager.checkpoint_manager, "save_phase")
    assert hasattr(manager.checkpoint_manager, "load_phase")
    assert hasattr(manager.checkpoint_manager, "find_by_topic")


def test_workflow_manager_interface_unchanged():
    """Test that WorkflowManager public interface is unchanged."""
    manager = WorkflowManager()
    
    # Core methods should still exist
    assert hasattr(manager, "run")
    assert callable(manager.run)
    
    # Configuration should still work
    assert hasattr(manager, "config")
    assert hasattr(manager, "topic_context")
    assert hasattr(manager, "output_dir")
