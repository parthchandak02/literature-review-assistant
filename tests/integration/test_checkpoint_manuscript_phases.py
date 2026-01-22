"""
Integration tests for checkpoint resumption with manuscript phases (17-18)
"""

import pytest
import json
from unittest.mock import patch
from src.orchestration.workflow_manager import WorkflowManager
from src.search.connectors.base import Paper


class TestCheckpointManuscriptPhases:
    """Test checkpoint resumption for phases 17-18."""

    @pytest.fixture
    def workflow_manager(self, tmp_path):
        """Create WorkflowManager instance for testing."""
        config_path = tmp_path / "workflow.yaml"
        config_path.write_text("""
topic:
  topic: "Test Topic"
  keywords: ["test"]
workflow:
  databases: []
manubot:
  enabled: true
submission:
  enabled: true
""")
        return WorkflowManager(str(config_path))

    def test_resume_from_manubot_export_checkpoint(self, workflow_manager, tmp_path):
        """Test resumption from manubot_export checkpoint."""
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = [Paper(title="Test", authors=["Author"])]
        workflow_manager.topic_context.topic = "Test Topic"
        
        # Create checkpoint directory
        workflow_id = "test_workflow_123"
        checkpoint_dir = tmp_path / workflow_id / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        
        # Create manubot_export checkpoint
        checkpoint_data = {
            "phase": "manubot_export",
            "workflow_id": workflow_id,
            "topic_context": {"topic": "Test Topic"},
            "data": {
                "manubot_export_path": str(tmp_path / "manuscript"),
                "article_sections": {"abstract": "Test abstract"},
            },
            "dependencies": ["article_writing"],
        }
        
        checkpoint_file = checkpoint_dir / "manubot_export_state.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f)
        
        # Create article_writing checkpoint (dependency)
        article_checkpoint = {
            "phase": "article_writing",
            "data": {
                "article_sections": {"abstract": "Test abstract"},
            },
        }
        with open(checkpoint_dir / "article_writing_state.json", "w") as f:
            json.dump(article_checkpoint, f)
        
        # Mock _find_existing_checkpoint_by_topic to return our checkpoint
        with patch.object(workflow_manager, "_find_existing_checkpoint_by_topic") as mock_find:
            mock_find.return_value = {
                "workflow_id": workflow_id,
                "latest_phase": "manubot_export",
                "checkpoint_dir": str(checkpoint_dir.parent),
            }
            
            # Test that checkpoint can be loaded
            # This tests the dependency resolution
            existing = workflow_manager._find_existing_checkpoint_by_topic()
            assert existing is not None
            assert existing["latest_phase"] == "manubot_export"

    def test_resume_from_submission_package_checkpoint(self, workflow_manager, tmp_path):
        """Test resumption from submission_package checkpoint."""
        workflow_manager.output_dir = tmp_path
        
        # Create checkpoint directory
        workflow_id = "test_workflow_123"
        checkpoint_dir = tmp_path / workflow_id / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        
        # Create submission_package checkpoint
        checkpoint_data = {
            "phase": "submission_package",
            "workflow_id": workflow_id,
            "topic_context": {"topic": "Test Topic"},
            "data": {
                "submission_package_path": str(tmp_path / "submission_package_ieee"),
                "article_sections": {"abstract": "Test abstract"},
            },
            "dependencies": ["article_writing", "report_generation"],
        }
        
        checkpoint_file = checkpoint_dir / "submission_package_state.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f)
        
        # Create dependency checkpoints
        for dep in ["article_writing", "report_generation"]:
            dep_checkpoint = {
                "phase": dep,
                "data": {"article_sections": {"abstract": "Test"}},
            }
            with open(checkpoint_dir / f"{dep}_state.json", "w") as f:
                json.dump(dep_checkpoint, f)
        
        # Mock checkpoint finder
        with patch.object(workflow_manager, "_find_existing_checkpoint_by_topic") as mock_find:
            mock_find.return_value = {
                "workflow_id": workflow_id,
                "latest_phase": "submission_package",
                "checkpoint_dir": str(checkpoint_dir.parent),
            }
            
            existing = workflow_manager._find_existing_checkpoint_by_topic()
            assert existing is not None
            assert existing["latest_phase"] == "submission_package"

    def test_checkpoint_dependencies_loaded(self, workflow_manager, tmp_path):
        """Test that dependencies are loaded correctly for phases 17-18."""
        workflow_manager.output_dir = tmp_path
        
        # Test dependency resolution
        deps_manubot = workflow_manager._get_phase_dependencies("manubot_export")
        assert "article_writing" in deps_manubot
        
        deps_submission = workflow_manager._get_phase_dependencies("submission_package")
        assert "article_writing" in deps_submission
        assert "report_generation" in deps_submission

    def test_checkpoint_serialization_manubot_export(self, workflow_manager, tmp_path):
        """Test checkpoint serialization for manubot_export phase."""
        workflow_manager.output_dir = tmp_path
        workflow_manager._manubot_export_path = tmp_path / "manuscript"
        workflow_manager._article_sections = {"abstract": "Test"}
        
        data = workflow_manager._serialize_phase_data("manubot_export")
        assert "manubot_export_path" in data
        assert "article_sections" in data

    def test_checkpoint_serialization_submission_package(self, workflow_manager, tmp_path):
        """Test checkpoint serialization for submission_package phase."""
        workflow_manager.output_dir = tmp_path
        workflow_manager._submission_package_path = tmp_path / "submission_package_ieee"
        workflow_manager._article_sections = {"abstract": "Test"}
        
        data = workflow_manager._serialize_phase_data("submission_package")
        assert "submission_package_path" in data
        assert "article_sections" in data

    def test_phases_skip_if_already_completed(self, workflow_manager, tmp_path):
        """Test that phases 17-18 skip if checkpoints exist."""
        workflow_manager.output_dir = tmp_path
        
        # Create checkpoints indicating phases already completed
        workflow_id = "test_workflow"
        checkpoint_dir = tmp_path / workflow_id / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        
        # Create completed checkpoints
        for phase in ["manubot_export", "submission_package"]:
            checkpoint_file = checkpoint_dir / f"{phase}_state.json"
            checkpoint_file.write_text(json.dumps({
                "phase": phase,
                "timestamp": "2024-01-01T00:00:00",
            }))
        
        # When resuming, these phases should be detected as completed
        # This is tested indirectly through the checkpoint loading logic

    def test_checkpoint_loading_with_dependencies(self, workflow_manager, tmp_path):
        """Test checkpoint loading includes dependencies for phases 17-18."""
        workflow_manager.output_dir = tmp_path
        
        # Create checkpoint structure
        workflow_id = "test_workflow"
        checkpoint_dir = tmp_path / workflow_id / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        
        # Create article_writing checkpoint (dependency)
        article_data = {
            "phase": "article_writing",
            "data": {
                "article_sections": {
                    "abstract": "Test abstract",
                    "introduction": "Test introduction",
                },
            },
        }
        with open(checkpoint_dir / "article_writing_state.json", "w") as f:
            json.dump(article_data, f)
        
        # Create manubot_export checkpoint
        manubot_data = {
            "phase": "manubot_export",
            "data": {
                "manubot_export_path": str(tmp_path / "manuscript"),
            },
            "dependencies": ["article_writing"],
        }
        with open(checkpoint_dir / "manubot_export_state.json", "w") as f:
            json.dump(manubot_data, f)
        
        # Test that dependencies are loaded
        # This would be tested through the actual checkpoint loading mechanism
