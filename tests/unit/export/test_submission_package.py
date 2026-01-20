"""
Tests for Submission Package Builder
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.export.submission_package import SubmissionPackageBuilder


class TestSubmissionPackageBuilder:
    """Test SubmissionPackageBuilder."""

    def test_builder_initialization(self, tmp_path):
        """Test builder initialization."""
        builder = SubmissionPackageBuilder(tmp_path)
        assert builder.output_dir == tmp_path
        assert builder.pandoc_converter is not None
        assert builder.template_manager is not None
        assert builder.checklist_generator is not None

    def test_build_package_creates_directory(self, tmp_path):
        """Test build_package creates package directory."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        assert package_dir.exists()
        assert package_dir.name == "submission_package_ieee"

    def test_build_package_copies_manuscript(self, tmp_path):
        """Test build_package copies manuscript."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test Manuscript")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        copied_manuscript = package_dir / "manuscript.md"
        assert copied_manuscript.exists()
        assert copied_manuscript.read_text() == "# Test Manuscript"

    def test_build_package_generates_pdf(self, tmp_path):
        """Test build_package generates PDF when enabled."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        with patch.object(builder.pandoc_converter, "markdown_to_pdf") as mock_pdf:
            mock_pdf.return_value = tmp_path / "manuscript.pdf"
            package_dir = builder.build_package(
                workflow_outputs,
                "ieee",
                manuscript_path,
                generate_pdf=True,
                generate_docx=False,
                generate_html=False,
            )
            mock_pdf.assert_called_once()

    def test_build_package_generates_docx(self, tmp_path):
        """Test build_package generates DOCX when enabled."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        with patch.object(builder.pandoc_converter, "markdown_to_docx") as mock_docx:
            mock_docx.return_value = tmp_path / "manuscript.docx"
            package_dir = builder.build_package(
                workflow_outputs,
                "ieee",
                manuscript_path,
                generate_pdf=False,
                generate_docx=True,
                generate_html=False,
            )
            mock_docx.assert_called_once()

    def test_build_package_generates_html(self, tmp_path):
        """Test build_package generates HTML when enabled."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        with patch.object(builder.pandoc_converter, "markdown_to_html") as mock_html:
            mock_html.return_value = tmp_path / "manuscript.html"
            package_dir = builder.build_package(
                workflow_outputs,
                "ieee",
                manuscript_path,
                generate_pdf=False,
                generate_docx=False,
                generate_html=True,
            )
            mock_html.assert_called_once()

    def test_build_package_collects_figures(self, tmp_path):
        """Test build_package figure collection."""
        builder = SubmissionPackageBuilder(tmp_path)
        prisma_diagram = tmp_path / "prisma.png"
        prisma_diagram.write_bytes(b"fake png data")
        
        workflow_outputs = {
            "prisma_diagram": str(prisma_diagram),
        }
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        figures_dir = package_dir / "figures"
        assert figures_dir.exists()
        assert len(list(figures_dir.iterdir())) > 0

    def test_build_package_collects_supplementary(self, tmp_path):
        """Test build_package supplementary materials collection."""
        builder = SubmissionPackageBuilder(tmp_path)
        search_strategies = tmp_path / "search_strategies.md"
        search_strategies.write_text("# Search Strategies")
        
        workflow_outputs = {
            "search_strategies": str(search_strategies),
        }
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
            include_supplementary=True,
        )
        
        supplementary_dir = package_dir / "supplementary"
        assert supplementary_dir.exists()
        assert (supplementary_dir / "search_strategies.md").exists()

    def test_build_package_copies_references(self, tmp_path):
        """Test build_package references copying."""
        builder = SubmissionPackageBuilder(tmp_path)
        
        # Create reference files in output_dir
        bibtex_path = tmp_path / "references.bib"
        bibtex_path.write_text("@article{test2023}")
        ris_path = tmp_path / "references.ris"
        ris_path.write_text("TY  - JOUR")
        
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        assert (package_dir / "references.bib").exists()
        assert (package_dir / "references.ris").exists()

    def test_build_package_generates_checklist(self, tmp_path):
        """Test build_package checklist generation."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        checklist_path = package_dir / "submission_checklist.md"
        assert checklist_path.exists()
        checklist_content = checklist_path.read_text()
        assert "Submission Checklist" in checklist_content
        assert "ieee" in checklist_content.lower()

    def test_build_for_multiple_journals(self, tmp_path):
        """Test build_for_multiple_journals."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        with patch.object(builder, "build_package") as mock_build:
            mock_build.return_value = tmp_path / "package"
            packages = builder.build_for_multiple_journals(
                workflow_outputs,
                ["ieee", "nature", "plos"],
                manuscript_path,
                generate_pdf=False,
                generate_docx=False,
                generate_html=False,
            )
            
            assert len(packages) == 3
            assert "ieee" in packages
            assert "nature" in packages
            assert "plos" in packages
            assert mock_build.call_count == 3

    def test_build_for_multiple_journals_with_failures(self, tmp_path):
        """Test build_for_multiple_journals with failures."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        def mock_build(*args, **kwargs):
            journal = args[1]
            if journal == "nature":
                raise Exception("Build failed")
            return tmp_path / f"package_{journal}"
        
        with patch.object(builder, "build_package", side_effect=mock_build):
            packages = builder.build_for_multiple_journals(
                workflow_outputs,
                ["ieee", "nature", "plos"],
                manuscript_path,
                generate_pdf=False,
                generate_docx=False,
                generate_html=False,
            )
            
            assert packages["ieee"] is not None
            assert packages["nature"] is None
            assert packages["plos"] is not None

    def test_build_package_without_manuscript(self, tmp_path):
        """Test build_package without manuscript path."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_markdown=None,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        assert package_dir.exists()
        assert not (package_dir / "manuscript.md").exists()

    def test_build_package_without_supplementary(self, tmp_path):
        """Test build_package without supplementary materials."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
            include_supplementary=False,
        )
        
        supplementary_dir = package_dir / "supplementary"
        assert not supplementary_dir.exists()

    def test_build_package_pdf_error_handling(self, tmp_path):
        """Test build_package handles PDF generation errors gracefully."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        with patch.object(builder.pandoc_converter, "markdown_to_pdf") as mock_pdf:
            mock_pdf.side_effect = Exception("PDF generation failed")
            # Should not raise exception, just log warning
            package_dir = builder.build_package(
                workflow_outputs,
                "ieee",
                manuscript_path,
                generate_pdf=True,
                generate_docx=False,
                generate_html=False,
            )
            assert package_dir.exists()

    def test_build_package_collects_visualizations(self, tmp_path):
        """Test build_package collects visualizations."""
        builder = SubmissionPackageBuilder(tmp_path)
        viz1 = tmp_path / "viz1.png"
        viz1.write_bytes(b"fake png")
        viz2 = tmp_path / "viz2.png"
        viz2.write_bytes(b"fake png")
        
        workflow_outputs = {
            "visualizations": {
                "chart1": str(viz1),
                "chart2": str(viz2),
            },
        }
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        figures_dir = package_dir / "figures"
        assert figures_dir.exists()
        figure_files = list(figures_dir.glob("*.png"))
        assert len(figure_files) >= 2

    def test_build_package_skips_html_visualizations(self, tmp_path):
        """Test build_package skips HTML visualizations."""
        builder = SubmissionPackageBuilder(tmp_path)
        html_viz = tmp_path / "viz.html"
        html_viz.write_text("<html>")
        
        workflow_outputs = {
            "visualizations": {
                "interactive": str(html_viz),
            },
        }
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        figures_dir = package_dir / "figures"
        if figures_dir.exists():
            html_files = list(figures_dir.glob("*.html"))
            assert len(html_files) == 0

    def test_build_package_empty_workflow_outputs(self, tmp_path):
        """Test build_package with empty workflow_outputs."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        assert package_dir.exists()
        # Should still create package structure
        assert (package_dir / "manuscript.md").exists()

    def test_build_package_missing_optional_files(self, tmp_path):
        """Test build_package with missing optional files."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {
            "prisma_diagram": str(tmp_path / "nonexistent.png"),
            "search_strategies": str(tmp_path / "nonexistent.md"),
        }
        manuscript_path = tmp_path / "manuscript.md"
        manuscript_path.write_text("# Test")
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        
        assert package_dir.exists()
        # Should handle missing files gracefully
        figures_dir = package_dir / "figures"
        if figures_dir.exists():
            assert len(list(figures_dir.iterdir())) == 0
