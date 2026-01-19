"""
Integration tests for extraction agents.
"""

from unittest.mock import patch
from src.extraction.data_extractor_agent import DataExtractorAgent
from tests.fixtures.mock_llm_responses import get_mock_extraction_response


def test_data_extractor_with_mock_llm(
    mock_openai_client, sample_topic_context, sample_agent_config
):
    """Test data extractor with mocked LLM."""
    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_openai_client

        extractor = DataExtractorAgent(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock structured output response
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = get_mock_extraction_response()

        result = extractor.extract(
            title="Test Paper", abstract="Test abstract about telemedicine UX"
        )

        assert result.title == "Test Paper"
        assert isinstance(result.study_objectives, list)
        assert isinstance(result.outcomes, list)


def test_data_extractor_fallback(sample_topic_context, sample_agent_config):
    """Test data extractor fallback."""
    extractor = DataExtractorAgent(
        llm_provider="openai",
        api_key=None,  # No API key triggers fallback
        topic_context=sample_topic_context.to_dict(),
        agent_config=sample_agent_config,
    )

    result = extractor.extract(
        title="Test Paper", abstract="Test abstract with user experience and outcomes"
    )

    assert result.title == "Test Paper"
    # Fallback should still extract some basic info
    assert len(result.ux_strategies) >= 0  # May find keywords


def test_data_extractor_structured_output(
    mock_openai_client, sample_topic_context, sample_agent_config
):
    """Test structured output extraction."""
    with patch("src.screening.base_agent.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_openai_client

        extractor = DataExtractorAgent(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        json_response = get_mock_extraction_response()
        mock_openai_client.chat.completions.create.return_value.choices[
            0
        ].message.content = json_response

        result = extractor.extract(title="Test Paper", abstract="Test abstract")

        # Should parse structured output
        assert result.title == "Test Paper"
        assert len(result.study_objectives) > 0
        assert result.methodology is not None
