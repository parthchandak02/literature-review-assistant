"""
E2E tests for workflow with state persistence.
"""

import pytest
import yaml

from src.orchestration.workflow_manager import WorkflowManager
from src.state.checkpoint_manager import CheckpointManager
from tests.fixtures.workflow_configs import get_test_workflow_config


@pytest.fixture
def workflow_with_checkpoints(tmp_path):
    """Create workflow config with checkpoint directory."""
    config = get_test_workflow_config()
    config_file = tmp_path / "workflow.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    return str(config_file), str(checkpoint_dir)


def test_workflow_checkpoint_creation(workflow_with_checkpoints):
    """Test workflow checkpoint creation."""
    config_path, checkpoint_dir = workflow_with_checkpoints

    _manager = WorkflowManager(config_path)
    checkpoint_manager = CheckpointManager(checkpoint_dir=checkpoint_dir)

    # Create checkpoint
    checkpoint = checkpoint_manager.create_checkpoint(
        workflow_id="test_workflow", phase="search", state={"papers": 10}
    )

    checkpoint_manager.save_checkpoint(checkpoint)

    # Verify checkpoint exists
    loaded = checkpoint_manager.load_checkpoint(checkpoint.checkpoint_id)
    assert loaded is not None
    assert loaded.state["papers"] == 10
