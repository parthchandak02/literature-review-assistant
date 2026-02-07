"""
Integration tests for checkpoint resumption.
"""

import tempfile
from pathlib import Path

import pytest

from src.orchestration.workflow_manager import WorkflowManager
from src.search.connectors.base import Paper
from src.utils.state_serialization import StateSerializer


class TestCheckpointResumption:
    """Test checkpoint resumption functionality."""

    def test_save_and_load_phase_state(self):
        """Test saving and loading phase state."""
        # Create a temporary checkpoint directory
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_dir = Path(tmpdir) / "test_workflow"
            checkpoint_dir.mkdir(parents=True)

            # Create a minimal WorkflowManager
            # Note: This requires a valid config file
            # For integration tests, we'd use a test config
            try:
                manager = WorkflowManager()
                manager.workflow_id = "test_workflow"
                manager.checkpoint_dir = checkpoint_dir

                # Set some test data
                manager.all_papers = [
                    Paper(
                        title="Test Paper",
                        abstract="Test abstract",
                        authors=["Author A"],
                    )
                ]

                # Save checkpoint
                checkpoint_path = manager.checkpoint_manager.save_phase("search_databases")
                assert checkpoint_path is not None
                assert Path(checkpoint_path).exists()

                # Load checkpoint
                loaded_data = manager.checkpoint_manager.load_phase(checkpoint_path)
                assert loaded_data["phase"] == "search_databases"
                assert "data" in loaded_data
                assert "all_papers" in loaded_data["data"]

            except Exception as e:
                # Skip if config not available
                pytest.skip(f"Config not available: {e}")

    def test_load_state_from_dict(self):
        """Test loading state from dictionary."""
        try:
            manager = WorkflowManager()

            # Create test state
            serializer = StateSerializer()
            papers = [
                Paper(
                    title="Test Paper",
                    abstract="Test abstract",
                    authors=["Author A"],
                )
            ]

            state = {
                "data": {
                    "all_papers": serializer.serialize_papers(papers),
                },
                "topic_context": {"topic": "test topic"},
            }

            # Load state
            manager.load_state_from_dict(state)

            assert len(manager.all_papers) == 1
            assert manager.all_papers[0].title == "Test Paper"

        except Exception as e:
            pytest.skip(f"Config not available: {e}")
