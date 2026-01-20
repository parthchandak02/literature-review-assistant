"""
Tests for ACM Connector
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup
from src.search.database_connectors import ACMConnector
from src.search.cache import SearchCache


class TestACMConnector:
    """Test ACM connector functionality."""

    def test_init(self):
        """Test connector initialization."""
        connector = ACMConnector()
        assert connector.base_url == "https://dl.acm.org"
        assert connector.search_url == "https://dl.acm.org/action/doSearch"

    def test_get_database_name(self):
        """Test database name."""
        connector = ACMConnector()
        assert connector.get_database_name() == "ACM"

    def test_parse_search_results_empty(self):
        """Test parsing empty results."""
        connector = ACMConnector()
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        papers = connector._parse_search_results(soup)
        assert papers == []

    def test_extract_paper_from_item_minimal(self):
        """Test extracting paper with minimal data."""
        connector = ACMConnector()
        html = """
        <div class="search__item">
            <h5 class="hlFld-Title"><a href="/doi/10.1145/test">Test Paper</a></h5>
            <div class="authors">
                <a class="author-name">John Smith</a>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        item = soup.find("div", class_="search__item")
        paper = connector._extract_paper_from_item(item)
        assert paper is not None
        assert paper.title == "Test Paper"
        assert "John Smith" in paper.authors
        assert paper.database == "ACM"

    def test_extract_paper_from_item_with_abstract(self):
        """Test extracting paper with abstract."""
        connector = ACMConnector()
        html = """
        <div class="search__item">
            <h5 class="hlFld-Title">Test Paper</h5>
            <div class="abstract">This is a test abstract.</div>
            <div class="authors">
                <a class="author-name">John Smith</a>
            </div>
            <span class="year">2023</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        item = soup.find("div", class_="search__item")
        paper = connector._extract_paper_from_item(item)
        assert paper is not None
        assert paper.abstract == "This is a test abstract."
        assert paper.year == 2023

    @patch("src.search.database_connectors.requests.get")
    def test_search_with_cache(self, mock_get):
        """Test search with cache."""
        cache = SearchCache(cache_dir=":memory:")
        connector = ACMConnector(cache=cache)
        
        # Mock empty response
        mock_response = Mock()
        mock_response.content = b"<html><body></body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        papers = connector.search("test query", max_results=10)
        assert papers == []

    @patch("src.search.database_connectors.requests.get")
    def test_search_error_handling(self, mock_get):
        """Test error handling in search."""
        connector = ACMConnector()
        mock_get.side_effect = Exception("Network error")
        
        with pytest.raises(Exception):
            connector.search("test query", max_results=10)
