"""
Tests for Manubot Citation Resolver
"""

from unittest.mock import patch

import pytest

from src.citations.manubot_resolver import MANUBOT_AVAILABLE, ManubotCitationResolver
from src.search.connectors.base import Paper


class TestManubotCitationResolver:
    """Test ManubotCitationResolver."""

    def test_resolver_initialization(self):
        """Test resolver initialization."""
        resolver = ManubotCitationResolver()
        assert resolver is not None
        assert hasattr(resolver, "_manubot_available")

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_resolve_from_doi(self):
        """Test DOI resolution."""
        resolver = ManubotCitationResolver()
        # Use a known DOI
        csl_item = resolver.resolve_from_doi("10.1038/nbt.3780")
        assert csl_item is not None
        assert "title" in csl_item or "author" in csl_item

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_resolve_from_pmid(self):
        """Test PubMed ID resolution."""
        resolver = ManubotCitationResolver()
        # Use a known PMID
        csl_item = resolver.resolve_from_pmid("29424689")
        assert csl_item is not None

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_resolve_from_arxiv_with_prefix(self):
        """Test arXiv ID resolution with arXiv: prefix."""
        resolver = ManubotCitationResolver()
        # Test with arXiv: prefix
        try:
            csl_item = resolver.resolve_from_arxiv("arXiv:1407.3561")
            assert csl_item is not None
        except (ValueError, Exception):
            # May fail if network unavailable, skip in that case
            pytest.skip("Network unavailable or arXiv ID not found")

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_resolve_from_arxiv_without_prefix(self):
        """Test arXiv ID resolution without prefix."""
        resolver = ManubotCitationResolver()
        # Test without prefix
        try:
            csl_item = resolver.resolve_from_arxiv("1407.3561")
            assert csl_item is not None
        except (ValueError, Exception):
            pytest.skip("Network unavailable or arXiv ID not found")

    def test_csl_to_paper(self):
        """Test CSL to Paper conversion."""
        resolver = ManubotCitationResolver()
        csl_item = {
            "title": "Test Paper",
            "author": [
                {"family": "Smith", "given": "John"},
                {"family": "Doe", "given": "Jane"},
            ],
            "issued": {"date-parts": [[2023]]},
            "DOI": "10.1000/test",
            "container-title": "Test Journal",
        }
        paper = resolver.csl_to_paper(csl_item)
        assert isinstance(paper, Paper)
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2
        assert paper.year == 2023
        assert paper.doi == "10.1000/test"
        assert paper.journal == "Test Journal"

    def test_csl_to_paper_missing_fields(self):
        """Test CSL to Paper conversion with missing fields."""
        resolver = ManubotCitationResolver()
        csl_item = {
            "title": "Test Paper",
            # Missing author, year, DOI, journal
        }
        paper = resolver.csl_to_paper(csl_item)
        assert isinstance(paper, Paper)
        assert paper.title == "Test Paper"
        assert paper.authors == []
        assert paper.year is None
        assert paper.doi is None
        assert paper.journal is None

    def test_csl_to_paper_author_formats(self):
        """Test CSL to Paper conversion with various author formats."""
        resolver = ManubotCitationResolver()

        # Test with family and given
        csl_item1 = {
            "title": "Paper 1",
            "author": [{"family": "Smith", "given": "John"}],
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.authors == ["Smith, John"]

        # Test with only family
        csl_item2 = {
            "title": "Paper 2",
            "author": [{"family": "Doe"}],
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.authors == ["Doe"]

        # Test with literal
        csl_item3 = {
            "title": "Paper 3",
            "author": [{"literal": "Smith, John"}],
        }
        paper3 = resolver.csl_to_paper(csl_item3)
        assert paper3.authors == ["Smith, John"]

    def test_csl_to_paper_date_variations(self):
        """Test CSL to Paper conversion with date variations."""
        resolver = ManubotCitationResolver()

        # Test with full date
        csl_item1 = {
            "title": "Paper 1",
            "issued": {"date-parts": [[2023, 6, 15]]},
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.year == 2023

        # Test with year only
        csl_item2 = {
            "title": "Paper 2",
            "issued": {"date-parts": [[2020]]},
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.year == 2020

        # Test with empty date-parts
        csl_item3 = {
            "title": "Paper 3",
            "issued": {"date-parts": [[]]},
        }
        paper3 = resolver.csl_to_paper(csl_item3)
        assert paper3.year is None

        # Test with missing issued
        csl_item4 = {
            "title": "Paper 4",
        }
        paper4 = resolver.csl_to_paper(csl_item4)
        assert paper4.year is None

    def test_csl_to_paper_journal_fallback(self):
        """Test CSL to Paper conversion with journal fallback."""
        resolver = ManubotCitationResolver()

        # Test container-title
        csl_item1 = {
            "title": "Paper 1",
            "container-title": "Journal A",
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.journal == "Journal A"

        # Test journal fallback
        csl_item2 = {
            "title": "Paper 2",
            "journal": "Journal B",
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.journal == "Journal B"

        # Test publisher fallback
        csl_item3 = {
            "title": "Paper 3",
            "publisher": "Publisher C",
        }
        paper3 = resolver.csl_to_paper(csl_item3)
        assert paper3.journal == "Publisher C"

    def test_graceful_degradation_no_manubot(self):
        """Test graceful degradation when Manubot not installed."""
        with patch("src.citations.manubot_resolver.MANUBOT_AVAILABLE", False):
            resolver = ManubotCitationResolver()
            assert resolver._manubot_available is False

            # Should raise ImportError when trying to resolve
            with pytest.raises(ImportError):
                resolver.resolve_from_doi("10.1038/nbt.3780")

            with pytest.raises(ImportError):
                resolver.resolve_from_pmid("12345678")

            with pytest.raises(ImportError):
                resolver.resolve_from_arxiv("1407.3561")

            with pytest.raises(ImportError):
                resolver.resolve_from_identifier("10.1038/nbt.3780")

    def test_resolve_from_identifier_doi(self):
        """Test identifier resolution with DOI."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        # Test with DOI format
        try:
            csl_item = resolver.resolve_from_identifier("10.1038/nbt.3780")
            assert csl_item is not None
        except (ImportError, ValueError):
            pytest.skip("Manubot resolution failed")

    def test_resolve_from_identifier_doi_with_prefix(self):
        """Test identifier resolution with doi: prefix."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        try:
            csl_item = resolver.resolve_from_identifier("doi:10.1038/nbt.3780")
            assert csl_item is not None
        except (ImportError, ValueError):
            pytest.skip("Manubot resolution failed")

    def test_resolve_from_identifier_pmid(self):
        """Test identifier resolution with PMID."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        try:
            csl_item = resolver.resolve_from_identifier("29424689")
            assert csl_item is not None
        except (ImportError, ValueError):
            pytest.skip("Manubot resolution failed")

    def test_resolve_from_identifier_pmid_with_prefix(self):
        """Test identifier resolution with pmid: prefix."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        try:
            csl_item = resolver.resolve_from_identifier("pmid:29424689")
            assert csl_item is not None
        except (ImportError, ValueError):
            pytest.skip("Manubot resolution failed")

    def test_resolve_from_identifier_arxiv(self):
        """Test identifier resolution with arXiv ID."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        try:
            csl_item = resolver.resolve_from_identifier("1407.3561")
            assert csl_item is not None
        except (ImportError, ValueError):
            pytest.skip("Manubot resolution failed")

    def test_resolve_from_identifier_invalid(self):
        """Test identifier resolution with invalid identifier."""
        resolver = ManubotCitationResolver()
        if not resolver._manubot_available:
            pytest.skip("Manubot not available")

        with pytest.raises(ValueError):
            resolver.resolve_from_identifier("invalid-identifier-12345")

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_network_error_handling(self):
        """Test network error handling."""
        resolver = ManubotCitationResolver()

        # Mock citekey_to_csl_item to raise an exception
        with patch("src.citations.manubot_resolver.citekey_to_csl_item") as mock_cite:
            mock_cite.side_effect = Exception("Network error")

            with pytest.raises(ValueError) as exc_info:
                resolver.resolve_from_doi("10.1038/nbt.3780")
            assert "Failed to resolve DOI" in str(exc_info.value)

    @pytest.mark.skipif(
        not MANUBOT_AVAILABLE,
        reason="Manubot not installed",
    )
    def test_timeout_handling(self):
        """Test timeout handling for slow API responses."""
        resolver = ManubotCitationResolver()

        # Mock citekey_to_csl_item to simulate timeout
        with patch("src.citations.manubot_resolver.citekey_to_csl_item") as mock_cite:
            mock_cite.side_effect = TimeoutError("Request timed out")

            with pytest.raises(ValueError) as exc_info:
                resolver.resolve_from_doi("10.1038/nbt.3780")
            assert "Failed to resolve DOI" in str(exc_info.value)

    def test_malformed_csl_json(self):
        """Test handling of malformed CSL JSON."""
        resolver = ManubotCitationResolver()

        # Test with malformed author structure
        csl_item1 = {
            "title": "Test Paper",
            "author": "Not a list",  # Should be a list
        }
        # Should handle gracefully
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.title == "Test Paper"
        assert paper1.authors == []

        # Test with malformed date structure
        csl_item2 = {
            "title": "Test Paper",
            "issued": "Not a dict",  # Should be a dict
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.year is None

    def test_csl_to_paper_keywords(self):
        """Test CSL to Paper conversion with keywords."""
        resolver = ManubotCitationResolver()

        # Test with list keywords
        csl_item1 = {
            "title": "Paper 1",
            "keyword": ["keyword1", "keyword2", "keyword3"],
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.keywords == ["keyword1", "keyword2", "keyword3"]

        # Test with string keyword
        csl_item2 = {
            "title": "Paper 2",
            "keyword": "single keyword",
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.keywords == ["single keyword"]

    def test_csl_to_paper_doi_variations(self):
        """Test CSL to Paper conversion with DOI variations."""
        resolver = ManubotCitationResolver()

        # Test with uppercase DOI
        csl_item1 = {
            "title": "Paper 1",
            "DOI": "10.1000/test",
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.doi == "10.1000/test"

        # Test with lowercase doi
        csl_item2 = {
            "title": "Paper 2",
            "doi": "10.1000/test2",
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.doi == "10.1000/test2"

    def test_csl_to_paper_url_variations(self):
        """Test CSL to Paper conversion with URL variations."""
        resolver = ManubotCitationResolver()

        # Test with uppercase URL
        csl_item1 = {
            "title": "Paper 1",
            "URL": "https://example.com/paper1",
        }
        paper1 = resolver.csl_to_paper(csl_item1)
        assert paper1.url == "https://example.com/paper1"

        # Test with lowercase url
        csl_item2 = {
            "title": "Paper 2",
            "url": "https://example.com/paper2",
        }
        paper2 = resolver.csl_to_paper(csl_item2)
        assert paper2.url == "https://example.com/paper2"
