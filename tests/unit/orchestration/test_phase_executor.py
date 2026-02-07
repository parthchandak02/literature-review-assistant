"""
Unit tests for PhaseExecutor.
"""

from unittest.mock import Mock

import pytest

from src.orchestration.checkpoint_manager import CheckpointManager
from src.orchestration.phase_executor import PhaseExecutor
from src.orchestration.phase_registry import PhaseDefinition, PhaseRegistry


def test_phase_executor_initialization():
    """Test PhaseExecutor initialization."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)

    executor = PhaseExecutor(registry, checkpoint_manager)
    assert executor.registry == registry
    assert executor.checkpoint_manager == checkpoint_manager


def test_execute_phase_success():
    """Test successful phase execution."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)
    checkpoint_manager.save_checkpoints = True
    checkpoint_manager.save_phase = Mock(return_value="/tmp/checkpoint.json")

    def handler():
        return "success"

    phase = PhaseDefinition(
        name="test_phase", phase_number=1, dependencies=[], handler=handler, checkpoint=True
    )
    registry.register(phase)

    workflow_manager = Mock()
    executor = PhaseExecutor(registry, checkpoint_manager)

    result = executor.execute_phase("test_phase", workflow_manager)
    assert result == "success"
    checkpoint_manager.save_phase.assert_called_once_with("test_phase")


def test_execute_phase_not_found():
    """Test executing non-existent phase."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)
    workflow_manager = Mock()

    executor = PhaseExecutor(registry, checkpoint_manager)

    with pytest.raises(ValueError, match="not found"):
        executor.execute_phase("nonexistent", workflow_manager)


def test_execute_phase_optional_failure():
    """Test that optional phase failures don't raise."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)
    checkpoint_manager.save_checkpoints = True

    def failing_handler():
        raise Exception("Phase failed")

    phase = PhaseDefinition(
        name="optional_phase",
        phase_number=1,
        dependencies=[],
        handler=failing_handler,
        required=False,
    )
    registry.register(phase)

    workflow_manager = Mock()
    executor = PhaseExecutor(registry, checkpoint_manager)

    # Should not raise, but return None
    result = executor.execute_phase("optional_phase", workflow_manager)
    assert result is None


def test_execute_phase_required_failure():
    """Test that required phase failures raise."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)
    checkpoint_manager.save_checkpoints = True

    def failing_handler():
        raise Exception("Phase failed")

    phase = PhaseDefinition(
        name="required_phase",
        phase_number=1,
        dependencies=[],
        handler=failing_handler,
        required=True,
    )
    registry.register(phase)

    workflow_manager = Mock()
    executor = PhaseExecutor(registry, checkpoint_manager)

    with pytest.raises(Exception, match="Phase failed"):
        executor.execute_phase("required_phase", workflow_manager)


def test_should_execute_phase():
    """Test phase execution decision based on start phase."""
    registry = PhaseRegistry()
    checkpoint_manager = Mock(spec=CheckpointManager)

    def handler():
        pass

    phase = PhaseDefinition("test_phase", 5, [], handler)
    registry.register(phase)

    executor = PhaseExecutor(registry, checkpoint_manager)

    # Should execute if no start phase
    assert executor.should_execute_phase("test_phase", None) is True

    # Should execute if phase number >= start phase
    assert executor.should_execute_phase("test_phase", 5) is True
    assert executor.should_execute_phase("test_phase", 4) is True

    # Should not execute if phase number < start phase
    assert executor.should_execute_phase("test_phase", 6) is False
