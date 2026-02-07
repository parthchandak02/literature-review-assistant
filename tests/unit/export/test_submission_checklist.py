"""
Tests for Submission Checklist Generator
"""

from src.export.submission_checklist import SubmissionChecklistGenerator


class TestSubmissionChecklistGenerator:
    """Test SubmissionChecklistGenerator."""

    def test_generator_initialization(self):
        """Test generator initialization."""
        generator = SubmissionChecklistGenerator()
        assert generator is not None

    def test_generate_checklist_complete_package(self, tmp_path):
        """Test generate_checklist with complete package."""
        generator = SubmissionChecklistGenerator()

        # Create complete package structure
        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "manuscript.pdf").write_text("PDF content")
        (package_dir / "manuscript.docx").write_text("DOCX content")
        (package_dir / "manuscript.html").write_text("HTML content")
        (package_dir / "references.bib").write_text("@article{test}")
        (package_dir / "figures").mkdir()
        (package_dir / "figures" / "figure1.png").write_bytes(b"fake png")
        (package_dir / "supplementary").mkdir()
        (package_dir / "manuscript.md").write_text(
            "# Abstract\n\n# Introduction\n\n# Methods\n\n# Results\n\n# Discussion\n\n# References"
        )

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Submission Checklist" in checklist
        assert "ieee" in checklist.lower()
        assert "[x]" in checklist  # Should have checked items

    def test_generate_checklist_incomplete_package(self, tmp_path):
        """Test generate_checklist with incomplete package."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        # Missing most files

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Submission Checklist" in checklist
        assert "[ ]" in checklist  # Should have unchecked items

    def test_validate_submission_all_checks_passing(self, tmp_path):
        """Test validate_submission with all checks passing."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text(
            "# Abstract\n\nAbstract content here.\n\n"
            "# Introduction\n\nIntroduction content.\n\n"
            "# Methods\n\nMethods content.\n\n"
            "# Results\n\nResults content.\n\n"
            "# Discussion\n\nDiscussion content.\n\n"
            "# References\n\nReferences here [1].\n\n"
        )
        (package_dir / "figures").mkdir()
        (package_dir / "figures" / "figure1.png").write_bytes(b"fake png")
        (package_dir / "references.bib").write_text("@article{test}")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_abstract"] is True
        assert results["has_introduction"] is True
        assert results["has_methods"] is True
        assert results["has_results"] is True
        assert results["has_discussion"] is True
        assert results["has_references"] is True
        assert results["has_figures"] is True

    def test_validate_submission_missing_sections(self, tmp_path):
        """Test validate_submission with missing sections."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text("# Introduction\n\nOnly introduction here.")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_abstract"] is False
        assert results["has_introduction"] is True
        assert results["has_methods"] is False
        assert results["has_results"] is False
        assert results["has_discussion"] is False

    def test_validate_submission_missing_files(self, tmp_path):
        """Test validate_submission with missing files."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        # No manuscript.md, no figures, no references

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_abstract"] is False
        assert results["has_figures"] is False
        assert results["has_references"] is False

    def test_validate_submission_citation_detection(self, tmp_path):
        """Test validate_submission citation detection."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text("This is a citation [1] and another [2].")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["citations_valid"] is True

    def test_validate_submission_no_citations(self, tmp_path):
        """Test validate_submission with no citations."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text("No citations here.")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["citations_valid"] is False

    def test_validate_submission_figure_detection(self, tmp_path):
        """Test validate_submission figure detection."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text("Figure 1: Test caption\n\nSome text.")
        (package_dir / "figures").mkdir()
        (package_dir / "figures" / "figure1.png").write_bytes(b"fake png")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_figures"] is True
        assert results["figure_captions"] is True

    def test_validate_submission_figures_no_captions(self, tmp_path):
        """Test validate_submission with figures but no captions."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        manuscript_md = package_dir / "manuscript.md"
        manuscript_md.write_text("Some text without figure captions.")
        (package_dir / "figures").mkdir()
        (package_dir / "figures" / "figure1.png").write_bytes(b"fake png")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_figures"] is True
        assert results["figure_captions"] is False

    def test_generate_checklist_markdown_formatting(self, tmp_path):
        """Test checklist markdown formatting."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "manuscript.md").write_text("# Abstract\n\n# Introduction")

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "#" in checklist  # Should have markdown headers
        assert "##" in checklist  # Should have subheaders
        assert "[" in checklist  # Should have checkboxes

    def test_generate_checklist_empty_package(self, tmp_path):
        """Test generate_checklist with empty package directory."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Submission Checklist" in checklist
        assert "[ ]" in checklist  # All items should be unchecked

    def test_generate_checklist_non_existent_directory(self, tmp_path):
        """Test generate_checklist with non-existent directory."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "nonexistent"

        # Should handle gracefully
        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Submission Checklist" in checklist

    def test_validate_submission_empty_directory(self, tmp_path):
        """Test validate_submission with empty directory."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_abstract"] is False
        assert results["has_figures"] is False
        assert results["has_references"] is False

    def test_validate_submission_references_from_bibtex(self, tmp_path):
        """Test validate_submission detects references from BibTeX."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "references.bib").write_text("@article{test2023}")

        results = generator.validate_submission(package_dir, "ieee")
        assert results["has_references"] is True

    def test_generate_checklist_summary(self, tmp_path):
        """Test generate_checklist includes summary."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "manuscript.md").write_text("# Abstract\n\n# Introduction")

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Summary" in checklist or "Total checks" in checklist
        assert "Passed" in checklist or "Failed" in checklist

    def test_generate_checklist_status(self, tmp_path):
        """Test generate_checklist includes status."""
        generator = SubmissionChecklistGenerator()

        package_dir = tmp_path / "package"
        package_dir.mkdir()
        # Create complete package
        (package_dir / "manuscript.pdf").write_text("PDF")
        (package_dir / "manuscript.docx").write_text("DOCX")
        (package_dir / "manuscript.md").write_text(
            "# Abstract\n\n# Introduction\n\n# Methods\n\n# Results\n\n# Discussion\n\n# References"
        )
        (package_dir / "references.bib").write_text("@article{test}")
        (package_dir / "figures").mkdir()

        checklist = generator.generate_checklist("ieee", package_dir)
        assert "Status" in checklist or "READY" in checklist or "REVIEW" in checklist
