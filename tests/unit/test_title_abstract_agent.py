"""
Unit tests for title/abstract screening agent.

Tests all failure modes for TitleAbstractScreener, including response parsing edge cases.
"""

import json
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.screening.base_agent import InclusionDecision
from src.screening.title_abstract_agent import TitleAbstractScreener
from tests.fixtures.llm_response_factory import LLMResponseFactory
from tests.fixtures.recorded_llm_responses import (
    PLAIN_TEXT_RESPONSE_PAPER4,
    VALID_INCLUDE_RESPONSE,
)


@pytest.mark.fast
@pytest.mark.unit
class TestTitleAbstractScreener:
    """Test TitleAbstractScreener agent."""

    def test_screener_initialization(self, sample_topic_context, sample_agent_config):
        """Test TitleAbstractScreener initialization."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert screener.llm_provider == "gemini"
        assert screener.topic_context is not None

    def test_screen_with_llm(self, sample_topic_context, sample_agent_config):
        """Test basic screening with LLM."""
        screener = TitleAbstractScreener(
            llm_provider="openai",
            api_key=None,  # Use fallback
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener.screen(
            title="Test Paper",
            abstract="Test abstract about relevant topic",
            inclusion_criteria=["relevant topic"],
            exclusion_criteria=[],
        )

        assert result is not None
        assert result.decision in [
            InclusionDecision.INCLUDE,
            InclusionDecision.EXCLUDE,
            InclusionDecision.UNCERTAIN,
        ]

    @pytest.mark.fast
    @pytest.mark.regression
    def test_convert_schema_to_result_with_none(self, sample_topic_context, sample_agent_config):
        """Test _convert_schema_to_result handles None gracefully (NEW)."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Pass None - should not crash
        result = screener._convert_schema_to_result(None)

        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.3
        assert "parsing failed" in result.reasoning.lower()

    @pytest.mark.fast
    @pytest.mark.regression
    def test_screen_with_structured_output_failure_fallback(
        self, sample_topic_context, sample_agent_config
    ):
        """Test screen falls back to text parsing when structured output fails (NEW)."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock structured output to fail
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = ValidationError("Schema validation failed", [])

            # Mock text-based call to succeed
            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                result = screener.screen(
                    title="Test Paper",
                    abstract="Test abstract",
                    inclusion_criteria=["health science"],
                    exclusion_criteria=["general education"],
                )

                # Verify fallback was used
                assert result is not None
                assert mock_text.called
                assert result.decision == InclusionDecision.EXCLUDE

    @pytest.mark.fast
    @pytest.mark.regression
    def test_screen_handles_plain_text_response(self, sample_topic_context, sample_agent_config):
        """Test screen handles plain text response from LLM (NEW)."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Simulate plain text response
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = json.JSONDecodeError("Not JSON", "", 0)

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # This MUST NOT crash
                result = screener.screen(
                    title="Test Paper",
                    abstract="Test abstract",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result is not None
                assert result.decision is not None

    def test_fallback_screen(self, sample_topic_context, sample_agent_config):
        """Test fallback keyword matching."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key=None,  # No API key triggers fallback
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener.screen(
            title="Telemedicine UX Study",
            abstract="Research on telemedicine user experience",
            inclusion_criteria=["telemedicine", "UX"],
            exclusion_criteria=["editorial"],
        )

        assert result is not None
        assert result.decision in [
            InclusionDecision.INCLUDE,
            InclusionDecision.EXCLUDE,
            InclusionDecision.UNCERTAIN,
        ]

    def test_build_screening_prompt(self, sample_topic_context, sample_agent_config):
        """Test prompt building."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        prompt = screener._build_screening_prompt(
            title="Test Title",
            abstract="Test abstract",
            inclusion_criteria=["Criterion 1", "Criterion 2"],
            exclusion_criteria=["Exclusion 1"],
        )

        assert "Test Title" in prompt
        assert "Test abstract" in prompt
        assert "Criterion 1" in prompt
        assert "Criterion 2" in prompt
        assert "Exclusion 1" in prompt

    def test_parse_llm_response_include(self, sample_topic_context, sample_agent_config):
        """Test parsing INCLUDE decision."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        response = """DECISION: INCLUDE
CONFIDENCE: 0.9
REASONING: Meets all inclusion criteria"""

        result = screener._parse_llm_response(response)

        assert result.decision == InclusionDecision.INCLUDE
        assert result.confidence == 0.9

    def test_parse_llm_response_exclude(self, sample_topic_context, sample_agent_config):
        """Test parsing EXCLUDE decision."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        response = """DECISION: EXCLUDE
CONFIDENCE: 0.85
REASONING: Does not meet criteria
EXCLUSION_REASON: Wrong domain"""

        result = screener._parse_llm_response(response)

        assert result.decision == InclusionDecision.EXCLUDE
        assert result.confidence == 0.85
        assert result.exclusion_reason == "Wrong domain"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
