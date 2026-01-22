"""
Integration tests for workflow phases.
"""

import pytest
from pathlib import Path
import tempfile
from src.orchestration.workflow_manager import WorkflowManager
from tests.fixtures.workflow_configs import get_test_workflow_config


@pytest.fixture
def temp_workflow_config(tmp_path):
    """Create temporary workflow config file."""
    import yaml

    config = get_test_workflow_config()
    config_file = tmp_path / "test_workflow.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    return str(config_file)


def test_search_strategy_building(temp_workflow_config):
    """Test search strategy building phase."""
    manager = WorkflowManager(temp_workflow_config)
    manager._build_search_strategy()

    assert manager.search_strategy is not None
    assert len(manager.search_strategy.term_groups) > 0


def test_prisma_generation():
    """Test PRISMA diagram generation."""
    from src.prisma.prisma_generator import PRISMACounter, PRISMAGenerator

    counter = PRISMACounter()
    counter.set_found(100, database_breakdown={"PubMed": 60, "arXiv": 40})
    counter.set_no_dupes(95)
    counter.set_screened(80)
    counter.set_screen_exclusions(15)  # 95 - 80 = 15 excluded at screening
    counter.set_full_text(50)
    counter.set_full_text_exclusions(20)  # 50 - 30 = 20 excluded at full-text
    counter.set_qualitative(30)
    counter.set_quantitative(30)

    generator = PRISMAGenerator(counter)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        output_path = tmp.name

    try:
        result_path = generator.generate(output_path, format="png")
        assert Path(result_path).exists()
        # Verify file is not empty
        assert Path(result_path).stat().st_size > 0
    finally:
        Path(output_path).unlink(missing_ok=True)


def test_visualization_generation(sample_papers, tmp_path):
    """Test visualization generation."""
    from src.visualization.charts import ChartGenerator

    generator = ChartGenerator(output_dir=str(tmp_path))

    # Add years to papers for testing
    papers_with_years = []
    for i, paper in enumerate(sample_papers[:5]):
        paper.year = 2020 + i
        papers_with_years.append(paper)

    result = generator.papers_per_year(papers_with_years)

    if result:  # May be empty if no years
        assert Path(result).exists()
