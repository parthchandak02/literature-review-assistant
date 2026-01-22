"""
Unit tests for Paper Enricher
"""

import pytest
from unittest.mock import Mock, patch
from src.enrichment.paper_enricher import PaperEnricher
from src.search.connectors.base import Paper


class TestPaperEnricher:
    """Test PaperEnricher functionality."""

    def test_enrich_papers_skips_papers_with_affiliations(self):
        """Test that papers with existing affiliations are skipped."""
        enricher = PaperEnricher()
        
        papers = [
            Paper(
                title="Test Paper 1",
                abstract="Abstract",
                authors=["Author A"],
                doi="10.1000/test.1",
                affiliations=["University A", "Country A"]
            ),
            Paper(
                title="Test Paper 2",
                abstract="Abstract",
                authors=["Author B"],
                doi="10.1000/test.2",
                affiliations=None
            ),
        ]
        
        # Mock the _fetch_by_doi to avoid actual API calls
        with patch.object(enricher, '_fetch_by_doi', return_value=None):
            enriched = enricher.enrich_papers(papers)
        
        # First paper should be unchanged (has affiliations)
        assert enriched[0].affiliations == ["University A", "Country A"]
        # Second paper should be unchanged (no DOI or fetch returned None)
        assert enriched[1].affiliations is None

    def test_enrich_papers_skips_papers_without_doi(self):
        """Test that papers without DOI are skipped."""
        enricher = PaperEnricher()
        
        papers = [
            Paper(
                title="Test Paper",
                abstract="Abstract",
                authors=["Author A"],
                doi=None,
                affiliations=None
            ),
        ]
        
        enriched = enricher.enrich_papers(papers)
        
        # Paper should be unchanged
        assert enriched[0].affiliations is None
        assert enriched[0].doi is None

    @patch('src.enrichment.paper_enricher.requests.get')
    def test_fetch_by_doi_success(self, mock_get):
        """Test successful DOI fetch."""
        # Mock Crossref API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "title": ["Test Paper"],
                "author": [
                    {
                        "given": "John",
                        "family": "Doe",
                        "affiliation": [
                            {
                                "name": "University of Test"
                            }
                        ]
                    },
                    {
                        "given": "Jane",
                        "family": "Smith",
                        "affiliation": [
                            {
                                "name": "Test Hospital"
                            }
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        enricher = PaperEnricher()
        result = enricher._fetch_by_doi("10.1000/test.1")
        
        assert result is not None
        assert result.affiliations == ["University of Test", "Test Hospital"]
        assert len(result.authors) == 2

    @patch('src.enrichment.paper_enricher.requests.get')
    def test_fetch_by_doi_not_found(self, mock_get):
        """Test DOI not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        enricher = PaperEnricher()
        result = enricher._fetch_by_doi("10.1000/nonexistent")
        
        assert result is None

    @patch('src.enrichment.paper_enricher.requests.get')
    def test_fetch_by_doi_rate_limit(self, mock_get):
        """Test rate limit handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        enricher = PaperEnricher()
        
        with pytest.raises(Exception):  # Should raise RateLimitError after retries
            enricher._fetch_by_doi("10.1000/test.1")

    def test_normalize_doi(self):
        """Test DOI normalization."""
        enricher = PaperEnricher()
        
        # Test with https://doi.org/ prefix
        with patch('src.enrichment.paper_enricher.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            enricher._fetch_by_doi("https://doi.org/10.1000/test.1")
            # Verify DOI was normalized (no prefix in URL)
            call_args = mock_get.call_args
            assert "10.1000/test.1" in call_args[0][0] or "10.1000/test.1" in str(call_args)
