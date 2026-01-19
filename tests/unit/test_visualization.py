"""
Unit tests for visualization/charts module.
"""

from pathlib import Path
from src.visualization.charts import ChartGenerator
from src.search.database_connectors import Paper


class TestChartGenerator:
    """Test ChartGenerator class."""

    def test_chart_generator_initialization(self, tmp_path):
        """Test ChartGenerator initialization."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        assert generator.output_dir == Path(tmp_path)
        assert generator.output_dir.exists()

    def test_papers_per_year_empty_list(self, tmp_path):
        """Test papers_per_year with empty list."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        result = generator.papers_per_year([])

        assert result == ""

    def test_papers_per_year_no_years(self, tmp_path):
        """Test papers_per_year with papers without years."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = [
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], year=None),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"], year=None),
        ]

        result = generator.papers_per_year(papers)

        assert result == ""

    def test_papers_per_year_with_years(self, tmp_path):
        """Test papers_per_year with papers that have years."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = [
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], year=2020),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"], year=2021),
            Paper(title="Paper 3", abstract="Abstract 3", authors=["Author 3"], year=2021),
            Paper(title="Paper 4", abstract="Abstract 4", authors=["Author 4"], year=2022),
        ]

        result = generator.papers_per_year(papers)

        assert result != ""
        assert Path(result).exists()
        assert result.endswith(".png")

    def test_papers_per_year_custom_path(self, tmp_path):
        """Test papers_per_year with custom output path."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        custom_path = tmp_path / "custom_chart.png"
        papers = [Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], year=2020)]

        result = generator.papers_per_year(papers, output_path=str(custom_path))

        assert result == str(custom_path)
        assert Path(result).exists()

    def test_papers_by_country_empty_list(self, tmp_path):
        """Test papers_by_country with empty list."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        result = generator.papers_by_country([])

        assert result == ""

    def test_papers_by_country_with_papers(self, tmp_path):
        """Test papers_by_country with papers."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = [Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"])]

        result = generator.papers_by_country(papers)

        # Should create placeholder chart
        assert result != ""
        assert Path(result).exists()
        assert result.endswith(".png")

    def test_papers_by_subject_empty_list(self, tmp_path):
        """Test papers_by_subject with empty list."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        result = generator.papers_by_subject([])

        assert result == ""

    def test_papers_by_subject_with_papers(self, tmp_path):
        """Test papers_by_subject with papers."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = [Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"])]

        result = generator.papers_by_subject(papers)

        # Should create placeholder chart
        assert result != ""
        assert Path(result).exists()
        assert result.endswith(".png")

    def test_network_graph_empty_list(self, tmp_path):
        """Test network_graph with empty list."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        result = generator.network_graph([])

        assert result == ""

    def test_network_graph_with_papers(self, tmp_path):
        """Test network_graph with papers."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = [
            Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"]),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"]),
            Paper(title="Paper 3", abstract="Abstract 3", authors=["Author 3"]),
        ]

        result = generator.network_graph(papers)

        # Should create network graph if networkx and pyvis are available
        if result:  # Only if both libraries are installed
            assert Path(result).exists()
            # Now generates HTML file (primary) and PNG (fallback)
            assert result.endswith(".html") or result.endswith(".png")

    def test_papers_per_year_many_years(self, tmp_path):
        """Test papers_per_year with many years (tests rotation logic)."""
        generator = ChartGenerator(output_dir=str(tmp_path))

        papers = []
        for year in range(2010, 2025):
            papers.append(
                Paper(title=f"Paper {year}", abstract="Abstract", authors=["Author"], year=year)
            )

        result = generator.papers_per_year(papers)

        assert result != ""
        assert Path(result).exists()
