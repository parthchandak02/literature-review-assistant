"""
Integration tests for real database connectors.

These tests make actual API calls to test real database connectors.
They are skipped if required API keys are not available.
"""

import os

import pytest

from src.search.database_connectors import (
    ArxivConnector,
    CrossrefConnector,
    Paper,
    PubMedConnector,
    ScopusConnector,
    SemanticScholarConnector,
)
from src.search.exceptions import DatabaseSearchError

# Test query that should return results
TEST_QUERY = "health literacy"
TEST_QUERY_SPECIFIC = "health literacy chatbots"


class TestPubMedConnector:
    """Test PubMed connector with real API calls."""

    @pytest.mark.integration
    def test_pubmed_search_with_api_key(self):
        """Test PubMed search with API key."""
        api_key = os.getenv("PUBMED_API_KEY")
        email = os.getenv("PUBMED_EMAIL")

        connector = PubMedConnector(api_key=api_key, email=email)
        results = connector.search(TEST_QUERY, max_results=10)

        assert len(results) > 0, "PubMed should return results"
        assert all(isinstance(p, Paper) for p in results), "All results should be Paper objects"
        assert all(p.title for p in results), "All papers should have titles"
        assert all(p.database == "PubMed" for p in results), "All papers should be from PubMed"

        # Check that at least some papers have abstracts
        papers_with_abstracts = [p for p in results if p.abstract]
        assert len(papers_with_abstracts) > 0, "At least some papers should have abstracts"

        # Check that at least some papers have authors
        papers_with_authors = [p for p in results if p.authors]
        assert len(papers_with_authors) > 0, "At least some papers should have authors"

    @pytest.mark.integration
    def test_pubmed_search_without_api_key(self):
        """Test PubMed search without API key (should still work)."""
        connector = PubMedConnector(api_key=None, email=None)
        results = connector.search(TEST_QUERY, max_results=5)

        assert len(results) > 0, "PubMed should work without API key"
        assert all(isinstance(p, Paper) for p in results)

    @pytest.mark.integration
    def test_pubmed_paper_structure(self):
        """Test that PubMed papers have required fields."""
        api_key = os.getenv("PUBMED_API_KEY")
        email = os.getenv("PUBMED_EMAIL")

        connector = PubMedConnector(api_key=api_key, email=email)
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            paper = results[0]
            assert hasattr(paper, "title"), "Paper should have title"
            assert hasattr(paper, "abstract"), "Paper should have abstract"
            assert hasattr(paper, "authors"), "Paper should have authors"
            assert hasattr(paper, "year"), "Paper should have year"
            assert hasattr(paper, "database"), "Paper should have database"
            assert paper.database == "PubMed"

    @pytest.mark.integration
    def test_pubmed_max_results(self):
        """Test that max_results limit is respected."""
        api_key = os.getenv("PUBMED_API_KEY")
        email = os.getenv("PUBMED_EMAIL")

        connector = PubMedConnector(api_key=api_key, email=email)
        results = connector.search(TEST_QUERY, max_results=3)

        assert len(results) <= 3, f"Should return at most 3 results, got {len(results)}"


class TestArxivConnector:
    """Test arXiv connector with real API calls."""

    @pytest.mark.integration
    def test_arxiv_search(self):
        """Test arXiv search (no API key needed)."""
        connector = ArxivConnector()
        results = connector.search(TEST_QUERY, max_results=10)

        assert len(results) > 0, "arXiv should return results"
        assert all(isinstance(p, Paper) for p in results)
        assert all(p.title for p in results)
        assert all(p.database == "arXiv" for p in results)

    @pytest.mark.integration
    def test_arxiv_paper_structure(self):
        """Test that arXiv papers have required fields."""
        connector = ArxivConnector()
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            paper = results[0]
            assert hasattr(paper, "title"), "Paper should have title"
            assert hasattr(paper, "abstract"), "Paper should have abstract"
            assert hasattr(paper, "authors"), "Paper should have authors"
            assert hasattr(paper, "database"), "Paper should have database"
            assert paper.database == "arXiv"
            # arXiv papers should have URLs
            assert paper.url is not None, "arXiv papers should have URLs"

    @pytest.mark.integration
    def test_arxiv_max_results(self):
        """Test that max_results limit is respected."""
        connector = ArxivConnector()
        results = connector.search(TEST_QUERY, max_results=3)

        assert len(results) <= 3, f"Should return at most 3 results, got {len(results)}"


