"""
Pytest configuration and fixtures.
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.search.database_connectors import Paper
from src.orchestration.topic_propagator import TopicContext
from src.tools.tool_registry import ToolRegistry, Tool, ToolParameter
from src.utils.retry_strategies import RetryConfig
from src.utils.circuit_breaker import CircuitBreakerConfig


@pytest.fixture
def sample_papers() -> List[Paper]:
    """Generate sample Paper objects for testing."""
    return [
        Paper(
            title="Adaptive Interface Design in Telemedicine",
            abstract="This paper explores adaptive interface design for telemedicine applications.",
            authors=["Smith, J.", "Doe, A."],
            year=2022,
            doi="10.1000/test1",
            journal="Journal of Telemedicine",
            database="PubMed",
        ),
        Paper(
            title="User Experience in Digital Health",
            abstract="A study on UX principles in digital health platforms.",
            authors=["Johnson, B."],
            year=2021,
            doi="10.1000/test2",
            journal="Digital Health Review",
            database="Scopus",
        ),
        Paper(
            title="Adaptive Interface Design in Telemedicine",  # Duplicate title
            abstract="This paper explores adaptive interface design for telemedicine applications.",
            authors=["Smith, J.", "Doe, A."],
            year=2022,
            doi="10.1000/test1",  # Same DOI
            journal="Journal of Telemedicine",
            database="Scopus",  # Different database
        ),
    ]


@pytest.fixture
def sample_topic_context() -> TopicContext:
    """Create sample topic context."""
    return TopicContext(
        topic="Adaptive Interface Design in Telemedicine",
        keywords=["telemedicine", "UX", "adaptive interfaces"],
        domain="healthcare",
        research_question="How can adaptive interface design enhance UX?",
        context="Existing studies focus on general usability",
    )


@pytest.fixture
def sample_agent_config() -> Dict[str, Any]:
    """Sample agent configuration."""
    return {
        "role": "Test Agent",
        "goal": "Test goal",
        "backstory": "Test backstory",
        "llm_model": "gemini-2.5-pro",
        "temperature": 0.3,
        "max_iterations": 5,
    }


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create tool registry for testing."""
    registry = ToolRegistry()
    return registry


@pytest.fixture
def sample_tool() -> Tool:
    """Create a sample tool for testing."""

    def execute_test(query: str) -> str:
        return f"Result for: {query}"

    return Tool(
        name="test_tool",
        description="A test tool",
        parameters=[
            ToolParameter(name="query", type="string", description="Test query", required=True)
        ],
        execute_fn=execute_test,
    )


@pytest.fixture
def retry_config() -> RetryConfig:
    """Create retry configuration for testing."""
    from src.utils.retry_strategies import RetryConfig

    return RetryConfig(
        max_attempts=3,
        initial_delay=0.1,
        max_delay=1.0,
        jitter=False,  # Disable jitter for deterministic tests
    )


@pytest.fixture
def circuit_breaker_config() -> CircuitBreakerConfig:
    """Create circuit breaker configuration for testing."""
    from src.utils.circuit_breaker import CircuitBreakerConfig

    return CircuitBreakerConfig(failure_threshold=3, success_threshold=2, timeout=1.0)


@pytest.fixture
def mock_workflow_config() -> Dict[str, Any]:
    """Mock workflow configuration."""
    return {
        "topic": {"topic": "Test Topic"},
        "agents": {
            "title_abstract_screener": {
                "role": "Test Title/Abstract Screener",
                "goal": "Test title/abstract screening",
                "backstory": "Test",
                "llm_model": "gemini-2.5-flash-lite",
                "temperature": 0.2,
            },
            "fulltext_screener": {
                "role": "Test Fulltext Screener",
                "goal": "Test fulltext screening",
                "backstory": "Test",
                "llm_model": "gemini-2.5-flash-lite",
                "temperature": 0.2,
            }
        },
        "workflow": {
            "databases": ["PubMed"],
            "date_range": {"start": None, "end": 2022},
            "language": "English",
            "max_results_per_db": 10,
        },
        "criteria": {"inclusion": ["Test inclusion"], "exclusion": ["Test exclusion"]},
        "output": {"directory": "data/outputs", "formats": ["markdown"]},
    }


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    """Setup test environment."""
    # Set test output directory
    test_output_dir = tmp_path / "test_outputs"
    test_output_dir.mkdir()

    # Mock environment variables
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # Note: PERPLEXITY_SEARCH_API_KEY is still used for database search

    # Set test paths
    monkeypatch.setattr(
        "src.orchestration.workflow_manager.Path", lambda x: test_output_dir / Path(x).name
    )

    yield

    # Cleanup if needed
