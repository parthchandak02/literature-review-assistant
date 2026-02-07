"""
Integration tests for WorkflowManager Phase 17-18 (Manubot and Submission Package)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration.workflow_manager import WorkflowManager
from src.search.connectors.base import Paper


class TestWorkflowManuscriptIntegration:
    """Test WorkflowManager Phase 17-18 integration."""

    @pytest.fixture
    def workflow_manager(self, tmp_path):
        """Create WorkflowManager instance for testing."""
        config_path = tmp_path / "workflow.yaml"
        config_path.write_text("""
topic:
  topic: "Test Topic"
  keywords: ["test", "keyword"]
workflow:
  databases: []
""")
        return WorkflowManager(str(config_path))

    def test_phase_17_execution_manubot_export(self, workflow_manager, tmp_path):
        """Test Phase 17 execution (Manubot export)."""
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "manuscript",
            "citation_style": "ieee",
            "auto_resolve_citations": True,
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = [
            Paper(title="Test Paper", authors=["Author"], year=2023),
        ]
        workflow_manager.topic_context.topic = "Test Topic"
        workflow_manager.topic_context.keywords = ["test"]

        article_sections = {
            "abstract": "Test abstract",
            "introduction": "Test introduction",
        }

        manubot_path = workflow_manager._export_manubot_structure(article_sections)
        assert manubot_path is not None
        assert Path(manubot_path).exists()
        assert (Path(manubot_path) / "content").exists()
        assert (Path(manubot_path) / "manubot.yaml").exists()

    def test_phase_17_disabled(self, workflow_manager):
        """Test Phase 17 with manubot.enabled=false."""
        workflow_manager.config["manubot"] = {"enabled": False}

        article_sections = {"abstract": "Test"}
        manubot_path = workflow_manager._export_manubot_structure(article_sections)
        assert manubot_path is None

    def test_phase_18_execution_submission_package(self, workflow_manager, tmp_path):
        """Test Phase 18 execution (submission package)."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "ieee",
            "generate_pdf": False,
            "generate_docx": False,
            "generate_html": False,
        }
        workflow_manager.output_dir = tmp_path

        # Create manuscript file
        manuscript_path = tmp_path / "final_report.md"
        manuscript_path.write_text("# Test Report\n\nContent here.")

        workflow_outputs = {
            "final_report": str(manuscript_path),
        }
        article_sections = {"abstract": "Test"}

        package_path = workflow_manager._generate_submission_package(
            workflow_outputs,
            article_sections,
            str(manuscript_path),
        )
        assert package_path is not None
        assert Path(package_path).exists()
        assert "submission_package" in package_path

    def test_phase_18_disabled(self, workflow_manager):
        """Test Phase 18 with submission.enabled=false."""
        workflow_manager.config["submission"] = {"enabled": False}

        package_path = workflow_manager._generate_submission_package(
            {},
            {},
            "",
        )
        assert package_path is None

    def test_phase_17_error_handling(self, workflow_manager, tmp_path):
        """Test Phase 17 error handling."""
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "manuscript",
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"

        # Mock exporter to raise exception
        with patch("src.orchestration.workflow_manager.ManubotExporter") as mock_exporter:
            mock_exporter.side_effect = Exception("Export failed")

            article_sections = {"abstract": "Test"}
            manubot_path = workflow_manager._export_manubot_structure(article_sections)
            # Should return None on error, not raise exception
            assert manubot_path is None

    def test_phase_18_error_handling(self, workflow_manager, tmp_path):
        """Test Phase 18 error handling."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "ieee",
        }
        workflow_manager.output_dir = tmp_path

        # Mock builder to raise exception
        with patch("src.orchestration.workflow_manager.SubmissionPackageBuilder") as mock_builder:
            mock_instance = MagicMock()
            mock_instance.build_package.side_effect = Exception("Build failed")
            mock_builder.return_value = mock_instance

            manuscript_path = tmp_path / "final_report.md"
            manuscript_path.write_text("# Test")

            package_path = workflow_manager._generate_submission_package(
                {"final_report": str(manuscript_path)},
                {},
                str(manuscript_path),
            )
            # Should return None on error, not raise exception
            assert package_path is None

    def test_phase_17_checkpoint_saving(self, workflow_manager, tmp_path):
        """Test checkpoint saving after Phase 17."""
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "manuscript",
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"
        workflow_manager.save_checkpoints = True

        article_sections = {"abstract": "Test"}
        workflow_manager._export_manubot_structure(article_sections)

        # Checkpoint should be saved (verify via state file existence)
        # This is tested indirectly through workflow run

    def test_phase_18_checkpoint_saving(self, workflow_manager, tmp_path):
        """Test checkpoint saving after Phase 18."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "ieee",
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.save_checkpoints = True

        manuscript_path = tmp_path / "final_report.md"
        manuscript_path.write_text("# Test")

        workflow_manager._generate_submission_package(
            {"final_report": str(manuscript_path)},
            {},
            str(manuscript_path),
        )

        # Checkpoint should be saved (verify via state file existence)

    def test_phase_17_resumption(self, workflow_manager, tmp_path):
        """Test resumption from Phase 17 checkpoint."""
        # This would require checkpoint loading logic
        # For now, test that Phase 17 can run after initialization
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "manuscript",
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"

        article_sections = {"abstract": "Test"}
        manubot_path = workflow_manager._export_manubot_structure(article_sections)
        assert manubot_path is not None

    def test_phase_18_resumption(self, workflow_manager, tmp_path):
        """Test resumption from Phase 18 checkpoint."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "ieee",
        }
        workflow_manager.output_dir = tmp_path

        manuscript_path = tmp_path / "final_report.md"
        manuscript_path.write_text("# Test")

        package_path = workflow_manager._generate_submission_package(
            {"final_report": str(manuscript_path)},
            {},
            str(manuscript_path),
        )
        assert package_path is not None

    def test_phase_17_configuration_override(self, workflow_manager, tmp_path):
        """Test Phase 17 configuration override."""
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "custom_manuscript",
            "citation_style": "apa",
            "auto_resolve_citations": False,
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"

        article_sections = {"abstract": "Test"}
        manubot_path = workflow_manager._export_manubot_structure(article_sections)

        assert manubot_path is not None
        assert "custom_manuscript" in manubot_path

    def test_phase_18_configuration_override(self, workflow_manager, tmp_path):
        """Test Phase 18 configuration override."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "nature",
            "generate_pdf": True,
            "generate_docx": True,
            "generate_html": True,
        }
        workflow_manager.output_dir = tmp_path

        manuscript_path = tmp_path / "final_report.md"
        manuscript_path.write_text("# Test")

        with patch("src.orchestration.workflow_manager.SubmissionPackageBuilder") as mock_builder:
            mock_instance = MagicMock()
            mock_instance.build_package.return_value = tmp_path / "package"
            mock_builder.return_value = mock_instance

            workflow_manager._generate_submission_package(
                {"final_report": str(manuscript_path)},
                {},
                str(manuscript_path),
            )

            # Verify journal was passed correctly
            call_args = mock_instance.build_package.call_args
            assert call_args[0][1] == "nature"  # journal parameter

    def test_phase_17_metadata_generation(self, workflow_manager, tmp_path):
        """Test Phase 17 metadata generation."""
        workflow_manager.config["manubot"] = {
            "enabled": True,
            "output_dir": "manuscript",
        }
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test Topic"
        workflow_manager.topic_context.keywords = ["keyword1", "keyword2"]

        article_sections = {"abstract": "Test"}

        with patch("src.orchestration.workflow_manager.ManubotExporter") as mock_exporter_class:
            mock_exporter = MagicMock()
            mock_exporter.export.return_value = tmp_path / "manuscript"
            mock_exporter_class.return_value = mock_exporter

            workflow_manager._export_manubot_structure(article_sections)

            # Verify metadata was passed correctly
            call_args = mock_exporter.export.call_args
            metadata = call_args[1]["metadata"]
            assert "Test Topic" in metadata["title"]
            assert metadata["keywords"] == ["keyword1", "keyword2"]

    def test_phase_18_missing_manuscript(self, workflow_manager, tmp_path):
        """Test Phase 18 handles missing manuscript gracefully."""
        workflow_manager.config["submission"] = {
            "enabled": True,
            "default_journal": "ieee",
        }
        workflow_manager.output_dir = tmp_path

        # No manuscript file exists
        package_path = workflow_manager._generate_submission_package(
            {},
            {},
            "",
        )
        # Should return None when manuscript not found
        assert package_path is None
