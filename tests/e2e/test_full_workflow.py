"""
End-to-end test for full workflow.
"""

import pytest
import yaml
from unittest.mock import Mock, patch
from src.orchestration.workflow_manager import WorkflowManager
from tests.fixtures.workflow_configs import get_test_workflow_config
from tests.fixtures.mock_llm_responses import (
    get_mock_screening_response,
    get_mock_extraction_response,
)


@pytest.fixture
def mock_workflow_config_file(tmp_path):
    """Create mock workflow config file."""
    config = get_test_workflow_config()
    config_file = tmp_path / "workflow.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    return str(config_file)


@pytest.fixture
def mock_llm_responses():
    """Mock LLM responses for workflow."""
    return {
        "screening": get_mock_screening_response("include", 0.85),
        "extraction": get_mock_extraction_response(),
    }


def test_workflow_initialization(mock_workflow_config_file):
    """Test workflow manager initialization."""
    manager = WorkflowManager(mock_workflow_config_file)

    assert manager.topic_context is not None
    assert manager.topic_context.topic == "Test Research Topic"
    assert manager.deduplicator is not None
    assert manager.title_screener is not None


def test_workflow_phases_with_mocks(mock_workflow_config_file, mock_llm_responses):
    """Test workflow phases with mocked LLM."""
    with patch("src.screening.base_agent.openai") as mock_openai_module:
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = mock_llm_responses["screening"]
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_module.OpenAI.return_value = mock_client

        manager = WorkflowManager(mock_workflow_config_file)

        # Test search strategy building
        manager._build_search_strategy()
        assert manager.search_strategy is not None

        # Test database search (will use mock connectors)
        papers = manager._search_databases()
        assert isinstance(papers, list)

        # Test deduplication
        if papers:
            manager.all_papers = papers
            dedup_result = manager.deduplicator.deduplicate_papers(papers)
            manager.unique_papers = dedup_result.unique_papers
            assert len(manager.unique_papers) <= len(papers)


def test_workflow_state_transitions(mock_workflow_config_file):
    """Test workflow state transitions."""
    manager = WorkflowManager(mock_workflow_config_file)

    # Initial state
    assert len(manager.all_papers) == 0
    assert len(manager.unique_papers) == 0

    # After search (mock)
    manager.all_papers = [Mock(title="Test", abstract="Test", authors=[], database="PubMed")]
    manager.prisma_counter.set_found(len(manager.all_papers))

    assert manager.prisma_counter.get_counts()["found"] == 1

    # After deduplication
    manager.unique_papers = manager.all_papers
    manager.prisma_counter.set_no_dupes(len(manager.unique_papers))

    assert manager.prisma_counter.get_counts()["no_dupes"] == 1


def test_workflow_error_scenarios(mock_workflow_config_file):
    """Test workflow with various error scenarios."""
    manager = WorkflowManager(mock_workflow_config_file)

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
    import yaml
    
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