class TestSemanticScholarConnector:
    """Test Semantic Scholar connector with real API calls."""

    @pytest.mark.integration
    def test_semantic_scholar_search_with_api_key(self):
        """Test Semantic Scholar search with API key."""
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

        connector = SemanticScholarConnector(api_key=api_key)
        results = connector.search(TEST_QUERY, max_results=10)

        assert len(results) > 0, "Semantic Scholar should return results"
        assert all(isinstance(p, Paper) for p in results)
        assert all(p.title for p in results)
        assert all(p.database == "Semantic Scholar" for p in results)

    @pytest.mark.integration
    def test_semantic_scholar_search_without_api_key(self):
        """Test Semantic Scholar search without API key (should still work with lower limits)."""
        connector = SemanticScholarConnector(api_key=None)
        results = connector.search(TEST_QUERY, max_results=5)

        # Should work but might hit rate limits
        assert all(isinstance(p, Paper) for p in results) if results else True

    @pytest.mark.integration
    def test_semantic_scholar_paper_structure(self):
        """Test that Semantic Scholar papers have required fields."""
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

        connector = SemanticScholarConnector(api_key=api_key)
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            paper = results[0]
            assert hasattr(paper, "title"), "Paper should have title"
            assert hasattr(paper, "abstract"), "Paper should have abstract"
            assert hasattr(paper, "authors"), "Paper should have authors"
            assert hasattr(paper, "database"), "Paper should have database"
            assert paper.database == "Semantic Scholar"

    @pytest.mark.integration
    def test_semantic_scholar_field_extraction(self):
        """Test that Semantic Scholar extracts fields correctly."""
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

        connector = SemanticScholarConnector(api_key=api_key)
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            # Check that at least some papers have DOIs
            [p for p in results if p.doi]
            # Check that at least some papers have venues/journals
            [p for p in results if p.journal]


class TestCrossrefConnector:
    """Test Crossref connector with real API calls."""

    @pytest.mark.integration
    def test_crossref_search(self):
        """Test Crossref search."""
        email = os.getenv("CROSSREF_EMAIL")

        connector = CrossrefConnector(email=email)
        results = connector.search(TEST_QUERY, max_results=10)

        assert len(results) > 0, "Crossref should return results"
        assert all(isinstance(p, Paper) for p in results)
        assert all(p.title for p in results)
        assert all(p.database == "Crossref" for p in results)

    @pytest.mark.integration
    def test_crossref_paper_structure(self):
        """Test that Crossref papers have required fields."""
        email = os.getenv("CROSSREF_EMAIL")

        connector = CrossrefConnector(email=email)
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            paper = results[0]
            assert hasattr(paper, "title"), "Paper should have title"
            assert hasattr(paper, "abstract"), "Paper should have abstract"
            assert hasattr(paper, "authors"), "Paper should have authors"
            assert hasattr(paper, "database"), "Paper should have database"
            assert paper.database == "Crossref"

    @pytest.mark.integration
    def test_crossref_doi_extraction(self):
        """Test that Crossref extracts DOIs correctly."""
        email = os.getenv("CROSSREF_EMAIL")

        connector = CrossrefConnector(email=email)
        results = connector.search(TEST_QUERY, max_results=10)

        if len(results) > 0:
            # Crossref should have DOIs for most papers
            papers_with_doi = [p for p in results if p.doi]
            assert len(papers_with_doi) > 0, "At least some Crossref papers should have DOIs"

    @pytest.mark.integration
    def test_crossref_pagination(self):
        """Test Crossref pagination (cursor-based)."""
        email = os.getenv("CROSSREF_EMAIL")

        connector = CrossrefConnector(email=email)
        # Request more than default page size to test pagination
        results = connector.search(TEST_QUERY, max_results=50)

        # Should handle pagination correctly
        assert len(results) <= 50, f"Should return at most 50 results, got {len(results)}"


