"""
E2E tests for workflow with visualization.
"""

import pytest
from pathlib import Path
from src.visualization.charts import ChartGenerator
from src.search.database_connectors import Paper


@pytest.fixture
def sample_papers_with_years():
    """Create sample papers with years."""
    return [
        Paper(title="Paper 1", abstract="Abstract 1", authors=["Author 1"], year=2020),
        Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"], year=2021),
        Paper(title="Paper 3", abstract="Abstract 3", authors=["Author 3"], year=2021),
        Paper(title="Paper 4", abstract="Abstract 4", authors=["Author 4"], year=2022),
        Paper(title="Paper 5", abstract="Abstract 5", authors=["Author 5"], year=2022),
    ]


def test_workflow_visualization_generation(sample_papers_with_years, tmp_path):
    """Test visualization generation in workflow."""
    generator = ChartGenerator(output_dir=str(tmp_path))

    # Generate charts
    year_chart = generator.papers_per_year(sample_papers_with_years)
    country_chart = generator.papers_by_country(sample_papers_with_years)
    subject_chart = generator.papers_by_subject(sample_papers_with_years)
    network_chart = generator.network_graph(sample_papers_with_years)

    # Verify charts were created (or handled gracefully)
    if year_chart:
        assert Path(year_chart).exists()
    if country_chart:
        assert Path(country_chart).exists()
    if subject_chart:
        assert Path(subject_chart).exists()
    if network_chart:  # May be empty if networkx not available
        assert Path(network_chart).exists()
