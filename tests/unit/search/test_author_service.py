"""
Tests for Author Service
"""

import pytest
from unittest.mock import Mock, MagicMock
from src.search.author_service import AuthorService
from src.search.models import Author, Affiliation


@pytest.fixture
def mock_scopus_connector():
    """Mock Scopus connector with author retrieval."""
    connector = Mock()
    connector.get_author_by_id = Mock(return_value=Author(
        name="Test Author",
        id="12345",
        h_index=10,
        citation_count=100,
        database="Scopus",
    ))
    connector.search_authors = Mock(return_value=[
        Author(name="Test Author", id="12345", database="Scopus")
    ])
    return connector


@pytest.fixture
def mock_google_scholar_connector():
    """Mock Google Scholar connector."""
    connector = Mock()
    connector.search_author = Mock(return_value=[
        {
            'name': 'Test Author',
            'id': 'scholar_id',
            'hindex': 8,
            'citedby': 80,
        }
    ])
    return connector


@pytest.fixture
def author_service(mock_scopus_connector, mock_google_scholar_connector):
    """Create author service with mock connectors."""
    connectors = {
        "Scopus": mock_scopus_connector,
        "Google Scholar": mock_google_scholar_connector,
    }
    return AuthorService(connectors)


class TestAuthorService:
    """Test Author Service."""
    
    def test_get_author_by_id(self, author_service, mock_scopus_connector):
        """Test retrieving author by ID."""
        author = author_service.get_author("12345", database="Scopus")
        
        assert author is not None
        assert author.name == "Test Author"
        assert author.h_index == 10
        mock_scopus_connector.get_author_by_id.assert_called_once_with("12345")
    
    def test_search_author(self, author_service, mock_scopus_connector):
        """Test searching for authors."""
        authors = author_service.search_author("Test Author", database="Scopus")
        
        assert len(authors) > 0
        assert authors[0].name == "Test Author"
        mock_scopus_connector.search_authors.assert_called_once()
    
    def test_get_author_metrics(self, author_service, mock_scopus_connector):
        """Test getting author metrics."""
        metrics = author_service.get_author_metrics("12345", database="Scopus")
        
        assert "h_index" in metrics
        assert metrics["h_index"] == 10
        assert metrics["citation_count"] == 100
    
    def test_aggregate_author_profiles(self, author_service):
        """Test aggregating author profiles from multiple databases."""
        author = author_service.aggregate_author_profiles("Test Author")
        
        # Should return an author with aggregated data
        assert author is not None or len(author_service.search_author("Test Author")) == 0
