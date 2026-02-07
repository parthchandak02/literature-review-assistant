"""
Unit tests for src/citations/citation_manager.py

Tests the CitationManager class and citation handling functionality.
"""

import pytest

from src.citations import CitationManager
from src.search.database_connectors import Paper


@pytest.fixture
def sample_papers():
    """Create sample papers for testing."""
    return [
        Paper(
            title="Test Paper 1",
            abstract="Abstract 1",
            authors=["Author A", "Author B"],
            year=2023,
            doi="10.1000/test1",
            journal="Test Journal",
        ),
        Paper(
            title="Test Paper 2",
            abstract="Abstract 2",
            authors=["Author C"],
            year=2024,
            doi="10.1000/test2",
            journal="Another Journal",
        ),
    ]


def test_citation_extraction_single(sample_papers):
    """Test extraction of single citation."""
    manager = CitationManager(sample_papers)
    text = "This is a test [Citation 1]."
    result = manager.extract_and_map_citations(text)
    assert "[1]" in result
    assert "Citation 1" not in result
    assert 1 in manager.used_citations


def test_citation_extraction_multiple(sample_papers):
    """Test extraction of multiple citations."""
    manager = CitationManager(sample_papers)
    text = "See [Citation 1, Citation 2] for details."
    result = manager.extract_and_map_citations(text)
    assert "[1, 2]" in result or "[1,2]" in result
    assert 1 in manager.used_citations
    assert 2 in manager.used_citations


def test_citation_extraction_none(sample_papers):
    """Test text with no citations."""
    manager = CitationManager(sample_papers)
    text = "This text has no citations."
    result = manager.extract_and_map_citations(text)
    assert result == text
    assert len(manager.used_citations) == 0


def test_references_section_generation(sample_papers):
    """Test References section generation."""
    manager = CitationManager(sample_papers)
    text = "See [Citation 1] and [Citation 2]."
    manager.extract_and_map_citations(text)
    references = manager.generate_references_section()

    assert "## References" in references
    assert "Test Paper 1" in references or "Author A" in references
    assert "Test Paper 2" in references or "Author C" in references


def test_citation_count(sample_papers):
    """Test citation count."""
    manager = CitationManager(sample_papers)
    text = "See [Citation 1, Citation 2, Citation 1]."  # Citation 1 appears twice
    manager.extract_and_map_citations(text)
    assert manager.get_citation_count() == 2  # Unique citations


def test_empty_papers():
    """Test with empty paper list."""
    manager = CitationManager([])
    text = "See [Citation 1]."
    result = manager.extract_and_map_citations(text)
    # Should still replace citation but won't map to any paper
    assert "[1]" in result
    references = manager.generate_references_section()
    assert "No citations found" in references


def test_generate_bibtex_references(sample_papers):
    """Test BibTeX references generation."""
    manager = CitationManager(sample_papers)
    manager.extract_and_map_citations("See [Citation 1].")
    bibtex = manager.generate_bibtex_references()
    assert "@article" in bibtex or "@inproceedings" in bibtex or "@misc" in bibtex
    assert "Test Paper 1" in bibtex


def test_export_bibtex(sample_papers, tmp_path):
    """Test BibTeX export to file."""
    manager = CitationManager(sample_papers)
    manager.extract_and_map_citations("See [Citation 1].")
    output_path = tmp_path / "test.bib"
    result_path = manager.export_bibtex(str(output_path))
    assert output_path.exists()
    assert result_path == str(output_path)
    content = output_path.read_text()
    assert "@article" in content or "@inproceedings" in content or "@misc" in content
