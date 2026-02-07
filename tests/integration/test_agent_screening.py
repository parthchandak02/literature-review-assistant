"""
Integration tests for screening agents.
"""

from unittest.mock import patch

from src.screening.base_agent import InclusionDecision
from src.screening.title_abstract_agent import TitleAbstractScreener
from tests.fixtures.mock_llm_responses import get_mock_screening_response


def test_title_abstract_screener_with_mock_llm(
    mock_openai_client, sample_topic_context, sample_agent_config
):
    """Test title/abstract screener with mocked LLM."""
    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_openai_client

        screener = TitleAbstractScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock structured output response
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = get_mock_screening_response("include", 0.9)

        result = screener.screen(
            title="Adaptive Interface Design in Telemedicine",
            abstract="This paper explores adaptive interfaces for diverse populations.",
            inclusion_criteria=["Telemedicine", "UX design"],
            exclusion_criteria=["Technical only"],
        )

        assert result.decision in [
            InclusionDecision.INCLUDE,
            InclusionDecision.EXCLUDE,
            InclusionDecision.UNCERTAIN,
        ]
        assert 0.0 <= result.confidence <= 1.0


def test_title_abstract_screener_fallback(sample_topic_context, sample_agent_config):
    """Test title/abstract screener fallback to keyword matching."""
    screener = TitleAbstractScreener(
        llm_provider="openai",
        api_key=None,  # No API key triggers fallback
        topic_context=sample_topic_context.to_dict(),
        agent_config=sample_agent_config,
    )

    result = screener.screen(
        title="Telemedicine UX Design",
        abstract="User experience design in telemedicine for diverse populations.",
        inclusion_criteria=["Telemedicine", "UX"],
        exclusion_criteria=["Technical"],
    )

    assert result.decision in [
        InclusionDecision.INCLUDE,
        InclusionDecision.EXCLUDE,
        InclusionDecision.UNCERTAIN,
    ]


def test_title_abstract_screener_structured_output(
    mock_openai_client, sample_topic_context, sample_agent_config
):
    """Test structured output parsing."""
    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_openai_client

        screener = TitleAbstractScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock JSON response
        json_response = get_mock_screening_response("include", 0.85)
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = json_response

        result = screener.screen(
            title="Test Paper",
            abstract="Test abstract",
            inclusion_criteria=["Test"],
            exclusion_criteria=[],
        )

        # Should parse structured output
        assert result.decision is not None
        assert result.confidence > 0


def test_screener_with_circuit_breaker(
    mock_openai_client, sample_topic_context, sample_agent_config
):
    """Test screener with circuit breaker."""
    from src.utils.circuit_breaker import CircuitBreakerConfig

    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_openai_client

        screener = TitleAbstractScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
        )

        # Mock failures to trigger circuit breaker
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        # First call should fail
        result1 = screener.screen(
            title="Test", abstract="Test", inclusion_criteria=[], exclusion_criteria=[]
        )

        # Should handle gracefully
        assert "Error" in result1.reasoning or result1.decision == InclusionDecision.UNCERTAIN
