"""
Unit tests for src/deduplication.py

Tests the Deduplicator class and deduplication functionality.
"""

from src.deduplication import Deduplicator
from src.search.database_connectors import Paper


class TestDeduplicator:
    """Test Deduplicator class."""

    def test_no_duplicates(self):
        """Test deduplication with no duplicates."""
        papers = [
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"]),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"]),
            Paper(title="Paper 3", abstract="Abstract 3", authors=["Author 3"]),
        ]

        deduplicator = Deduplicator(similarity_threshold=85)
        result = deduplicator.deduplicate_papers(papers)

        assert len(result.unique_papers) == 3
        assert result.duplicates_removed == 0

    def test_exact_duplicates_by_doi(self):
        """Test deduplication of exact duplicates by DOI."""
        papers = [
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], doi="10.1000/test"),
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], doi="10.1000/test"),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"]),
        ]

        deduplicator = Deduplicator(similarity_threshold=85)
        result = deduplicator.deduplicate_papers(papers)

        assert len(result.unique_papers) == 2
        assert result.duplicates_removed == 1

    def test_similar_titles(self):
        """Test deduplication of papers with similar titles."""
        papers = [
            Paper(
                title="Machine Learning in Healthcare", abstract="Abstract 1", authors=["Author 1"]
            ),
            Paper(
                title="Machine Learning in Health Care", abstract="Abstract 1", authors=["Author 1"]
            ),
            Paper(title="Deep Learning Applications", abstract="Abstract 2", authors=["Author 2"]),
        ]

        deduplicator = Deduplicator(similarity_threshold=85)
        result = deduplicator.deduplicate_papers(papers)

        # Should identify first two as duplicates
        assert len(result.unique_papers) <= 2
        assert result.duplicates_removed >= 1

    def test_record_prioritization(self):
        """Test that best record is kept from duplicate group."""
        papers = [
            Paper(
                title="Test Paper",
                abstract="Short abstract",
                authors=["Author 1"],
                year=2020,
                database="arXiv",
            ),
            Paper(
                title="Test Paper",
                abstract="This is a much longer and more complete abstract with detailed information",
                authors=["Author 1", "Author 2"],
                year=2023,
                doi="10.1000/test",
                database="PubMed",
            ),
        ]

        deduplicator = Deduplicator(similarity_threshold=85)
        result = deduplicator.deduplicate_papers(papers)

        assert len(result.unique_papers) == 1
        # Should keep the one with DOI (PubMed record)
        assert result.unique_papers[0].doi == "10.1000/test"
        assert result.unique_papers[0].database == "PubMed"

    def test_empty_list(self):
        """Test deduplication with empty list."""
        deduplicator = Deduplicator()
        result = deduplicator.deduplicate_papers([])

        assert len(result.unique_papers) == 0
        assert result.duplicates_removed == 0

    def test_single_paper(self):
        """Test deduplication with single paper."""
        papers = [Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"])]

        deduplicator = Deduplicator()
        result = deduplicator.deduplicate_papers(papers)

        assert len(result.unique_papers) == 1
        assert result.duplicates_removed == 0
