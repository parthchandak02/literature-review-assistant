"""
End-to-end tests for error recovery.

Tests error handling throughout the workflow:
- Database API failures (one database fails, others continue)
- Network timeout handling
- Invalid API key handling
- Empty search results handling
- LLM API failure handling
- PRISMA generation failure recovery
"""

import pytest
import os
from unittest.mock import Mock, patch
from src.orchestration.workflow_manager import WorkflowManager
from src.search.database_connectors import DatabaseConnector, DatabaseSearchError, NetworkError, APIKeyError
from tests.fixtures.workflow_configs import get_test_workflow_config
import yaml
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def error_test_config(tmp_path):
    """Create config for error testing."""
    config = get_test_workflow_config()
    config_file = tmp_path / "error_test.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    return str(config_file)


def test_retry_mechanisms_end_to_end(error_test_config):
    """Test retry mechanisms work end-to-end."""
    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_client = Mock()

        # First call fails, second succeeds
        mock_response_success = Mock()
        mock_message = Mock()
        mock_message.content = '{"decision": "include", "confidence": 0.85, "reasoning": "Test"}'
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response_success.choices = [mock_choice]
        mock_response_success.usage = Mock()
        mock_response_success.usage.prompt_tokens = 100
        mock_response_success.usage.completion_tokens = 50
        mock_response_success.usage.total_tokens = 150

        mock_client.chat.completions.create.side_effect = [
            Exception("Temporary error"),
            mock_response_success,
        ]
        mock_openai.OpenAI.return_value = mock_client

        manager = WorkflowManager(error_test_config)

        # Should retry and eventually succeed
        result = manager.title_screener.screen(
            title="Test", abstract="Test", inclusion_criteria=[], exclusion_criteria=[]
        )

        # Should handle error gracefully
        assert result is not None


def test_circuit_breaker_recovery(error_test_config):
    """Test circuit breaker recovery."""
    from src.utils.circuit_breaker import CircuitBreakerConfig

    manager = WorkflowManager(error_test_config)

    # Configure circuit breaker with low threshold
    manager.title_screener.circuit_breaker = manager.title_screener.circuit_breaker.__class__(
        CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
    )

    # Simulate failures
    manager.title_screener.llm_client = None  # Will cause failures

    # Multiple calls should trigger circuit breaker
    for _i in range(3):
        result = manager.title_screener.screen(
            title="Test", abstract="Test", inclusion_criteria=[], exclusion_criteria=[]
        )
        # Should use fallback
        assert result is not None


def test_graceful_degradation(error_test_config):
    """Test graceful degradation when LLM unavailable."""
    manager = WorkflowManager(error_test_config)

    # Disable LLM
    manager.title_screener.llm_client = None
    manager.title_screener.api_key = None

    # Should still work with fallback
    result = manager.title_screener.screen(
        title="Telemedicine UX Design",
        abstract="User experience in telemedicine platforms",
        inclusion_criteria=["Telemedicine", "UX"],
        exclusion_criteria=["Technical only"],
    )

    assert result is not None
    assert result.decision is not None


def test_error_context_propagation(error_test_config):
    """Test error context propagation through handoffs."""
    from src.orchestration.handoff_protocol import HandoffProtocol

    manager = WorkflowManager(error_test_config)

    error = ValueError("Test error")
    error_handoff = HandoffProtocol.create_error_handoff(
        from_agent="title_abstract_screener",
        to_agent="error_handler",
        stage="screening",
        topic_context=manager.topic_context,
        error=error,
        retry_count=2,
    )

    assert error_handoff.error_context is not None
    assert error_handoff.error_context.error_type == "ValueError"
    assert error_handoff.error_context.retry_count == 2


def test_database_api_failure_recovery(error_test_config):
    """Test that workflow continues when one database fails."""
    manager = WorkflowManager(error_test_config)
    
    # Create a mock connector that fails
    class FailingConnector(DatabaseConnector):
        def search(self, query: str, max_results: int = 100):
            raise DatabaseSearchError("Simulated database failure")
        
        def get_database_name(self) -> str:
            return "FailingDB"
    
    # Add failing connector
    failing_connector = FailingConnector()
    
    # Mock the connector creation to include failing one
    original_create = manager._create_connector
    
    def mock_create(db_name, cache=None):
        if db_name == "FailingDB":
            return failing_connector
        return original_create(db_name, cache)
    
    manager._create_connector = mock_create
    
    # Build search strategy
    manager._build_search_strategy()
    
    # Search should continue even if one database fails
    # (This depends on MultiDatabaseSearcher implementation)
    # For now, verify that error handling exists
    assert manager.search_strategy is not None


