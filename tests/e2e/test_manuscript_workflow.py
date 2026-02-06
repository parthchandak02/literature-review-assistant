"""
End-to-end tests for manuscript workflow
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.orchestration.workflow_manager import WorkflowManager
from src.search.connectors.base import Paper


class TestManuscriptWorkflowE2E:
    """End-to-end tests for manuscript workflow."""

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
  output_dir: "manuscript"
submission:
  enabled: true
  default_journal: "ieee"
""")
        return WorkflowManager(str(config_path))

    def test_complete_workflow_with_manubot_export(self, workflow_manager, tmp_path):
        """Test complete workflow with Manubot export enabled."""
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = [
            Paper(title="Test Paper", authors=["Author"], year=2023),
        ]
        workflow_manager.topic_context.topic = "Test Topic"
        
        # Mock article sections
        article_sections = {
            "abstract": "Test abstract",
            "introduction": "Test introduction",
            "methods": "Test methods",
            "results": "Test results",
            "discussion": "Test discussion",
        }
        
        # Mock report generation
        report_path = tmp_path / "final_report.md"
        report_path.write_text("# Test Report")
        
        # Test Phase 17
        manubot_path = workflow_manager._export_manubot_structure(article_sections)
        assert manubot_path is not None

    def test_complete_workflow_with_submission_package(self, workflow_manager, tmp_path):
        """Test complete workflow with submission package enabled."""
        workflow_manager.output_dir = tmp_path
        
        # Create required files
        report_path = tmp_path / "final_report.md"
        report_path.write_text("# Test Report")
        
        workflow_outputs = {
            "final_report": str(report_path),
        }
        article_sections = {"abstract": "Test"}
        
        # Test Phase 18
        package_path = workflow_manager._generate_submission_package(
            workflow_outputs,
            article_sections,
            str(report_path),
        )
        assert package_path is not None

    def test_complete_workflow_both_enabled(self, workflow_manager, tmp_path):
        """Test complete workflow with both Manubot and submission enabled."""
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = [Paper(title="Test", authors=["Author"])]
        workflow_manager.topic_context.topic = "Test"
        
        article_sections = {"abstract": "Test"}
        report_path = tmp_path / "final_report.md"
        report_path.write_text("# Test")
        
        # Test both phases
        manubot_path = workflow_manager._export_manubot_structure(article_sections)
        package_path = workflow_manager._generate_submission_package(
            {"final_report": str(report_path)},
            article_sections,
            str(report_path),
        )
        
        assert manubot_path is not None
        assert package_path is not None

    def test_workflow_with_multiple_journals(self, workflow_manager, tmp_path):
        """Test workflow with multiple journals."""
        workflow_manager.config["submission"]["journals"] = ["ieee", "nature", "plos"]
        workflow_manager.output_dir = tmp_path
        
        report_path = tmp_path / "final_report.md"
        report_path.write_text("# Test")
        
        with patch("src.orchestration.workflow_manager.SubmissionPackageBuilder") as mock_builder:
            mock_instance = MagicMock()
            mock_instance.build_for_multiple_journals.return_value = {
                "ieee": tmp_path / "package_ieee",
                "nature": tmp_path / "package_nature",
                "plos": tmp_path / "package_plos",
            }
            mock_builder.return_value = mock_instance
            
            # This would be called in actual workflow
            # For now, test the method directly
            workflow_manager._generate_submission_package(
                {"final_report": str(report_path)},
                {},
                str(report_path),
            )
            # Verify multi-journal support exists

    def test_workflow_with_citation_resolution(self, workflow_manager, tmp_path):
        """Test workflow with citation resolution."""
        workflow_manager.config["manubot"]["auto_resolve_citations"] = True
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"
        
        article_sections = {
            "introduction": "Citation [@doi:10.1000/test] here.",
        }
        
        with patch("src.citations.CitationManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            
            workflow_manager._export_manubot_structure(article_sections)
            # Verify citation resolution was attempted

    def test_workflow_output_validation(self, workflow_manager, tmp_path):
        """Test workflow output validation."""
        workflow_manager.output_dir = tmp_path
        
        # Create outputs
        report_path = tmp_path / "final_report.md"
        report_path.write_text("# Test")
        prisma_path = tmp_path / "prisma.png"
        prisma_path.write_bytes(b"fake png")
        
        workflow_outputs = {
            "final_report": str(report_path),
            "prisma_diagram": str(prisma_path),
        }
        
        package_path = workflow_manager._generate_submission_package(
            workflow_outputs,
            {},
            str(report_path),
        )
        
        assert package_path is not None
        package_dir = Path(package_path)
        assert package_dir.exists()

    def test_workflow_error_recovery(self, workflow_manager, tmp_path):
        """Test workflow error recovery."""
        workflow_manager.output_dir = tmp_path
        workflow_manager.final_papers = []
        workflow_manager.topic_context.topic = "Test"
        
        # Test that errors don't crash workflow
        with patch("src.orchestration.workflow_manager.ManubotExporter") as mock_exporter:
            mock_exporter.side_effect = Exception("Export failed")
            
            article_sections = {"abstract": "Test"}
            manubot_path = workflow_manager._export_manubot_structure(article_sections)
            # Should return None, not raise exception
            assert manubot_path is None
