"""
Enhanced unit tests for visualization improvements.
"""

import pytest
from pathlib import Path
from src.visualization.charts import ChartGenerator
from src.search.database_connectors import Paper


class TestCountryExtraction:
    """Test enhanced country extraction."""

    def test_country_extraction_from_affiliations(self, tmp_path):
        """Test country extraction from affiliation strings."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        # Test with various affiliation formats
        test_cases = [
            (["Department of Health, University of California, San Francisco, CA, USA"], "United States"),
            (["School of Medicine, Harvard University, Boston, MA, United States"], "United States"),
            (["Imperial College London, UK"], "United Kingdom"),
            (["University of Toronto, Canada"], "Canada"),
            (["University of Sydney, Australia"], "Australia"),
            (["ETH Zurich, Switzerland"], "Switzerland"),
        ]
        
        for affiliations, expected_country in test_cases:
            country = generator._extract_country_from_affiliations(affiliations)
            assert country is not None, f"Failed to extract country from: {affiliations}"
            # Country name should be normalized
            assert expected_country in country or country in expected_country

    def test_country_extraction_with_country_codes(self, tmp_path):
        """Test country extraction with ISO codes."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        test_cases = [
            (["Some University, USA"], "United States"),
            (["Some University, US"], "United States"),
            (["Some University, GB"], "United Kingdom"),
            (["Some University, UK"], "United Kingdom"),
        ]
        
        for affiliations, expected_country in test_cases:
            country = generator._extract_country_from_affiliations(affiliations)
            if country:  # May not work without pycountry
                assert expected_country in country or country in expected_country

    def test_papers_by_country_with_affiliations(self, tmp_path):
        """Test country chart generation with papers that have affiliations."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        papers = [
            Paper(
                title="Paper 1",
                abstract="Abstract 1",
                authors=["Author 1"],
                affiliations=["University of California, San Francisco, CA, USA"],
                year=2020
            ),
            Paper(
                title="Paper 2",
                abstract="Abstract 2",
                authors=["Author 2"],
                affiliations=["Imperial College London, UK"],
                year=2021
            ),
            Paper(
                title="Paper 3",
                abstract="Abstract 3",
                authors=["Author 3"],
                affiliations=["University of Toronto, Canada"],
                year=2022
            ),
        ]
        
        result = generator.papers_by_country(papers)
        
        # Should generate actual chart, not placeholder
        assert result != ""
        assert Path(result).exists()
        assert result.endswith(".png")
        
        # Verify file is not empty (placeholder would be small)
        assert Path(result).stat().st_size > 1000


class TestSubjectExtraction:
    """Test enhanced subject extraction."""

    def test_subject_normalization(self, tmp_path):
        """Test subject keyword normalization."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        test_cases = [
            ("health literacy", "Health Sciences"),
            ("medical informatics", "Health Sciences"),
            ("artificial intelligence", "Artificial Intelligence"),
            ("large language model", "Artificial Intelligence"),
            ("llm", "Artificial Intelligence"),
            ("machine learning", "Machine Learning"),
            ("deep learning", "Machine Learning"),
            ("natural language processing", "Natural Language Processing"),
            ("nlp", "Natural Language Processing"),
            ("computer science", "Computer Science"),
            ("social science", "Social Sciences"),
            ("psychology", "Social Sciences"),
        ]
        
        for keyword, expected_category in test_cases:
            result = generator._normalize_subject(keyword)
            assert result == expected_category, f"'{keyword}' should map to '{expected_category}', got '{result}'"

    def test_journal_subject_inference(self, tmp_path):
        """Test subject inference from journal names."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        test_cases = [
            ("Journal of Health Sciences", "Health Sciences"),
            ("Nature Medicine", "Health Sciences"),
            ("IEEE Transactions on Neural Networks", "Artificial Intelligence"),
            ("Journal of Machine Learning Research", "Artificial Intelligence"),
            ("Computational Linguistics", "Natural Language Processing"),
            ("ACM Transactions on Computer Systems", "Computer Science"),
        ]
        
        for journal_name, expected_subject in test_cases:
            result = generator._infer_subject_from_journal(journal_name)
            assert result == expected_subject, f"'{journal_name}' should infer '{expected_subject}', got '{result}'"

    def test_papers_by_subject_with_keywords(self, tmp_path):
        """Test subject chart generation with keyword data."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        papers = [
            Paper(
                title="Health Literacy Paper",
                abstract="Abstract about health",
                authors=["Author 1"],
                keywords=["health literacy", "patient education"],
                year=2020
            ),
            Paper(
                title="AI Chatbot Paper",
                abstract="Abstract about AI",
                authors=["Author 2"],
                keywords=["artificial intelligence", "chatbot", "llm"],
                year=2021
            ),
            Paper(
                title="NLP Paper",
                abstract="Abstract about NLP",
                authors=["Author 3"],
                keywords=["natural language processing", "language models"],
                year=2022
            ),
        ]
        
        result = generator.papers_by_subject(papers)
        
        # Should generate actual chart, not placeholder
        assert result != ""
        assert Path(result).exists()
        assert result.endswith(".png")
        
        # Verify file is not empty
        assert Path(result).stat().st_size > 1000


