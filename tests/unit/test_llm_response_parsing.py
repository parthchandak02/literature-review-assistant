"""
Unit tests for LLM response parsing edge cases.

Tests all failure modes: None parsed, plain text, malformed JSON, etc.
Uses recorded fixtures from actual production failures.
"""

import json
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.schemas.llm_response_schemas import ScreeningResultSchema, SchemaInclusionDecision
from src.screening.base_agent import BaseScreeningAgent, InclusionDecision
from src.screening.fulltext_agent import FullTextScreener
from src.screening.title_abstract_agent import TitleAbstractScreener
from tests.fixtures.llm_response_factory import LLMResponseFactory
from tests.fixtures.recorded_llm_responses import (
    PLAIN_TEXT_RESPONSE_PAPER4,
    MALFORMED_JSON_RESPONSE,
    TEXT_BEFORE_JSON,
    TEXT_AFTER_JSON,
    WRONG_SCHEMA_RESPONSE,
    WRONG_TYPE_RESPONSE,
    EMPTY_RESPONSE,
    WHITESPACE_ONLY_RESPONSE,
    MARKDOWN_WRAPPED_JSON,
    VALID_INCLUDE_RESPONSE,
    CONFIDENCE_OUT_OF_RANGE,
)


@pytest.mark.fast
@pytest.mark.unit
class TestLLMResponseParsing:
    """Test LLM response parsing handles all edge cases."""

    def test_response_parsed_returns_none(self, sample_agent_config):
        """Test handling when response.parsed returns None (CRITICAL)."""

        # Create minimal test agent
        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        # Mock response with parsed=None (the crash scenario)
        mock_response = LLMResponseFactory.plain_text_response(PLAIN_TEXT_RESPONSE_PAPER4)

        # Since the response is plain text, it can't be parsed as JSON
        # This should try manual parsing and raise ValidationError
        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            # Should handle None gracefully, attempt manual parsing, and raise for retry
            with pytest.raises(ValidationError):
                agent._call_llm_with_schema(
                    prompt="test prompt", response_model=ScreeningResultSchema
                )

    def test_valid_response_parsing(self, sample_agent_config):
        """Test that valid responses parse correctly."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        # Create valid schema object
        valid_schema = ScreeningResultSchema(
            decision=SchemaInclusionDecision.INCLUDE,
            confidence=0.95,
            reasoning="Valid response",
            exclusion_reason=None,
        )

        mock_response = LLMResponseFactory.valid_structured_response(valid_schema)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            result = agent._call_llm_with_schema(
                prompt="test", response_model=ScreeningResultSchema
            )

            assert result is not None
            assert result.decision == SchemaInclusionDecision.INCLUDE
            assert result.confidence == 0.95

    def test_malformed_json_handling(self, sample_agent_config):
        """Test malformed JSON is handled gracefully."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.malformed_json_response(MALFORMED_JSON_RESPONSE)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            # Should raise ValidationError to trigger retry
            with pytest.raises((ValidationError, json.JSONDecodeError)):
                agent._call_llm_with_schema(
                    prompt="test", response_model=ScreeningResultSchema
                )

    def test_empty_response_handling(self, sample_agent_config):
        """Test empty response doesn't crash."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.empty_response()

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            with pytest.raises((ValidationError, json.JSONDecodeError)):
                agent._call_llm_with_schema(
                    prompt="test", response_model=ScreeningResultSchema
                )


@pytest.mark.fast
@pytest.mark.unit
class TestFulltextAgentResponseHandling:
    """Test fulltext agent handles all response types."""

    def test_plain_text_fallback_parsing(self, sample_topic_context, sample_agent_config):
        """Test fallback to text parsing when structured output fails (CRITICAL)."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock _call_llm_with_schema to raise ValidationError
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = ValidationError("Schema validation failed", [])

            # Mock _call_llm to return plain text
            with patch.object(screener, "_call_llm") as mock_llm:
                mock_llm.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # Should fall back to text parsing and work
                result = screener.screen(
                    title="Test Paper",
                    abstract="Test abstract",
                    full_text="Test full text",
                    inclusion_criteria=["health science"],
                    exclusion_criteria=["general education"],
                )

                # Verify fallback worked
                assert result is not None
                assert result.decision is not None
                assert result.decision == InclusionDecision.EXCLUDE
                assert result.confidence >= 0.0
                assert "general education" in result.reasoning.lower()

    def test_convert_schema_to_result_with_none(self, sample_topic_context, sample_agent_config):
        """Test _convert_schema_to_result handles None gracefully (CRITICAL)."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Pass None to _convert_schema_to_result
        result = screener._convert_schema_to_result(None)

        # Should return UNCERTAIN, not crash
        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.3
        assert "parsing failed" in result.reasoning.lower()

    def test_screen_with_structured_output_failure_fallback(
        self, sample_topic_context, sample_agent_config
    ):
        """Test that screen method falls back when structured output fails."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock to simulate structured output failure
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            # First attempt fails
            mock_schema.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            # Mock text-based call
            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                # Verify fallback was used
                assert result is not None
                assert mock_text.called

    def test_screen_handles_various_malformed_responses(
        self, sample_topic_context, sample_agent_config
    ):
        """Test screen handles various malformed response types."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        malformed_responses = [
            MALFORMED_JSON_RESPONSE,
            EMPTY_RESPONSE,
            WHITESPACE_ONLY_RESPONSE,
        ]

        for malformed_response in malformed_responses:
            with patch.object(screener, "_call_llm_with_schema") as mock_schema:
                mock_schema.side_effect = ValidationError("Invalid", [])

                with patch.object(screener, "_call_llm") as mock_text:
                    # Even with malformed text, _parse_llm_response should handle it
                    mock_text.return_value = malformed_response

                    result = screener.screen(
                        title="Test",
                        abstract="Test",
                        full_text="Test",
                        inclusion_criteria=[],
                        exclusion_criteria=[],
                    )

                    # Should not crash, should return some result
                    assert result is not None
                    assert result.decision is not None


@pytest.mark.fast
@pytest.mark.unit
class TestTitleAbstractAgentResponseHandling:
    """Test title/abstract agent handles all response types."""

    def test_plain_text_fallback(self, sample_topic_context, sample_agent_config):
        """Test fallback to text parsing when structured output fails."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = ValidationError("Schema failed", [])

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result is not None
                assert result.decision == InclusionDecision.EXCLUDE

    def test_convert_schema_to_result_with_none(self, sample_topic_context, sample_agent_config):
        """Test _convert_schema_to_result handles None."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._convert_schema_to_result(None)

        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.3


@pytest.mark.fast
@pytest.mark.unit
class TestResponseParsingEdgeCases:
    """Test edge cases in response parsing."""

    def test_json_with_extra_text_before(self, sample_agent_config):
        """Test JSON extraction when text appears before JSON."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.response_with_extra_text(
            json_text=VALID_INCLUDE_RESPONSE,
            prefix="Here's my analysis:\n\n",
        )

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            # Should fail because parsed is None and manual parsing will fail
            # (text before JSON makes json.loads fail)
            with pytest.raises((ValidationError, json.JSONDecodeError)):
                agent._call_llm_with_schema(
                    prompt="test", response_model=ScreeningResultSchema
                )

    def test_markdown_wrapped_json(self, sample_agent_config):
        """Test JSON wrapped in markdown code blocks."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.plain_text_response(MARKDOWN_WRAPPED_JSON)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            # Should fail and trigger retry
            with pytest.raises((ValidationError, json.JSONDecodeError)):
                agent._call_llm_with_schema(
                    prompt="test", response_model=ScreeningResultSchema
                )

    def test_confidence_out_of_range(self, sample_agent_config):
        """Test handling of confidence values outside valid range."""

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.plain_text_response(CONFIDENCE_OUT_OF_RANGE)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            # Pydantic should reject confidence > 1.0
            with pytest.raises(ValidationError):
                agent._call_llm_with_schema(
                    prompt="test", response_model=ScreeningResultSchema
                )


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.regression
class TestHistoricalFailures:
    """Test specific responses that caused production crashes."""

    def test_paper4_crash_scenario(self, sample_topic_context, sample_agent_config):
        """
        Test the exact scenario that caused the crash on 2026-02-07.
        
        Paper: "Conversational AI as an Intelligent Tutor"
        Issue: LLM returned plain text instead of JSON
        Result: AttributeError when accessing schema_result.decision
        """
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock the exact failure scenario
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            # Simulate ValidationError after retries exhausted
            mock_schema.side_effect = ValidationError("All retries failed", [])

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # This MUST NOT crash
                result = screener.screen(
                    title="Conversational AI as an Intelligent Tutor: A Review of Dialogue-Based Learning Systems",
                    abstract="",
                    full_text="International Journal of Science...",
                    inclusion_criteria=["health science education"],
                    exclusion_criteria=["general education"],
                )

                # Verify it worked
                assert result is not None
                assert result.decision == InclusionDecision.EXCLUDE
                assert result.confidence > 0.0
                assert "general education" in result.reasoning.lower()

    def test_null_schema_result_doesnt_crash(self, sample_topic_context, sample_agent_config):
        """Test that None schema_result returns UNCERTAIN instead of crashing."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Directly test the conversion method with None
        result = screener._convert_schema_to_result(None)

        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.3
        assert "parsing failed" in result.reasoning