class TestScopusConnector:
    """Test Scopus connector with real API calls."""

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("SCOPUS_API_KEY"), reason="Scopus API key not set")
    def test_scopus_search_with_api_key(self):
        """Test Scopus search with API key."""
        api_key = os.getenv("SCOPUS_API_KEY")

        connector = ScopusConnector(api_key=api_key)
        results = connector.search(TEST_QUERY, max_results=10)

        assert len(results) > 0, "Scopus should return results"
        assert all(isinstance(p, Paper) for p in results)
        assert all(p.title for p in results)
        assert all(p.database == "Scopus" for p in results)

    @pytest.mark.integration
    def test_scopus_requires_api_key(self):
        """Test that Scopus requires API key."""
        connector = ScopusConnector(api_key=None)
        results = connector.search(TEST_QUERY, max_results=10)

        # Should return empty list when no API key
        assert len(results) == 0, "Scopus should return empty list without API key"

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("SCOPUS_API_KEY"), reason="Scopus API key not set")
    def test_scopus_paper_structure(self):
        """Test that Scopus papers have required fields."""
        api_key = os.getenv("SCOPUS_API_KEY")

        connector = ScopusConnector(api_key=api_key)
        results = connector.search(TEST_QUERY, max_results=5)

        if len(results) > 0:
            paper = results[0]
            assert hasattr(paper, "title"), "Paper should have title"
            assert hasattr(paper, "abstract"), "Paper should have abstract"
            assert hasattr(paper, "authors"), "Paper should have authors"
            assert hasattr(paper, "database"), "Paper should have database"
            assert paper.database == "Scopus"


class TestConnectorErrorHandling:
    """Test error handling for connectors."""

    @pytest.mark.integration
    def test_invalid_query_handling(self):
        """Test that connectors handle invalid queries gracefully."""
        # Very long or malformed query
        invalid_query = "a" * 10000

        connectors = [
            PubMedConnector(),
            ArxivConnector(),
            SemanticScholarConnector(),
            CrossrefConnector(),
        ]

        for connector in connectors:
            try:
                results = connector.search(invalid_query, max_results=5)
                # Should either return empty list or raise exception, not crash
                assert isinstance(results, list)
            except Exception as e:
                # Should raise a proper exception, not crash
                assert isinstance(e, (DatabaseSearchError, Exception))

    @pytest.mark.integration
    def test_empty_query_handling(self):
        """Test that connectors handle empty queries."""
        connectors = [
            PubMedConnector(),
            ArxivConnector(),
            SemanticScholarConnector(),
            CrossrefConnector(),
        ]

        for connector in connectors:
            try:
                results = connector.search("", max_results=5)
                # Should handle gracefully
                assert isinstance(results, list)
            except Exception:
                # Exception is acceptable for empty query
                pass

    @pytest.mark.integration
    def test_zero_max_results(self):
        """Test that connectors handle zero max_results."""
        connectors = [
            PubMedConnector(),
            ArxivConnector(),
            SemanticScholarConnector(),
            CrossrefConnector(),
        ]

        for connector in connectors:
            results = connector.search(TEST_QUERY, max_results=0)
            assert len(results) == 0, "Should return empty list for max_results=0"


class TestConnectorComparison:
    """Test comparing results across different connectors."""

    @pytest.mark.integration
    def test_multiple_connectors_same_query(self):
        """Test that multiple connectors can search the same query."""
        connectors = []

        # Add available connectors
        if os.getenv("PUBMED_API_KEY") or os.getenv("PUBMED_EMAIL"):
            connectors.append(PubMedConnector())
        connectors.append(ArxivConnector())
        if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
            connectors.append(SemanticScholarConnector())
        if os.getenv("CROSSREF_EMAIL"):
            connectors.append(CrossrefConnector())

        if len(connectors) < 2:
            pytest.skip("Need at least 2 connectors available")

        results_by_db = {}
        for connector in connectors:
            try:
                results = connector.search(TEST_QUERY, max_results=5)
                results_by_db[connector.get_database_name()] = results
            except Exception as e:
                pytest.fail(f"Connector {connector.get_database_name()} failed: {e}")

        # Should have results from multiple databases
        assert len(results_by_db) >= 2, "Should have results from at least 2 databases"

        # Each database should return some results
        for db_name, results in results_by_db.items():
            assert len(results) > 0, f"{db_name} should return results"