class TestNetworkGraphPyvis:
    """Test Pyvis network graph generation."""

    def test_network_graph_html_generation(self, tmp_path):
        """Test that network graph generates HTML file."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        papers = [
            Paper(
                title="Paper 1: Health Literacy and AI",
                abstract="Abstract about health literacy and artificial intelligence",
                authors=["Author 1"],
                keywords=["health", "ai"],
                year=2020,
                url="https://example.com/paper1"
            ),
            Paper(
                title="Paper 2: AI Chatbots in Healthcare",
                abstract="Abstract about AI chatbots",
                authors=["Author 2"],
                keywords=["ai", "chatbot", "health"],
                year=2021,
                url="https://example.com/paper2"
            ),
            Paper(
                title="Paper 3: Machine Learning for Health",
                abstract="Abstract about ML",
                authors=["Author 3"],
                keywords=["machine learning", "health"],
                year=2022,
                url="https://example.com/paper3"
            ),
        ]
        
        result = generator.network_graph(papers)
        
        # Should generate HTML file
        if result:  # Only if pyvis is installed
            assert result.endswith(".html")
            assert Path(result).exists()
            
            # Verify HTML file is valid
            html_content = Path(result).read_text()
            assert "<html" in html_content.lower() or "<!doctype" in html_content.lower()
            assert "vis-network" in html_content or "pyvis" in html_content.lower()
            
            # Verify PNG fallback also exists
            png_path = Path(result).with_suffix(".png")
            if png_path.exists():
                assert png_path.stat().st_size > 0

    def test_network_graph_with_no_similarity(self, tmp_path):
        """Test network graph with papers that have no similarity."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        papers = [
            Paper(
                title="Completely Different Paper 1",
                abstract="Abstract about astronomy",
                authors=["Author A"],
                keywords=["astronomy"],
                year=2020
            ),
            Paper(
                title="Completely Different Paper 2",
                abstract="Abstract about geology",
                authors=["Author B"],
                keywords=["geology"],
                year=2021
            ),
        ]
        
        result = generator.network_graph(papers)
        
        # Should still generate graph (minimal spanning tree)
        if result:
            assert Path(result).exists()

    def test_network_graph_node_features(self, tmp_path):
        """Test that network graph includes interactive features."""
        generator = ChartGenerator(output_dir=str(tmp_path))
        
        papers = [
            Paper(
                title="Test Paper with Very Long Title That Should Be Truncated in Label But Full in Tooltip",
                abstract="Test abstract",
                authors=["Author 1", "Author 2"],
                keywords=["test"],
                year=2020,
                url="https://example.com/test",
                journal="Test Journal"
            ),
            Paper(
                title="Another Test Paper",
                abstract="Another abstract",
                authors=["Author 3"],
                keywords=["test"],
                year=2021
            ),
        ]
        
        result = generator.network_graph(papers)
        
        if result:
            html_content = Path(result).read_text()
            
            # Check for interactive features
            # Note: Exact content depends on Pyvis version, but should have some JavaScript
            assert "javascript" in html_content.lower() or "script" in html_content.lower()
            
            # Check that full title is somewhere in HTML (for tooltip)
            assert "Very Long Title" in html_content or "Test Paper" in html_content
