"""
Unit tests for affiliation extraction in database connectors.
"""

import pytest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from src.search.database_connectors import (
    Paper,
    PubMedConnector,
    CrossrefConnector,
    ScopusConnector,
    SemanticScholarConnector,
)


class TestPubMedAffiliationExtraction:
    """Test PubMed affiliation extraction."""

    @patch("src.search.database_connectors.requests.get")
    def test_pubmed_affiliation_extraction(self, mock_get):
        """Test that affiliations are extracted from PubMed XML."""
        # Mock search response
        mock_search_response = Mock()
        mock_search_response.json.return_value = {
            "esearchresult": {"idlist": ["12345678"]}
        }
        mock_search_response.raise_for_status = Mock()

        # Mock fetch response with XML containing affiliations
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
                                <Affiliation>Department of Health, University of California, San Francisco, CA, USA</Affiliation>
                            </Author>
                            <Author>
                                <LastName>Doe</LastName>
                                <ForeName>Jane</ForeName>
                                <Affiliation>School of Medicine, Harvard University, Boston, MA, USA</Affiliation>
                            </Author>
                        </AuthorList>
                    </Article>
                    <Journal>
                        <Title>Test Journal</Title>
                    </Journal>
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
        paper = results[0]
        assert paper.affiliations is not None
        assert len(paper.affiliations) == 2
        assert "University of California" in paper.affiliations[0]
        assert "Harvard University" in paper.affiliations[1]

    @patch("src.search.database_connectors.requests.get")
    def test_pubmed_no_affiliations(self, mock_get):
        """Test PubMed paper with no affiliations."""
        mock_search_response = Mock()
        mock_search_response.json.return_value = {
            "esearchresult": {"idlist": ["12345678"]}
        }
        mock_search_response.raise_for_status = Mock()

        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Paper</ArticleTitle>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                    </Article>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>"""

        mock_fetch_response = Mock()
        mock_fetch_response.content = xml_content.encode()
        mock_fetch_response.raise_for_status = Mock()

        mock_get.side_effect = [mock_search_response, mock_fetch_response]

        connector = PubMedConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        # Affiliations should be None or empty list
        assert results[0].affiliations is None or len(results[0].affiliations) == 0


class TestCrossrefAffiliationExtraction:
    """Test Crossref affiliation extraction."""

    @patch("src.search.database_connectors.requests.get")
    def test_crossref_affiliation_extraction(self, mock_get):
        """Test that affiliations are extracted from Crossref JSON."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "abstract": "Test abstract",
                        "author": [
                            {
                                "given": "John",
                                "family": "Smith",
                                "affiliation": [
                                    {"name": "University of California, San Francisco"},
                                    {"name": "Department of Health"}
                                ]
                            },
                            {
                                "given": "Jane",
                                "family": "Doe",
                                "affiliation": [{"name": "Harvard University"}]
                            }
                        ],
                        "published-print": {"date-parts": [[2023]]},
                        "DOI": "10.1000/test"
                    }
                ],
                "next-cursor": None
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        connector = CrossrefConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        paper = results[0]
        assert paper.affiliations is not None
        assert len(paper.affiliations) >= 2
        assert any("University of California" in aff for aff in paper.affiliations)
        assert any("Harvard" in aff for aff in paper.affiliations)


class TestScopusAffiliationExtraction:
    """Test Scopus affiliation extraction."""

    @patch("src.search.database_connectors.requests.get")
    def test_scopus_affiliation_extraction(self, mock_get):
        """Test that affiliations are extracted from Scopus API."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "search-results": {
                "entry": [
                    {
                        "dc:title": "Test Paper",
                        "dc:description": "Test abstract",
                        "dc:creator": "Smith, J.",
                        "prism:coverDate": "2023-01-01",
                        "prism:doi": "10.1000/test",
                        "affiliation": [
                            {
                                "affilname": "University of California, San Francisco",
                                "affiliation-city": "San Francisco",
                                "affiliation-country": "United States"
                            },
                            {
                                "affilname": "Harvard Medical School",
                                "affiliation-city": "Boston",
                                "affiliation-country": "United States"
                            }
                        ]
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        connector = ScopusConnector(api_key="test_key")
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        paper = results[0]
        assert paper.affiliations is not None
        assert len(paper.affiliations) == 2
        assert "University of California" in paper.affiliations[0]
        assert "Harvard" in paper.affiliations[1]


class TestSemanticScholarAffiliationExtraction:
    """Test Semantic Scholar affiliation extraction."""

    @patch("src.search.database_connectors.requests.get")
    def test_semanticscholar_affiliation_extraction(self, mock_get):
        """Test that affiliations are extracted from Semantic Scholar API."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "authors": [
                        {
                            "name": "John Smith",
                            "affiliation": "University of California, San Francisco"
                        },
                        {
                            "name": "Jane Doe",
                            "affiliation": "Harvard University"
                        }
                    ],
                    "year": 2023,
                    "externalIds": {"DOI": "10.1000/test"},
                    "url": "https://example.com/paper"
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        connector = SemanticScholarConnector()
        results = connector.search("test query", max_results=10)

        assert len(results) > 0
        paper = results[0]
        assert paper.affiliations is not None
        assert len(paper.affiliations) == 2
        assert "University of California" in paper.affiliations[0]
        assert "Harvard" in paper.affiliations[1]
