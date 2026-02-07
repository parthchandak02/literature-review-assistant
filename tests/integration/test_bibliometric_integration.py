"""
Integration tests for bibliometric features.

Tests the integration of bibliometric components with the workflow.
"""

import pytest

from src.search.author_service import AuthorService
from src.search.bibliometric_enricher import BibliometricEnricher
from src.search.citation_network import CitationNetworkBuilder
from src.search.connectors.base import Paper
from src.search.database_connectors import ScopusConnector

try:
    from src.search.connectors.google_scholar_connector import GoogleScholarConnector

    GOOGLE_SCHOLAR_AVAILABLE = True
except ImportError:
    GOOGLE_SCHOLAR_AVAILABLE = False
    GoogleScholarConnector = None


class TestBibliometricIntegration:
    """Integration tests for bibliometric features."""

    def test_components_can_be_instantiated(self):
        """Test that all bibliometric components can be instantiated."""
        # Test Scopus connector with enhanced features
        scopus = ScopusConnector(api_key="test_key")
        assert hasattr(scopus, "get_author_by_id")
        assert hasattr(scopus, "get_affiliation_by_id")
        assert hasattr(scopus, "search_authors")

        # Test Author Service
        connectors = {"Scopus": scopus}
        author_service = AuthorService(connectors)
        assert author_service is not None

        # Test Citation Network Builder
        network_builder = CitationNetworkBuilder()
        assert network_builder is not None

        # Test Bibliometric Enricher
        enricher = BibliometricEnricher(
            author_service=author_service, citation_network_builder=network_builder, enabled=True
        )
        assert enricher is not None

    def test_google_scholar_connector_creation(self):
        """Test Google Scholar connector can be created."""
        if not GOOGLE_SCHOLAR_AVAILABLE:
            pytest.skip("scholarly library not available")

        try:
            gs = GoogleScholarConnector(use_proxy=False)
            assert gs.get_database_name() == "Google Scholar"
        except ImportError as e:
            pytest.skip(f"scholarly not properly installed: {e}")

    def test_paper_with_bibliometric_fields(self):
        """Test that Paper objects support bibliometric fields."""
        paper = Paper(
            title="Test Paper",
            abstract="Test abstract",
            authors=["Author 1", "Author 2"],
            citation_count=10,
            eid="2-s2.0-123456789",
            subject_areas=["Computer Science", "Machine Learning"],
            scopus_id="2-s2.0-123456789",
        )

        assert paper.citation_count == 10
        assert paper.eid == "2-s2.0-123456789"
        assert paper.subject_areas == ["Computer Science", "Machine Learning"]
        assert paper.scopus_id == "2-s2.0-123456789"

    def test_author_service_with_multiple_connectors(self):
        """Test Author Service works with multiple connectors."""
        scopus = ScopusConnector(api_key="test_key")
        connectors = {"Scopus": scopus}

        if GOOGLE_SCHOLAR_AVAILABLE:
            try:
                gs = GoogleScholarConnector(use_proxy=False)
                connectors["Google Scholar"] = gs
            except ImportError:
                pass

        author_service = AuthorService(connectors)
        assert len(author_service.connectors) >= 1

    def test_citation_network_with_papers(self):
        """Test citation network can be built from papers."""
        papers = [
            Paper(
                title="Paper 1",
                abstract="Abstract 1",
                authors=["Author 1"],
                doi="10.1000/paper1",
                citation_count=10,
            ),
            Paper(
                title="Paper 2",
                abstract="Abstract 2",
                authors=["Author 2"],
                doi="10.1000/paper2",
                citation_count=5,
            ),
        ]

        network_builder = CitationNetworkBuilder()
        network_data = network_builder.build_network_from_papers(papers)

        assert "nodes" in network_data
        assert "edges" in network_data
        assert "statistics" in network_data
        assert network_data["statistics"]["total_papers"] == 2

    def test_bibliometric_enricher_enrichment(self):
        """Test bibliometric enricher can enrich papers."""
        scopus = ScopusConnector(api_key="test_key")
        connectors = {"Scopus": scopus}
        author_service = AuthorService(connectors)
        network_builder = CitationNetworkBuilder()

        enricher = BibliometricEnricher(
            author_service=author_service,
            citation_network_builder=network_builder,
            enabled=True,
            include_author_metrics=True,
        )

        papers = [
            Paper(
                title="Test Paper",
                abstract="Test",
                authors=["Test Author"],
                citation_count=5,
            )
        ]

        enriched = enricher.enrich_papers(papers)
        assert len(enriched) == 1
        assert enriched[0].citation_count == 5

    def test_scopus_enhanced_search_fields(self):
        """Test that Scopus search includes bibliometric fields."""
        scopus = ScopusConnector(api_key="test_key")

        # Verify the connector has enhanced methods
        assert hasattr(scopus, "get_author_by_id")
        assert hasattr(scopus, "get_affiliation_by_id")
        assert hasattr(scopus, "search_authors")

        # Note: Actual search would require real API key and network access
        # This test just verifies the methods exist

    def test_graceful_degradation_without_dependencies(self):
        """Test that system degrades gracefully without optional dependencies."""
        # Test Scopus without pybliometrics
        scopus = ScopusConnector(api_key="test_key")

        # Author retrieval should return None without pybliometrics
        # (unless pybliometrics is actually installed)
        author = scopus.get_author_by_id("12345")
        # Should either return None or Author object, but not crash
        assert author is None or hasattr(author, "name")

    def test_configuration_respect(self):
        """Test that bibliometric features respect configuration."""
        enricher_disabled = BibliometricEnricher(enabled=False)
        papers = [Paper(title="Test", abstract="Test", authors=["Author"])]
        enriched = enricher_disabled.enrich_papers(papers)

        # Should return papers unchanged when disabled
        assert len(enriched) == 1
        assert enriched[0].title == "Test"

    def test_network_statistics_calculation(self):
        """Test citation network statistics are calculated correctly."""
        papers = [
            Paper(
                title="Paper 1",
                abstract="Abstract 1",
                authors=["Author 1"],
                citation_count=10,
            ),
            Paper(
                title="Paper 2",
                abstract="Abstract 2",
                authors=["Author 2"],
                citation_count=5,
            ),
        ]

        network_builder = CitationNetworkBuilder()
        network_builder.build_network_from_papers(papers)
        stats = network_builder.get_citation_statistics()

        assert "total_papers" in stats
        assert "total_citations" in stats
        assert stats["total_papers"] == 2
        assert stats["total_citations"] == 15  # 10 + 5
        assert stats["average_citations"] == 7.5  # 15 / 2
