"""Tests for CitationRegistry."""

import pytest
from src.orchestration.citation_registry import CitationRegistry
from src.search.database_connectors import Paper


def test_citation_registry_basic():
    """Test basic citation registry functionality."""
    # Create test papers
    papers = [
        Paper(
            title="First Paper",
            abstract="Abstract 1",
            authors=["Smith, John"],
            year=2023,
            doi="10.1234/paper1",
        ),
        Paper(
            title="Second Paper",
            abstract="Abstract 2",
            authors=["Jones, Alice"],
            year=2024,
            doi="10.1234/paper2",
        ),
    ]
    
    # Create registry
    registry = CitationRegistry(papers)
    
    # Check citekeys generated
    assert "Smith2023" in registry.citekey_to_paper
    assert "Jones2024" in registry.citekey_to_paper
    
    # Test resolution
    assert registry.resolve_citekey("Smith2023") == papers[0]
    assert registry.resolve_citekey("Jones2024") == papers[1]


def test_citation_registry_disambiguation():
    """Test disambiguation for same author+year."""
    papers = [
        Paper(
            title="First Paper by Smith",
            abstract="Abstract 1",
            authors=["Smith, John"],
            year=2023,
        ),
        Paper(
            title="Second Paper by Smith",
            abstract="Abstract 2",
            authors=["Smith, Mary"],
            year=2023,
        ),
    ]
    
    registry = CitationRegistry(papers)
    
    # Check disambiguation suffixes
    assert "Smith2023a" in registry.citekey_to_paper
    assert "Smith2023b" in registry.citekey_to_paper


def test_replace_citekeys_with_numbers():
    """Test converting citekeys to numbered citations."""
    papers = [
        Paper(
            title="Paper 1",
            abstract="Abstract 1",
            authors=["Smith, John"],
            year=2023,
        ),
        Paper(
            title="Paper 2",
            abstract="Abstract 2",
            authors=["Jones, Alice"],
            year=2024,
        ),
    ]
    
    registry = CitationRegistry(papers)
    
    text = "This is a citation [Smith2023] and another [Jones2024] and repeat [Smith2023]."
    transformed, used_keys = registry.replace_citekeys_with_numbers(text)
    
    # Check transformation
    assert "[1]" in transformed
    assert "[2]" in transformed
    assert "[Smith2023]" not in transformed
    assert "[Jones2024]" not in transformed
    
    # Check used keys order
    assert used_keys == ["Smith2023", "Jones2024"]


def test_replace_multi_citekeys_with_numbers():
    """Test converting multi-citation brackets to numbered citations."""
    papers = [
        Paper(
            title="Paper 1",
            abstract="Abstract 1",
            authors=["Smith, John"],
            year=2023,
        ),
        Paper(
            title="Paper 2",
            abstract="Abstract 2",
            authors=["Jones, Alice"],
            year=2024,
        ),
    ]

    registry = CitationRegistry(papers)

    text = "Combined evidence [Smith2023, Jones2024] supports this."
    transformed, used_keys = registry.replace_citekeys_with_numbers(text)

    assert "[1, 2]" in transformed
    assert used_keys == ["Smith2023", "Jones2024"]


def test_validate_citekeys():
    """Test citekey validation."""
    papers = [
        Paper(
            title="Paper 1",
            abstract="Abstract 1",
            authors=["Smith, John"],
            year=2023,
        ),
    ]
    
    registry = CitationRegistry(papers)
    
    # Valid citekey
    valid, invalid = registry.validate_citekeys(["Smith2023"])
    assert valid == ["Smith2023"]
    assert invalid == []
    
    # Invalid citekey
    valid, invalid = registry.validate_citekeys(["Jones2024"])
    assert valid == []
    assert invalid == ["Jones2024"]
    
    # Mixed
    valid, invalid = registry.validate_citekeys(["Smith2023", "Jones2024", "Smith2023"])
    assert "Smith2023" in valid
    assert "Jones2024" in invalid


def test_references_markdown():
    """Test markdown references generation."""
    papers = [
        Paper(
            title="Test Paper",
            abstract="Abstract",
            authors=["Smith, John", "Jones, Alice"],
            year=2023,
            journal="Nature",
            doi="10.1234/test",
        ),
    ]
    
    registry = CitationRegistry(papers)
    
    refs = registry.references_markdown(["Smith2023"])
    
    assert "## References" in refs
    assert "[1]" in refs
    assert "Smith, John" in refs
    assert "Test Paper" in refs
    assert "Nature" in refs
    assert "2023" in refs
    assert "10.1234/test" in refs


def test_bibtex_export():
    """Test BibTeX export."""
    papers = [
        Paper(
            title="Test Paper",
            abstract="Abstract",
            authors=["Smith, John"],
            year=2023,
            journal="Nature",
            doi="10.1234/test",
        ),
    ]
    
    registry = CitationRegistry(papers)
    bibtex = registry.to_bibtex(["Smith2023"])
    
    assert "@article{Smith2023," in bibtex
    assert "title = {Test Paper}" in bibtex
    assert "author = {Smith, John}" in bibtex
    assert "year = {2023}" in bibtex


def test_ris_export():
    """Test RIS export."""
    papers = [
        Paper(
            title="Test Paper",
            abstract="Abstract",
            authors=["Smith, John"],
            year=2023,
            journal="Nature",
            doi="10.1234/test",
        ),
    ]
    
    registry = CitationRegistry(papers)
    ris = registry.to_ris(["Smith2023"])
    
    assert "TY  - JOUR" in ris
    assert "AU  - Smith, John" in ris
    assert "TI  - Test Paper" in ris
    assert "PY  - 2023" in ris
    assert "ER  -" in ris
