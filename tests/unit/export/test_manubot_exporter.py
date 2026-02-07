"""
Tests for Manubot Exporter
"""

from src.citations import CitationManager
from src.export.manubot_exporter import ManubotExporter


class TestManubotExporter:
    """Test ManubotExporter."""

    def test_exporter_initialization(self, tmp_path):
        """Test exporter initialization."""
        exporter = ManubotExporter(tmp_path)
        assert exporter.output_dir == tmp_path
        assert exporter.content_dir == tmp_path / "content"

    def test_export_structure(self, tmp_path):
        """Test export creates correct structure."""
        exporter = ManubotExporter(tmp_path)
        citation_manager = CitationManager([])
        exporter.citation_manager = citation_manager

        article_sections = {
            "abstract": "Test abstract",
            "introduction": "Test introduction",
            "methods": "Test methods",
            "results": "Test results",
            "discussion": "Test discussion",
        }

        metadata = {
            "title": "Test Review",
            "authors": ["Author 1"],
            "keywords": ["test", "review"],
        }

        result_path = exporter.export(article_sections, metadata)

        assert result_path.exists()
        assert (result_path / "content").exists()
        assert (result_path / "manubot.yaml").exists()
        assert (result_path / "content" / "01.abstract.md").exists()
        assert (result_path / "content" / "02.introduction.md").exists()

    def test_front_matter_generation(self, tmp_path):
        """Test front matter generation."""
        exporter = ManubotExporter(tmp_path)
        metadata = {
            "title": "Test Title",
            "authors": ["Author 1", "Author 2"],
            "keywords": ["keyword1", "keyword2"],
        }
        front_matter = exporter._generate_front_matter(metadata)
        assert "title: Test Title" in front_matter
        assert "keyword1" in front_matter or "keyword2" in front_matter

    def test_section_formatting(self, tmp_path):
        """Test section formatting."""
        exporter = ManubotExporter(tmp_path)
        content = exporter._format_section("introduction", "Test content")
        assert "title: Introduction" in content
        assert "Test content" in content
