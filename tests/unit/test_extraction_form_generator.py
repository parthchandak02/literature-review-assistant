"""
Unit tests for extraction form generator.
"""

import pytest
import json
from pathlib import Path

from src.export.extraction_form_generator import ExtractionFormGenerator


@pytest.fixture
def generator():
    """Create extraction form generator instance."""
    return ExtractionFormGenerator()


def test_markdown_form_generation(generator, tmp_path):
    """Test markdown form generation."""
    output_path = tmp_path / "extraction_form.md"
    
    result_path = generator.generate_form(str(output_path), format="markdown")
    
    assert Path(result_path).exists()
    assert result_path == str(output_path)
    
    content = Path(result_path).read_text()
    
    # Check structure
    assert "# Data Extraction Form" in content
    assert "## Basic Metadata" in content
    assert "## Study Characteristics" in content
    assert "## Results" in content
    assert "## Limitations" in content
    
    # Check that fields are included (check for both underscore and space versions)
    assert "title" in content.lower()
    assert "authors" in content.lower()
    assert "study objectives" in content.lower() or "study_objectives" in content.lower()
    assert "methodology" in content.lower()


def test_json_form_generation(generator, tmp_path):
    """Test JSON form generation."""
    output_path = tmp_path / "extraction_form.json"
    
    result_path = generator.generate_form(str(output_path), format="json")
    
    assert Path(result_path).exists()
    
    with open(result_path, "r") as f:
        form_data = json.load(f)
    
    assert form_data["form_name"] == "Data Extraction Form"
    assert form_data["version"] == "1.0"
    assert "fields" in form_data
    assert isinstance(form_data["fields"], list)
    assert len(form_data["fields"]) > 0
    
    # Check field structure
    for field in form_data["fields"]:
        assert "name" in field
        assert "type" in field
        assert "description" in field
        assert "required" in field
        assert "value" in field


def test_word_form_generation(generator, tmp_path):
    """Test Word form generation."""
    output_path = tmp_path / "extraction_form.docx"
    
    result_path = generator.generate_form(str(output_path), format="word")
    
    # Should either generate Word doc or fallback to markdown
    assert Path(result_path).exists()
    
    # If python-docx is available, should be .docx
    # Otherwise, should fallback to .md
    assert result_path.endswith((".docx", ".md"))


def test_word_form_fallback(generator, tmp_path, monkeypatch):
    """Test Word form falls back to markdown if python-docx unavailable."""
    # Mock ImportError for docx
    original_import = __import__
    
    def mock_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("No module named 'docx'")
        return original_import(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    
    output_path = tmp_path / "extraction_form.docx"
    result_path = generator.generate_form(str(output_path), format="word")
    
    # Should fallback to markdown
    assert result_path.endswith(".md")


def test_field_extraction(generator):
    """Test field extraction from schema."""
    fields = generator.fields
    
    assert len(fields) > 0
    
    # Check that expected fields are present
    field_names = [f["name"] for f in fields]
    
    assert "title" in field_names
    assert "authors" in field_names
    assert "year" in field_names
    assert "study_objectives" in field_names
    assert "methodology" in field_names
    assert "outcomes" in field_names
    
    # Check field structure
    for field in fields:
        assert "name" in field
        assert "type" in field
        assert "description" in field
        assert "required" in field


def test_form_structure_completeness(generator, tmp_path):
    """Test that form includes all necessary sections."""
    output_path = tmp_path / "form.md"
    generator.generate_form(str(output_path), format="markdown")
    
    content = Path(output_path).read_text()
    
    # Check all major sections
    sections = [
        "Basic Metadata",
        "Study Characteristics",
        "Results",
        "Limitations"
    ]
    
    for section in sections:
        assert f"## {section}" in content


def test_unsupported_format(generator, tmp_path):
    """Test error for unsupported format."""
    output_path = tmp_path / "form.pdf"
    
    with pytest.raises(ValueError, match="Unsupported format"):
        generator.generate_form(str(output_path), format="pdf")


def test_form_output_directory_creation(generator, tmp_path):
    """Test that output directory is created if it doesn't exist."""
    output_path = tmp_path / "new_dir" / "form.md"
    
    result_path = generator.generate_form(str(output_path), format="markdown")
    
    assert Path(result_path).exists()
    assert output_path.parent.exists()


def test_json_form_field_values(generator, tmp_path):
    """Test that JSON form has correct field values."""
    output_path = tmp_path / "form.json"
    generator.generate_form(str(output_path), format="json")
    
    with open(output_path, "r") as f:
        form_data = json.load(f)
    
    # Check that all fields have value set to None initially
    for field in form_data["fields"]:
        assert field["value"] is None


def test_markdown_form_field_descriptions(generator, tmp_path):
    """Test that markdown form includes field descriptions."""
    output_path = tmp_path / "form.md"
    generator.generate_form(str(output_path), format="markdown")
    
    content = Path(output_path).read_text()
    
    # Check that descriptions are included
    assert "**Description:**" in content
    
    # Check that value placeholders are included
    assert "**Value:**" in content or "Value:" in content
