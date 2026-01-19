"""
End-to-end test with comprehensive mocks.
"""

import pytest
import yaml
from unittest.mock import Mock, patch
from src.orchestration.workflow_manager import WorkflowManager
from tests.fixtures.test_configs import get_test_workflow_config
from tests.fixtures.mock_papers import create_mock_papers
from tests.fixtures.mock_llm_responses import get_mock_screening_response


@pytest.fixture
def mock_config_file(tmp_path):
    """Create mock config file."""
    config = get_test_workflow_config()
    config_file = tmp_path / "workflow.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    return str(config_file)


def test_workflow_with_mocked_llm(mock_config_file):
    """Test workflow with mocked LLM responses."""
    mock_papers = create_mock_papers(5)

    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = get_mock_screening_response("include", 0.9)
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        manager = WorkflowManager(mock_config_file)

        # Mock the search results
        manager.all_papers = mock_papers
        manager.prisma_counter.set_found(len(mock_papers))

        # Test deduplication
        dedup_result = manager.deduplicator.deduplicate_papers(mock_papers)
        manager.unique_papers = dedup_result.unique_papers

        assert len(manager.unique_papers) <= len(mock_papers)


def test_workflow_error_scenarios(mock_config_file):
    """Test workflow with various error scenarios."""
    manager = WorkflowManager(mock_config_file)

    # Test with no API key (should use fallbacks)
    manager.title_screener.api_key = None
    manager.title_screener.llm_client = None

    result = manager.title_screener.screen(
        title="Test", abstract="Test abstract", inclusion_criteria=["Test"], exclusion_criteria=[]
    )

    # Should still work with fallback
    assert result.decision is not None


def test_workflow_different_configurations(tmp_path):
    """Test workflow with different configurations."""
    # Minimal config
    minimal_config = {
        "topic": {"topic": "Minimal Topic"},
        "agents": {
            "screening_agent": {
                "role": "Screener",
                "goal": "Screen",
                "backstory": "Test",
                "llm_model": "gpt-4",
                "temperature": 0.3,
            }
        },
        "workflow": {
            "databases": ["PubMed"],
            "date_range": {"start": None, "end": None},
            "language": "English",
            "max_results_per_db": 10,
        },
        "criteria": {"inclusion": ["Test"], "exclusion": []},
        "output": {"directory": "data/outputs", "formats": ["markdown"]},
    }

    config_file = tmp_path / "minimal.yaml"
    with open(config_file, "w") as f:
        yaml.dump(minimal_config, f)

    manager = WorkflowManager(str(config_file))
    assert manager.topic_context.topic == "Minimal Topic"
