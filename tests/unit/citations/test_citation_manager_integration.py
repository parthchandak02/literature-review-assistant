"""
Tests for CitationManager Integration with Manubot
"""

from unittest.mock import patch

import pytest

from src.citations import CitationManager
from src.search.connectors.base import Paper


class TestCitationManagerIntegration:
    """Test CitationManager integration with Manubot resolver."""

    def test_add_citation_from_identifier_doi(self):
        """Test add_citation_from_identifier with DOI."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        # Mock the resolver
        mock_csl_item = {
            "title": "Test Paper",
            "author": [{"family": "Smith", "given": "John"}],
            "issued": {"date-parts": [[2023]]},
            "DOI": "10.1000/test",
        }

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            with patch.object(manager.manubot_resolver, "csl_to_paper") as mock_convert:
                mock_resolve.return_value = mock_csl_item
                mock_paper = Paper(
                    title="Test Paper", authors=["Smith, John"], year=2023, doi="10.1000/test"
                )
                mock_convert.return_value = mock_paper

                citation_number = manager.add_citation_from_identifier("doi:10.1000/test")
                assert citation_number == 1
                assert len(manager.papers) == 1
                assert manager.citation_map[1] == 0

    def test_add_citation_from_identifier_pmid(self):
        """Test add_citation_from_identifier with PMID."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        mock_csl_item = {
            "title": "Test Paper",
            "author": [{"family": "Doe", "given": "Jane"}],
            "issued": {"date-parts": [[2022]]},
        }

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            with patch.object(manager.manubot_resolver, "csl_to_paper") as mock_convert:
                mock_resolve.return_value = mock_csl_item
                mock_paper = Paper(title="Test Paper", authors=["Doe, Jane"], year=2022)
                mock_convert.return_value = mock_paper

                citation_number = manager.add_citation_from_identifier("pmid:12345678")
                assert citation_number == 1
                assert len(manager.papers) == 1

    def test_add_citation_from_identifier_arxiv(self):
        """Test add_citation_from_identifier with arXiv ID."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        mock_csl_item = {
            "title": "Test Paper",
            "author": [{"family": "Author", "given": "Test"}],
        }

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            with patch.object(manager.manubot_resolver, "csl_to_paper") as mock_convert:
                mock_resolve.return_value = mock_csl_item
                mock_paper = Paper(title="Test Paper", authors=["Author, Test"])
                mock_convert.return_value = mock_paper

                citation_number = manager.add_citation_from_identifier("arxiv:1407.3561")
                assert citation_number == 1
                assert len(manager.papers) == 1

    def test_add_citation_from_identifier_error_handling(self):
        """Test add_citation_from_identifier error handling."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            mock_resolve.side_effect = ValueError("Invalid identifier")

            with pytest.raises(ValueError):
                manager.add_citation_from_identifier("invalid-identifier")

    def test_add_citation_from_identifier_no_resolver(self):
        """Test add_citation_from_identifier without Manubot resolver."""
        manager = CitationManager([])
        manager.manubot_resolver = None

        with pytest.raises(ImportError) as exc_info:
            manager.add_citation_from_identifier("doi:10.1000/test")
        assert "Manubot resolver not available" in str(exc_info.value)

    def test_extract_and_map_citations_auto_resolve_enabled(self):
        """Test extract_and_map_citations with auto_resolve enabled."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        with patch.object(manager, "add_citation_from_identifier") as mock_add:
            mock_add.return_value = 1

            text = "This is a citation [@doi:10.1000/test]."
            result = manager.extract_and_map_citations(text, auto_resolve=True)

            assert "[1]" in result
            mock_add.assert_called_once_with("doi:10.1000/test")

    def test_extract_and_map_citations_manubot_citations(self):
        """Test extract_and_map_citations with Manubot citations."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        with patch.object(manager, "add_citation_from_identifier") as mock_add:
            mock_add.return_value = 2

            text = "First citation [@pmid:12345678] and second [@arxiv:1407.3561]."
            result = manager.extract_and_map_citations(text, auto_resolve=True)

            assert "[2]" in result
            assert mock_add.call_count == 2

    def test_extract_and_map_citations_without_manubot_resolver(self):
        """Test extract_and_map_citations without Manubot resolver."""
        manager = CitationManager([])
        manager.manubot_resolver = None

        text = "This has a citation [@doi:10.1000/test]."
        result = manager.extract_and_map_citations(text, auto_resolve=True)

        # Should not resolve Manubot citations, but should handle other citations
        assert "[@doi:10.1000/test]" in result or result == text

    def test_extract_and_map_citations_auto_resolve_disabled(self):
        """Test extract_and_map_citations with auto_resolve disabled."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        text = "This has a citation [@doi:10.1000/test]."
        result = manager.extract_and_map_citations(text, auto_resolve=False)

        # Should not resolve Manubot citations when auto_resolve is False
        assert "[@doi:10.1000/test]" in result

    def test_citation_numbering_consistency(self):
        """Test citation numbering consistency."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        mock_paper1 = Paper(title="Paper 1", authors=["Author 1"])
        mock_paper2 = Paper(title="Paper 2", authors=["Author 2"])

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            with patch.object(manager.manubot_resolver, "csl_to_paper") as mock_convert:
                mock_resolve.side_effect = [
                    {"title": "Paper 1"},
                    {"title": "Paper 2"},
                ]
                mock_convert.side_effect = [mock_paper1, mock_paper2]

                # Add first citation
                cit1 = manager.add_citation_from_identifier("doi:10.1000/test1")
                assert cit1 == 1

                # Add second citation
                cit2 = manager.add_citation_from_identifier("doi:10.1000/test2")
                assert cit2 == 2

                # Verify numbering is consistent
                assert len(manager.papers) == 2
                assert manager.citation_map[1] == 0
                assert manager.citation_map[2] == 1

    def test_extract_and_map_citations_resolution_failure(self):
        """Test extract_and_map_citations handles resolution failures gracefully."""
        manager = CitationManager([])

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        with patch.object(manager, "add_citation_from_identifier") as mock_add:
            mock_add.side_effect = ValueError("Resolution failed")

            text = "This has a citation [@doi:10.1000/invalid]."
            result = manager.extract_and_map_citations(text, auto_resolve=True)

            # Should keep original citation if resolution fails
            assert "[@doi:10.1000/invalid]" in result

    def test_extract_and_map_citations_mixed_formats(self):
        """Test extract_and_map_citations with mixed citation formats."""
        manager = CitationManager(
            [
                Paper(title="Existing Paper", authors=["Author"]),
            ]
        )

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        with patch.object(manager, "add_citation_from_identifier") as mock_add:
            mock_add.return_value = 2

            text = "Existing citation [1] and new Manubot citation [@doi:10.1000/test]."
            result = manager.extract_and_map_citations(text, auto_resolve=True)

            # Should handle both formats
            assert "[1]" in result
            assert "[2]" in result
            assert "[@doi:10.1000/test]" not in result

    def test_add_citation_from_identifier_updates_citation_map(self):
        """Test add_citation_from_identifier updates citation map correctly."""
        manager = CitationManager(
            [
                Paper(title="Existing Paper", authors=["Author"]),
            ]
        )

        if not manager.manubot_resolver:
            pytest.skip("Manubot resolver not available")

        mock_paper = Paper(title="New Paper", authors=["New Author"])

        with patch.object(manager.manubot_resolver, "resolve_from_identifier") as mock_resolve:
            with patch.object(manager.manubot_resolver, "csl_to_paper") as mock_convert:
                mock_resolve.return_value = {"title": "New Paper"}
                mock_convert.return_value = mock_paper

                citation_number = manager.add_citation_from_identifier("doi:10.1000/new")

                # Should assign citation number 2 (since we already have 1 paper)
                assert citation_number == 2
                assert manager.citation_map[2] == 1
                assert 2 in manager.used_citations
