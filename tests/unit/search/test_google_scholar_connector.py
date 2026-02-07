"""
Tests for Google Scholar Connector
"""

from unittest.mock import MagicMock, patch

import pytest

from src.search.connectors.base import Paper
from src.search.connectors.google_scholar_connector import GoogleScholarConnector


@pytest.fixture
def mock_scholarly():
    """Mock scholarly library."""
    import sys

    mock_scholarly_module = MagicMock()
    mock_scholarly_module.search_pubs.return_value = [
        {
            "filled": True,
            "bib": {
                "title": "Test Paper",
                "abstract": "Test abstract",
                "author": ["Author 1", "Author 2"],
                "pub_year": "2023",
                "venue": "Test Journal",
                "doi": "10.1000/test",
            },
            "cites": "10",
            "pub_url": "https://example.com/paper",
        }
    ]
    mock_scholarly_module.fill.return_value = {
        "filled": True,
        "bib": {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "author": ["Author 1", "Author 2"],
            "pub_year": "2023",
            "venue": "Test Journal",
        },
        "cites": "10",
    }
    mock_scholarly_module.search_author.return_value = [
        {
            "name": "Test Author",
            "id": "test_id",
            "affiliation": "Test University",
            "hindex": 10,
            "citedby": 100,
        }
    ]

    with patch.dict(sys.modules, {"scholarly": mock_scholarly_module}):
        yield mock_scholarly_module


@pytest.fixture
def connector(mock_scholarly):
    """Create Google Scholar connector."""
    with patch("src.search.connectors.google_scholar_connector.SCHOLARLY_AVAILABLE", True):
        return GoogleScholarConnector(use_proxy=False)


class TestGoogleScholarConnector:
    """Test Google Scholar connector."""

    def test_init_without_scholarly(self):
        """Test initialization without scholarly library."""
        with patch("src.search.connectors.google_scholar_connector.SCHOLARLY_AVAILABLE", False):
            with pytest.raises(ImportError):
                GoogleScholarConnector()

    def test_search(self, connector, mock_scholarly):
        """Test search functionality."""
        papers = connector.search("test query", max_results=10)

        assert len(papers) > 0
        assert isinstance(papers[0], Paper)
        assert papers[0].title == "Test Paper"
        assert papers[0].database == "Google Scholar"

    def test_search_author(self, connector, mock_scholarly):
        """Test author search."""
        mock_scholarly.search_author.return_value = [
            {
                "name": "Test Author",
                "id": "test_id",
                "affiliation": "Test University",
                "hindex": 10,
                "citedby": 100,
            }
        ]

        authors = connector.search_author("Test Author", max_results=5)

        assert len(authors) > 0
        assert authors[0]["name"] == "Test Author"

    def test_get_cited_by_not_implemented(self, connector):
        """Test that cited_by returns empty list (not fully implemented)."""
        paper = Paper(
            title="Test",
            abstract="Test",
            authors=["Author"],
        )

        citing_papers = connector.get_cited_by(paper)
        assert citing_papers == []

    def test_get_related_articles_not_implemented(self, connector):
        """Test that related articles returns empty list (not fully implemented)."""
        paper = Paper(
            title="Test",
            abstract="Test",
            authors=["Author"],
        )

        related = connector.get_related_articles(paper)
        assert related == []

    def test_get_database_name(self, connector):
        """Test database name."""
        assert connector.get_database_name() == "Google Scholar"
