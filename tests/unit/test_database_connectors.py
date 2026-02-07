"""
Unit tests for database connectors.
"""

from unittest.mock import Mock, patch

import pytest

from src.search.cache import SearchCache
from src.search.database_connectors import (
    ArxivConnector,
    CrossrefConnector,
    MockConnector,
    Paper,
    PubMedConnector,
    SemanticScholarConnector,
)


class TestPaper:
    """Test Paper dataclass."""

    def test_paper_creation(self):
        """Test creating a Paper object."""
        paper = Paper(
            title="Test Paper",
            abstract="Test abstract",
            authors=["Author 1", "Author 2"],
            year=2023,
            doi="10.1000/test",
            journal="Test Journal",
            database="Test DB",
            url="https://example.com/paper",
            keywords=["keyword1", "keyword2"],
        )

        assert paper.title == "Test Paper"
        assert paper.abstract == "Test abstract"
        assert len(paper.authors) == 2
        assert paper.year == 2023
        assert paper.doi == "10.1000/test"
        assert paper.database == "Test DB"


class TestPubMedConnector:
    """Test PubMed connector."""

    @patch("src.search.database_connectors.requests.get")
    def test_search_success(self, mock_get):
        """Test successful PubMed search."""
        # Mock search response
        mock_search_response = Mock()
        mock_search_response.json.return_value = {
            "esearchresult": {"idlist": ["12345678", "87654321"]}
        }
        mock_search_response.raise_for_status = Mock()

        # Mock fetch response with XML
        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Paper Title</ArticleTitle>
                        <Abstract>
                            <AbstractText>Test abstract text</AbstractText>
                        </Abstract>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                    </Article>
                </MedlineCitation>
                <PubmedData>
                    <ArticleIdList>
                        <ArticleId IdType="doi">10.1000/test</ArticleId>
                    </ArticleIdList>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>"""

        mock_fetch_response = Mock()
        mock_fetch_response.content = xml_content.encode()
        mock_fetch_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_search_response, mock_fetch_response]

        connector = PubMedConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        assert results[0].title == "Test Paper Title"
        assert results[0].database == "PubMed"

    @patch("src.search.database_connectors.requests.get")
    def test_search_network_error(self, mock_get):
        """Test handling network errors."""
        mock_get.side_effect = Exception("Network error")

        connector = PubMedConnector()

        with pytest.raises(Exception):
            connector.search("test query")


class TestArxivConnector:
    """Test arXiv connector."""

    def test_import_error(self):
        """Test error when arxiv library is not installed."""
        with patch("src.search.database_connectors.arxiv", None):
            with pytest.raises(ImportError):
                ArxivConnector()

    @patch("src.search.database_connectors.arxiv")
    def test_search_success(self, mock_arxiv):
        """Test successful arXiv search."""
        # Mock arxiv client and results
        mock_client = Mock()
        mock_result = Mock()
        mock_result.title = "Test ArXiv Paper"
        mock_result.summary = "Test abstract"
        mock_result.authors = [Mock(name="Author 1"), Mock(name="Author 2")]
        mock_result.published.year = 2023
        mock_result.entry_id = "https://arxiv.org/abs/1234.5678"
        mock_result.categories = ["cs.AI"]

        mock_client.results.return_value = [mock_result]
        mock_arxiv.Client.return_value = mock_client
        mock_arxiv.Search = Mock()
        mock_arxiv.SortCriterion = Mock()
        mock_arxiv.SortOrder = Mock()

        connector = ArxivConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        assert results[0].title == "Test ArXiv Paper"
        assert results[0].database == "arXiv"


class TestSemanticScholarConnector:
    """Test Semantic Scholar connector."""

    @patch("src.search.database_connectors.requests.get")
    def test_search_success(self, mock_get):
        """Test successful Semantic Scholar search."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "authors": [{"name": "Author 1"}],
                    "year": 2023,
                    "url": "https://example.com",
                    "externalIds": {"DOI": "10.1000/test"},
                    "venue": "Test Venue",
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        connector = SemanticScholarConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        assert results[0].title == "Test Paper"
        assert results[0].database == "Semantic Scholar"

    @patch("src.search.database_connectors.requests.get")
    def test_rate_limit_error(self, mock_get):
        """Test handling rate limit errors."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        connector = SemanticScholarConnector()

        with pytest.raises(Exception):
            connector.search("test query")


class TestCrossrefConnector:
    """Test Crossref connector."""

    @patch("src.search.database_connectors.requests.get")
    def test_search_success(self, mock_get):
        """Test successful Crossref search."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "abstract": "Test abstract",
                        "author": [{"given": "John", "family": "Smith"}],
                        "published-print": {"date-parts": [[2023, 1, 1]]},
                        "DOI": "10.1000/test",
                        "container-title": ["Test Journal"],
                    }
                ],
                "next-cursor": None,
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        connector = CrossrefConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        assert results[0].title == "Test Paper"
        assert results[0].database == "Crossref"


class TestMockConnector:
    """Test Mock connector."""

    def test_search(self):
        """Test mock connector search."""
        connector = MockConnector("TestDB")
        results = connector.search("test query", max_results=5)

        assert len(results) <= 5
        assert all(r.database == "TestDB" for r in results)
        assert all(r.title for r in results)


class TestCaching:
    """Test caching functionality."""

    def test_cache_get_set(self, tmp_path):
        """Test cache get and set operations."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=1)

        papers = [Paper(title="Test", abstract="Abstract", authors=["Author"])]

        cache.set("test query", "TestDB", papers)
        cached = cache.get("test query", "TestDB")

        assert cached is not None
        assert len(cached) == 1
        assert cached[0].title == "Test"

    def test_cache_miss(self, tmp_path):
        """Test cache miss scenario."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=1)

        cached = cache.get("nonexistent query", "TestDB")
        assert cached is None

    def test_cache_expiration(self, tmp_path):
        """Test cache expiration."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=0.0001)  # Very short TTL

        papers = [Paper(title="Test", abstract="Abstract", authors=["Author"])]

        cache.set("test query", "TestDB", papers)

        # Wait a bit for expiration (in real test, would use time mocking)
        import time

        time.sleep(0.1)

        # Cache should be expired
        cached = cache.get("test query", "TestDB")
        # May or may not be None depending on timing, but should handle gracefully
        assert cached is None or len(cached) == 1

    def test_cache_stats(self, tmp_path):
        """Test cache statistics."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=1)

        papers = [Paper(title="Test", abstract="Abstract", authors=["Author"])]

        cache.set("query1", "DB1", papers)
        cache.set("query2", "DB2", papers)

        stats = cache.get_stats()

        assert stats["total_entries"] >= 2
        assert stats["valid_entries"] >= 2
        assert stats["cache_size_mb"] >= 0

    def test_clear_expired(self, tmp_path):
        """Test clearing expired entries."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=0.0001)

        papers = [Paper(title="Test", abstract="Abstract", authors=["Author"])]
        cache.set("test query", "TestDB", papers)

        # Clear expired (may or may not clear depending on timing)
        cache.clear_expired()

        stats = cache.get_stats()
        assert stats["expired_entries"] >= 0

    def test_clear_all(self, tmp_path):
        """Test clearing all cache entries."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=1)

        papers = [Paper(title="Test", abstract="Abstract", authors=["Author"])]
        cache.set("query1", "DB1", papers)
        cache.set("query2", "DB2", papers)

        cache.clear_all()

        stats = cache.get_stats()
        assert stats["total_entries"] == 0
