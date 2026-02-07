"""
Tests for Template Manager
"""

from pathlib import Path
from unittest.mock import patch

from src.export.template_manager import TemplateManager


class TestTemplateManager:
    """Test TemplateManager."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = TemplateManager()
        assert manager is not None
        assert manager.templates_dir.exists()

    def test_manager_initialization_custom_dir(self, tmp_path):
        """Test manager initialization with custom templates directory."""
        templates_dir = tmp_path / "custom_templates"
        manager = TemplateManager(templates_dir=templates_dir)
        assert manager.templates_dir == templates_dir
        assert templates_dir.exists()

    def test_get_template_existing(self, tmp_path):
        """Test get_template for existing journal."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        # Create template file
        template_file = templates_dir / "ieee.latex"
        template_file.write_text("\\documentclass{article}")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.get_template("ieee")
        assert result == template_file

    def test_get_template_non_existent(self, tmp_path):
        """Test get_template for non-existent journal."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.get_template("nonexistent")
        assert result is None

    def test_get_template_tries_multiple_extensions(self, tmp_path):
        """Test get_template tries multiple file extensions."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        # Create .tex file instead of .latex
        template_file = templates_dir / "ieee.tex"
        template_file.write_text("\\documentclass{article}")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.get_template("ieee")
        assert result == template_file

    def test_get_template_case_insensitive(self, tmp_path):
        """Test get_template handles case-insensitive journal names."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        template_file = templates_dir / "ieee.latex"
        template_file.write_text("\\documentclass{article}")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.get_template("IEEE")
        assert result == template_file

    def test_list_available_journals(self, tmp_path):
        """Test list_available_journals."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        # Create multiple template files
        (templates_dir / "ieee.latex").write_text("\\documentclass{article}")
        (templates_dir / "nature.latex").write_text("\\documentclass{article}")
        (templates_dir / "plos.tex").write_text("\\documentclass{article}")

        manager = TemplateManager(templates_dir=templates_dir)
        journals = manager.list_available_journals()
        assert "ieee" in journals
        assert "nature" in journals
        assert "plos" in journals
        assert len(journals) == 3

    def test_list_available_journals_empty(self, tmp_path):
        """Test list_available_journals with no templates."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        manager = TemplateManager(templates_dir=templates_dir)
        journals = manager.list_available_journals()
        assert journals == []

    def test_validate_template_valid(self, tmp_path):
        """Test validate_template with valid template."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        template_file = templates_dir / "ieee.latex"
        template_file.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.validate_template(template_file)
        assert result is True

    def test_validate_template_missing(self, tmp_path):
        """Test validate_template with missing file."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        template_file = templates_dir / "nonexistent.latex"

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.validate_template(template_file)
        assert result is False

    def test_validate_template_empty(self, tmp_path):
        """Test validate_template with empty file."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        template_file = templates_dir / "empty.latex"
        template_file.write_text("")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.validate_template(template_file)
        assert result is False

    def test_validate_template_not_file(self, tmp_path):
        """Test validate_template with path that is not a file."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.validate_template(templates_dir)
        assert result is False

    def test_validate_template_unreadable(self, tmp_path):
        """Test validate_template with unreadable file."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        template_file = templates_dir / "ieee.latex"
        template_file.write_text("\\documentclass{article}")

        manager = TemplateManager(templates_dir=templates_dir)

        # Mock read_text to raise exception
        with patch.object(Path, "read_text") as mock_read:
            mock_read.side_effect = PermissionError("Permission denied")
            result = manager.validate_template(template_file)
            assert result is False

    def test_create_custom_template(self, tmp_path):
        """Test create_custom_template."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        manager = TemplateManager(templates_dir=templates_dir)
        template_content = "\\documentclass{article}\n\\begin{document}\n\\end{document}"

        result = manager.create_custom_template("custom", template_content)
        assert result.exists()
        assert result == templates_dir / "custom.latex"
        assert result.read_text() == template_content

    def test_create_custom_template_overwrites(self, tmp_path):
        """Test create_custom_template overwrites existing template."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        manager = TemplateManager(templates_dir=templates_dir)
        template_file = templates_dir / "custom.latex"
        template_file.write_text("Old content")

        new_content = "New content"
        result = manager.create_custom_template("custom", new_content)
        assert result.read_text() == new_content

    def test_template_directory_creation(self, tmp_path):
        """Test template directory creation."""
        templates_dir = tmp_path / "new_templates"

        TemplateManager(templates_dir=templates_dir)
        assert templates_dir.exists()

    def test_get_template_path_resolution(self, tmp_path):
        """Test template path resolution."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True)

        # Create template with .lua extension (Pandoc template)
        template_file = templates_dir / "ieee.lua"
        template_file.write_text("-- Pandoc template")

        manager = TemplateManager(templates_dir=templates_dir)
        result = manager.get_template("ieee")
        # Should find .lua file
        assert result == template_file
