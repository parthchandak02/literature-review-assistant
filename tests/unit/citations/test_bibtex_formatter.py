"""
Tests for BibTeX Formatter
"""

from src.citations.bibtex_formatter import BibTeXFormatter
from src.search.connectors.base import Paper


class TestBibTeXFormatter:
    """Test BibTeX formatter functionality."""

    def test_generate_citation_key(self):
        """Test citation key generation."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Machine Learning for Health",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            abstract="Test abstract",
        )
        key = formatter.generate_citation_key(paper, 1)
        assert key.startswith("Smith2023")
        assert len(key) > 0

    def test_generate_citation_key_duplicates(self):
        """Test citation key uniqueness."""
        formatter = BibTeXFormatter()
        paper1 = Paper(
            title="Machine Learning for Health",
            authors=["Smith, John"],
            year=2023,
        )
        paper2 = Paper(
            title="Machine Learning for Health",
            authors=["Smith, John"],
            year=2023,
        )
        key1 = formatter.generate_citation_key(paper1, 1)
        key2 = formatter.generate_citation_key(paper2, 2)
        assert key1 != key2
        assert key2.endswith("b") or key2 != key1

    def test_determine_entry_type_article(self):
        """Test entry type detection for journal articles."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Paper",
            authors=["Author"],
            journal="Journal of Testing",
            year=2023,
        )
        assert formatter.determine_entry_type(paper) == "article"

    def test_determine_entry_type_conference(self):
        """Test entry type detection for conference papers."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Paper",
            authors=["Author"],
            journal="Proceedings of ICML",
            year=2023,
        )
        assert formatter.determine_entry_type(paper) == "inproceedings"

    def test_determine_entry_type_preprint(self):
        """Test entry type detection for preprints."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Paper",
            authors=["Author"],
            journal="arXiv preprint",
            year=2023,
            database="arXiv",
        )
        assert formatter.determine_entry_type(paper) == "misc"

    def test_format_authors(self):
        """Test author formatting."""
        formatter = BibTeXFormatter()
        authors = ["Smith, John", "Doe, Jane"]
        formatted = formatter.format_authors(authors)
        assert "Smith, John" in formatted
        assert "Doe, Jane" in formatted
        assert " and " in formatted

    def test_format_authors_single(self):
        """Test single author formatting."""
        formatter = BibTeXFormatter()
        authors = ["Smith, John"]
        formatted = formatter.format_authors(authors)
        assert formatted == "Smith, John"

    def test_escape_bibtex(self):
        """Test BibTeX special character escaping."""
        formatter = BibTeXFormatter()
        text = "Test {with} special & characters $ % _ #"
        escaped = formatter.escape_bibtex(text)
        assert "\\{" in escaped
        assert "\\}" in escaped
        assert "\\&" in escaped
        assert "\\$" in escaped
        assert "\\%" in escaped
        assert "\\_" in escaped
        assert "\\#" in escaped

    def test_format_citation_article(self):
        """Test full citation formatting for article."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Article",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            journal="Test Journal",
            doi="10.1000/test",
        )
        key = formatter.generate_citation_key(paper, 1)
        entry = formatter.format_citation(paper, key)
        assert f"@article{{{key}," in entry
        assert "title = {Test Article}" in entry
        assert "author = {" in entry
        assert "year = {2023}" in entry
        assert "journal = {Test Journal}" in entry
        assert "doi = {10.1000/test}" in entry

    def test_format_citation_conference(self):
        """Test full citation formatting for conference."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Conference Paper",
            authors=["Smith, John"],
            year=2023,
            journal="Proceedings of ICML",
        )
        key = formatter.generate_citation_key(paper, 1)
        entry = formatter.format_citation(paper, key)
        assert f"@inproceedings{{{key}," in entry
        assert "booktitle = {Proceedings of ICML}" in entry

    def test_format_citation_with_url(self):
        """Test citation formatting with URL."""
        formatter = BibTeXFormatter()
        paper = Paper(
            title="Test Paper",
            authors=["Author"],
            year=2023,
            url="https://example.com/paper",
        )
        key = formatter.generate_citation_key(paper, 1)
        entry = formatter.format_citation(paper, key)
        assert "url = {https://example.com/paper}" in entry
