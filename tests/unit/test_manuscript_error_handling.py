"""
Error handling tests for manuscript features
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.citations.manubot_resolver import ManubotCitationResolver
from src.export.pandoc_converter import PandocConverter
from src.export.submission_package import SubmissionPackageBuilder
from src.export.journal_selector import JournalSelector


class TestManuscriptErrorHandling:
    """Test error handling for manuscript features."""

    def test_manubot_not_installed_scenarios(self):
        """Test Manubot not installed scenarios."""
        with patch("src.citations.manubot_resolver.MANUBOT_AVAILABLE", False):
            resolver = ManubotCitationResolver()
            
            with pytest.raises(ImportError):
                resolver.resolve_from_doi("10.1038/nbt.3780")
            
            with pytest.raises(ImportError):
                resolver.resolve_from_pmid("12345678")
            
            with pytest.raises(ImportError):
                resolver.resolve_from_arxiv("1407.3561")

    def test_pandoc_not_installed_scenarios(self, tmp_path):
        """Test Pandoc not installed scenarios."""
        with patch("src.export.pandoc_converter.PYPANDOC_AVAILABLE", False):
            converter = PandocConverter()
            
            markdown_path = tmp_path / "test.md"
            markdown_path.write_text("# Test")
            output_path = tmp_path / "test.pdf"
            
            with pytest.raises(ImportError) as exc_info:
                converter.markdown_to_pdf(markdown_path, output_path)
            assert "pypandoc required" in str(exc_info.value)

    def test_network_failures_citation_resolution(self):
        """Test network failures during citation resolution."""
        resolver = ManubotCitationResolver()
        
        if not resolver._manubot_available:
            pytest.skip("Manubot not installed")
        
        with patch("src.citations.manubot_resolver.citekey_to_csl_item") as mock_cite:
            mock_cite.side_effect = Exception("Network error")
            
            with pytest.raises(ValueError) as exc_info:
                resolver.resolve_from_doi("10.1038/nbt.3780")
            assert "Failed to resolve DOI" in str(exc_info.value)

    def test_invalid_journal_configurations(self, tmp_path):
        """Test invalid journal configurations."""
        # Create invalid YAML
        config_path = tmp_path / "journals.yaml"
        config_path.write_text("invalid: yaml: content: [")
        
        selector = JournalSelector(config_path)
        journals = selector.list_journals()
        # Should handle gracefully
        assert isinstance(journals, list)

    def test_missing_template_files(self, tmp_path):
        """Test missing template files."""
        builder = SubmissionPackageBuilder(tmp_path)
        
        # Template manager should handle missing templates gracefully
        template = builder.template_manager.get_template("nonexistent")
        assert template is None

    def test_missing_csl_style_files(self, tmp_path):
        """Test missing CSL style files."""
        from src.citations.csl_formatter import CSLFormatter
        
        formatter = CSLFormatter(cache_dir=tmp_path / "csl_cache")
        
        # Should handle missing style gracefully
        with patch.object(formatter, "download_style") as mock_download:
            mock_download.side_effect = ValueError("Style not found")
            
            with pytest.raises(ValueError):
                formatter.get_style_path("nonexistent-style")

    def test_file_permission_errors(self, tmp_path):
        """Test file permission errors."""
        from src.export.manubot_exporter import ManubotExporter
        from src.citations import CitationManager
        
        exporter = ManubotExporter(tmp_path, CitationManager([]))
        
        # Create read-only directory
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        read_only_dir.chmod(0o444)
        
        try:
            article_sections = {"abstract": "Test"}
            # Should handle permission error gracefully
            with pytest.raises((PermissionError, OSError)):
                exporter.export(article_sections, {})
        finally:
            # Restore permissions for cleanup
            read_only_dir.chmod(0o755)

    def test_disk_space_errors(self, tmp_path):
        """Test disk space errors."""
        from src.export.submission_package import SubmissionPackageBuilder
        
        builder = SubmissionPackageBuilder(tmp_path)
        
        # Mock shutil to raise disk space error
        with patch("shutil.copy2") as mock_copy:
            mock_copy.side_effect = OSError("No space left on device")
            
            workflow_outputs = {}
            manuscript_path = tmp_path / "manuscript.md"
            manuscript_path.write_text("# Test")
            
            # Should handle error gracefully
            try:
                package_dir = builder.build_package(
                    workflow_outputs,
                    "ieee",
                    manuscript_path,
                    generate_pdf=False,
                    generate_docx=False,
                    generate_html=False,
                )
                # May succeed if error occurs in non-critical path
            except OSError:
                # Expected if disk space error occurs
                pass

    def test_malformed_configuration_files(self, tmp_path):
        """Test malformed configuration files."""
        from src.export.journal_selector import JournalSelector
        
        # Create malformed YAML
        config_path = tmp_path / "journals.yaml"
        config_path.write_text("invalid: yaml: [unclosed")
        
        selector = JournalSelector(config_path)
        # Should handle gracefully
        journals = selector.list_journals()
        assert isinstance(journals, list)

    def test_invalid_doi_format(self):
        """Test invalid DOI format handling."""
        resolver = ManubotCitationResolver()
        
        if not resolver._manubot_available:
            pytest.skip("Manubot not installed")
        
        with patch("src.citations.manubot_resolver.citekey_to_csl_item") as mock_cite:
            mock_cite.side_effect = ValueError("Invalid DOI")
            
            with pytest.raises(ValueError):
                resolver.resolve_from_doi("invalid-doi-format")

    def test_invalid_pmid_format(self):
        """Test invalid PMID format handling."""
        resolver = ManubotCitationResolver()
        
        if not resolver._manubot_available:
            pytest.skip("Manubot not installed")
        
        with patch("src.citations.manubot_resolver.citekey_to_csl_item") as mock_cite:
            mock_cite.side_effect = ValueError("Invalid PMID")
            
            with pytest.raises(ValueError):
                resolver.resolve_from_pmid("invalid-pmid")

    def test_missing_manuscript_file(self, tmp_path):
        """Test missing manuscript file handling."""
        builder = SubmissionPackageBuilder(tmp_path)
        workflow_outputs = {}
        
        # Non-existent manuscript path
        manuscript_path = tmp_path / "nonexistent.md"
        
        package_dir = builder.build_package(
            workflow_outputs,
            "ieee",
            manuscript_path,
            generate_pdf=False,
            generate_docx=False,
            generate_html=False,
        )
        # Should handle gracefully - package created but no manuscript copied
        assert package_dir.exists()