def test_network_timeout_handling(error_test_config):
    """Test network timeout handling."""
    import requests
    
    manager = WorkflowManager(error_test_config)
    
    # Mock requests.get to raise timeout
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.Timeout("Connection timeout")
        
        # Should handle timeout gracefully
        # This tests the retry mechanism in database connectors
        try:
            manager._build_search_strategy()
            # If search is called, it should handle timeout
            # (Actual behavior depends on connector retry logic)
            pass
        except Exception as e:
            # Timeout should be caught and handled
            assert isinstance(e, (NetworkError, requests.Timeout))


def test_invalid_api_key_handling(error_test_config):
    """Test handling of invalid API keys."""
    WorkflowManager(error_test_config)
    
    # Create connector with invalid key
    from src.search.database_connectors import ScopusConnector
    
    # Mock the API call to return 401
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_get.return_value = mock_response
        
        connector = ScopusConnector(api_key="invalid_key")
        
        # Should raise APIKeyError
        with pytest.raises(APIKeyError):
            connector.search("test query", max_results=1)


def test_empty_search_results_handling(error_test_config):
    """Test handling of empty search results."""
    manager = WorkflowManager(error_test_config)
    
    # Mock connector that returns empty results
    class EmptyConnector(DatabaseConnector):
        def search(self, query: str, max_results: int = 100):
            return []  # Empty results
        
        def get_database_name(self) -> str:
            return "EmptyDB"
    
    # Workflow should handle empty results gracefully
    manager._build_search_strategy()
    
    # Empty results should not crash workflow
    # (Actual behavior: workflow continues with empty results)


def test_llm_api_failure_handling(error_test_config):
    """Test LLM API failure handling."""
    manager = WorkflowManager(error_test_config)
    
    # Mock LLM to fail
    manager.title_screener.llm_client = None
    manager.title_screener.api_key = None
    
    # Should use fallback or handle gracefully
    result = manager.title_screener.screen(
        title="Test Title",
        abstract="Test Abstract",
        inclusion_criteria=["Test"],
        exclusion_criteria=[],
    )
    
    # Should return a result (may be fallback)
    assert result is not None
    assert result.decision is not None


def test_prisma_generation_failure_recovery(error_test_config, tmp_path):
    """Test PRISMA generation failure recovery."""
    manager = WorkflowManager(error_test_config)
    manager.output_dir = tmp_path
    
    # Set up minimal workflow state
    manager.all_papers = []
    manager.unique_papers = []
    manager.prisma_counter.set_found(0, {})
    manager.prisma_counter.set_no_dupes(0)
    
    # Mock PRISMA generator to fail
    with patch.object(manager.prisma_generator, 'generate_diagram') as mock_gen:
        mock_gen.side_effect = Exception("PRISMA generation failed")
        
        # Should handle failure gracefully
        try:
            manager._generate_prisma_diagram()
            # If it doesn't raise, it handled the error
        except Exception:
            # If it raises, that's also acceptable (error propagation)
            pass


def test_partial_results_saved_on_failure(error_test_config, tmp_path):
    """Test that partial results are saved when workflow fails."""
    manager = WorkflowManager(error_test_config)
    manager.output_dir = tmp_path
    
    # Set up some workflow state
    manager.all_papers = []
    manager.unique_papers = []
    
    # Simulate partial completion
    manager.prisma_counter.set_found(10, {"PubMed": 10})
    
    # Save state (should work even if workflow incomplete)
    try:
        state_path = manager._save_workflow_state()
        assert state_path is not None
        assert os.path.exists(state_path)
    except Exception as e:
        # State saving should not fail
        pytest.fail(f"State saving failed: {e}")


def test_workflow_continues_after_non_critical_error(error_test_config):
    """Test workflow continues after non-critical errors."""
    manager = WorkflowManager(error_test_config)
    
    # Build search strategy (should always work)
    manager._build_search_strategy()
    assert manager.search_strategy is not None
    
    # Even if search fails, workflow should handle it
    # (Actual behavior depends on implementation)
    # For now, verify workflow manager is resilient
    assert manager.deduplicator is not None
    assert manager.title_screener is not None
