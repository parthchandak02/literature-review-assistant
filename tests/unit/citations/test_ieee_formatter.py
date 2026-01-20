"""Tests for IEEEFormatter."""

import pytest
from src.citations.ieee_formatter import IEEEFormatter
from src.search.database_connectors import Paper


def test_format_journal_article():
    """Test formatting of journal article."""
    paper = Paper(
        title="Test Article",
        abstract="Abstract",
        authors=["Smith, John", "Doe, Jane"],
        year=2023,
        doi="10.1000/test",
        journal="Test Journal",
    )
    citation = IEEEFormatter.format_citation(paper, 1)
    assert "[1]" in citation
    assert "Test Article" in citation
    assert "Test Journal" in citation
    assert "2023" in citation
    assert "doi:" in citation


def test_format_preprint():
    """Test formatting of preprint."""
    paper = Paper(
        title="Test Preprint",
        abstract="Abstract",
        authors=["Author A"],
        year=2024,
        doi="10.48550/arXiv.2401.00001",
        journal="arXiv preprint",
        database="arXiv",
    )
    citation = IEEEFormatter.format_citation(paper, 2)
    assert "[2]" in citation
    assert "Preprint" in citation or "arXiv" in citation


def test_format_conference():
    """Test formatting of conference paper."""
    paper = Paper(
        title="Conference Paper",
        abstract="Abstract",
        authors=["Author B"],
        year=2023,
        doi="10.1000/conference",
        journal="IEEE Conference on Testing",
    )
    citation = IEEEFormatter.format_citation(paper, 3)
    assert "[3]" in citation
    assert "Conference" in citation or "IEEE" in citation


def test_format_authors_single():
    """Test formatting of single author."""
    authors = ["Smith, John"]
    result = IEEEFormatter._format_authors(authors)
    assert "Smith" in result


def test_format_authors_two():
    """Test formatting of two authors."""
    authors = ["Smith, John", "Doe, Jane"]
    result = IEEEFormatter._format_authors(authors)
    assert "Smith" in result
    assert "Doe" in result
    assert "and" in result


def test_format_authors_many():
    """Test formatting of many authors (et al.)."""
    authors = ["Author 1", "Author 2", "Author 3", "Author 4", "Author 5", "Author 6"]
    result = IEEEFormatter._format_authors(authors)
    assert "et al." in result
    assert "Author 1" in result


def test_format_author_name():
    """Test formatting of author name."""
    # Test "Last, First" format
    result = IEEEFormatter._format_author_name("Smith, John")
    assert "Smith" in result
    
    # Test "First Last" format
    result = IEEEFormatter._format_author_name("John Smith")
    assert "Smith" in result


def test_is_preprint():
    """Test preprint detection."""
    paper1 = Paper(
        title="Test",
        abstract="",
        authors=[],
        journal="arXiv preprint",
        database="arXiv",
    )
    assert IEEEFormatter._is_preprint(paper1)
    
    paper2 = Paper(
        title="Test",
        abstract="",
        authors=[],
        journal="Regular Journal",
    )
    assert not IEEEFormatter._is_preprint(paper2)


def test_is_conference():
    """Test conference detection."""
    paper1 = Paper(
        title="Test",
        abstract="",
        authors=[],
        journal="IEEE Conference on Testing",
    )
    assert IEEEFormatter._is_conference(paper1)
    
    paper2 = Paper(
        title="Test",
        abstract="",
        authors=[],
        journal="Regular Journal",
    )
    assert not IEEEFormatter._is_conference(paper2)