@pytest.mark.fast
@pytest.mark.unit
class TestParseMethodResilience:
    """Test that _parse_llm_response handles various formats."""

    def test_parse_plain_text_response(self, sample_topic_context, sample_agent_config):
        """Test parsing of plain text (non-JSON) responses."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._parse_llm_response(PLAIN_TEXT_RESPONSE_PAPER4)

        assert result is not None
        assert result.decision == InclusionDecision.EXCLUDE
        assert result.confidence == 0.9
        assert "general education" in result.reasoning.lower()

    def test_parse_empty_response(self, sample_topic_context, sample_agent_config):
        """Test parsing empty response defaults to UNCERTAIN."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._parse_llm_response(EMPTY_RESPONSE)

        # Should default to UNCERTAIN
        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN

    def test_parse_whitespace_only(self, sample_topic_context, sample_agent_config):
        """Test parsing whitespace-only response."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._parse_llm_response(WHITESPACE_ONLY_RESPONSE)

        assert result is not None
        assert result.decision == InclusionDecision.UNCERTAIN


@pytest.mark.fast
@pytest.mark.unit
class TestLLMResponseFactory:
    """Test the response factory itself."""

    def test_factory_creates_plain_text_response(self):
        """Test factory creates correct plain text response."""
        response = LLMResponseFactory.plain_text_response("Test text")

        assert response.content == "Test text"
        assert response.parsed is None
        assert response.usage.total_tokens == 150

    def test_factory_creates_valid_structured_response(self):
        """Test factory creates valid structured response."""
        schema = ScreeningResultSchema(
            decision=SchemaInclusionDecision.INCLUDE,
            confidence=0.9,
            reasoning="Test",
            exclusion_reason=None,
        )

        response = LLMResponseFactory.valid_structured_response(schema)

        assert response.parsed == schema
        assert response.content is not None
        assert "include" in response.content.lower()

    def test_factory_creates_empty_response(self):
        """Test factory creates empty response."""
        response = LLMResponseFactory.empty_response()

        assert response.content == ""
        assert response.parsed is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
