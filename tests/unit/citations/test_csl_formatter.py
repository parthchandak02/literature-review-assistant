"""
Tests for CSL Formatter
"""

import pytest
import json
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from src.citations.csl_formatter import CSLFormatter
from src.search.connectors.base import Paper


class TestCSLFormatter:
    """Test CSLFormatter."""

    def test_formatter_initialization(self):
        """Test formatter initialization."""
        formatter = CSLFormatter()
        assert formatter is not None
        assert formatter.cache_dir.exists()

    def test_formatter_initialization_custom_cache(self, tmp_path):
        """Test formatter initialization with custom cache directory."""
        cache_dir = tmp_path / "custom_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        assert formatter.cache_dir == cache_dir
        assert cache_dir.exists()

    def test_get_available_styles(self):
        """Test getting available styles."""
        formatter = CSLFormatter()
        styles = formatter.get_available_styles()
        assert isinstance(styles, list)
        assert len(styles) > 0
        assert "ieee" in styles
        assert "apa" in styles

    def test_paper_to_csl(self):
        """Test Paper to CSL conversion."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            abstract="Test abstract",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            doi="10.1000/test",
            journal="Test Journal",
            url="https://example.com/paper",
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["title"] == "Test Paper"
        assert len(csl_item["author"]) == 2
        assert csl_item["issued"]["date-parts"][0][0] == 2023
        assert csl_item["DOI"] == "10.1000/test"
        assert csl_item["container-title"] == "Test Journal"

    def test_paper_to_csl_missing_fields(self):
        """Test Paper to CSL with missing optional fields."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            # Missing abstract, authors, year, doi, journal, url
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["title"] == "Test Paper"
        assert "abstract" not in csl_item
        assert "author" not in csl_item
        assert "issued" not in csl_item
        assert "DOI" not in csl_item
        assert "container-title" not in csl_item
        assert "URL" not in csl_item

    def test_paper_to_csl_author_formats(self):
        """Test Paper to CSL with various author name formats."""
        formatter = CSLFormatter()
        
        # Test with "Last, First" format
        paper1 = Paper(
            title="Paper 1",
            authors=["Smith, John", "Doe, Jane"],
        )
        csl_item1 = formatter.paper_to_csl(paper1)
        assert len(csl_item1["author"]) == 2
        assert csl_item1["author"][0]["family"] == "Smith"
        assert csl_item1["author"][0]["given"] == "John"
        
        # Test with "First Last" format
        paper2 = Paper(
            title="Paper 2",
            authors=["John Smith", "Jane Doe"],
        )
        csl_item2 = formatter.paper_to_csl(paper2)
        assert len(csl_item2["author"]) == 2
        assert csl_item2["author"][0]["family"] == "Smith"
        assert csl_item2["author"][0]["given"] == "John"
        
        # Test with single name
        paper3 = Paper(
            title="Paper 3",
            authors=["Smith"],
        )
        csl_item3 = formatter.paper_to_csl(paper3)
        assert len(csl_item3["author"]) == 1
        assert csl_item3["author"][0]["literal"] == "Smith"

    def test_paper_to_csl_keywords_list(self):
        """Test Paper to CSL with keywords as list."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            keywords=["keyword1", "keyword2", "keyword3"],
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["keyword"] == ["keyword1", "keyword2", "keyword3"]

    def test_paper_to_csl_keywords_string(self):
        """Test Paper to CSL with keywords as string."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            keywords="single keyword",
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["keyword"] == ["single keyword"]

    def test_format_citations(self):
        """Test formatting multiple papers."""
        formatter = CSLFormatter()
        papers = [
            Paper(
                title="Paper 1",
                abstract="Abstract 1",
                authors=["Author 1"],
                year=2023,
            ),
            Paper(
                title="Paper 2",
                abstract="Abstract 2",
                authors=["Author 2"],
                year=2024,
            ),
        ]
        csl_items = formatter.format_citations(papers, style="ieee")
        assert len(csl_items) == 2
        assert csl_items[0]["title"] == "Paper 1"
        assert csl_items[1]["title"] == "Paper 2"

    def test_export_csl_json(self, tmp_path):
        """Test CSL JSON export."""
        formatter = CSLFormatter()
        papers = [
            Paper(
                title="Test Paper",
                abstract="Test",
                authors=["Author"],
                year=2023,
            )
        ]
        output_path = tmp_path / "references.json"
        result_path = formatter.export_csl_json(papers, output_path)
        assert result_path.exists()
        assert result_path == output_path
        
        # Verify JSON content
        with open(result_path, "r") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Paper"

    def test_export_csl_json_empty_list(self, tmp_path):
        """Test export_csl_json with empty papers list."""
        formatter = CSLFormatter()
        output_path = tmp_path / "references.json"
        result_path = formatter.export_csl_json([], output_path)
        assert result_path.exists()
        
        # Verify JSON content is empty list
        with open(result_path, "r") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_export_csl_json_creates_directory(self, tmp_path):
        """Test export_csl_json creates parent directory if needed."""
        formatter = CSLFormatter()
        papers = [
            Paper(
                title="Test Paper",
                authors=["Author"],
                year=2023,
            )
        ]
        output_path = tmp_path / "subdir" / "references.json"
        result_path = formatter.export_csl_json(papers, output_path)
        assert result_path.exists()
        assert output_path.parent.exists()

    def test_download_style_caching(self, tmp_path):
        """Test CSL style caching behavior."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        # Create a cached style file
        style_file = cache_dir / "ieee.csl"
        style_file.parent.mkdir(parents=True, exist_ok=True)
        style_file.write_text("/* IEEE Style */")
        
        # Should return cached file without downloading
        with patch("urllib.request.urlretrieve") as mock_download:
            result = formatter.download_style("ieee")
            assert result == style_file
            mock_download.assert_not_called()

    def test_download_style_success(self, tmp_path):
        """Test CSL style downloading with mocking."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        # Mock successful download
        with patch("urllib.request.urlretrieve") as mock_download:
            # Create a mock file-like object
            mock_file = MagicMock()
            mock_file.write = MagicMock()
            mock_download.return_value = (mock_file, None)
            
            # Mock file writing
            with patch("builtins.open", mock_open()):
                style_path = formatter.download_style("ieee")
                assert style_path == cache_dir / "ieee.csl"
                mock_download.assert_called()

    def test_download_style_failure(self, tmp_path):
        """Test style download failure handling."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        # Mock all download attempts failing
        with patch("urllib.request.urlretrieve") as mock_download:
            mock_download.side_effect = urllib.error.HTTPError(
                "url", 404, "Not Found", {}, None
            )
            
            with pytest.raises(ValueError) as exc_info:
                formatter.download_style("nonexistent-style")
            assert "Could not download CSL style" in str(exc_info.value)

    def test_download_style_tries_multiple_names(self, tmp_path):
        """Test that download tries multiple possible file names."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        call_count = 0
        
        def mock_urlretrieve(url, filename):
            nonlocal call_count
            call_count += 1
            if call_count == 3:  # Success on third try
                Path(filename).write_text("/* Style */")
                return
            raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        
        with patch("urllib.request.urlretrieve", side_effect=mock_urlretrieve):
            style_path = formatter.download_style("test-style")
            assert style_path.exists()
            assert call_count == 3

    def test_get_style_path_existing(self, tmp_path):
        """Test get_style_path with existing cached style."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        # Create cached style
        style_file = cache_dir / "ieee.csl"
        style_file.parent.mkdir(parents=True, exist_ok=True)
        style_file.write_text("/* IEEE Style */")
        
        result = formatter.get_style_path("ieee")
        assert result == style_file

    def test_get_style_path_non_existent(self, tmp_path):
        """Test get_style_path with non-existent style."""
        cache_dir = tmp_path / "csl_cache"
        formatter = CSLFormatter(cache_dir=cache_dir)
        
        # Mock download to fail
        with patch.object(formatter, "download_style") as mock_download:
            mock_download.side_effect = ValueError("Style not found")
            
            with pytest.raises(ValueError):
                formatter.get_style_path("nonexistent-style")

    def test_paper_to_csl_type(self):
        """Test Paper to CSL sets correct type."""
        formatter = CSLFormatter()
        paper = Paper(title="Test Paper")
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["type"] == "article-journal"

    def test_paper_to_csl_abstract(self):
        """Test Paper to CSL includes abstract."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            abstract="This is a test abstract.",
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["abstract"] == "This is a test abstract."

    def test_paper_to_csl_year(self):
        """Test Paper to CSL includes year."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            year=2023,
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["issued"]["date-parts"][0][0] == 2023

    def test_paper_to_csl_url(self):
        """Test Paper to CSL includes URL."""
        formatter = CSLFormatter()
        paper = Paper(
            title="Test Paper",
            url="https://example.com/paper",
        )
        csl_item = formatter.paper_to_csl(paper)
        assert csl_item["URL"] == "https://example.com/paper"
