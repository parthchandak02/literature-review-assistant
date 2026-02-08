"""
Integration tests using recorded LLM responses.

These tests use actual problematic responses that crashed the system,
recorded as fixtures for zero-cost, deterministic testing.
"""

import pytest
from unittest.mock import patch, Mock

from src.screening.fulltext_agent import FullTextScreener
from src.screening.title_abstract_agent import TitleAbstractScreener
from src.screening.base_agent import InclusionDecision
from tests.fixtures.recorded_llm_responses import (
    PLAIN_TEXT_RESPONSE_PAPER4,
    MALFORMED_JSON_RESPONSE,
    TEXT_BEFORE_JSON,
    TEXT_AFTER_JSON,
    WRONG_SCHEMA_RESPONSE,
    EMPTY_RESPONSE,
    WHITESPACE_ONLY_RESPONSE,
    MARKDOWN_WRAPPED_JSON,
    VALID_INCLUDE_RESPONSE,
    VALID_EXCLUDE_RESPONSE,
    VALID_UNCERTAIN_RESPONSE,
)
from tests.fixtures.llm_response_factory import LLMResponseFactory


@pytest.mark.integration
@pytest.mark.regression
class TestScreeningWithRecordedResponses:
    """Test screening with actual problematic responses that crashed the system."""

    def test_paper4_plain_text_response(self, sample_topic_context, sample_agent_config):
        """
        Test the exact response that caused the crash (Paper 4).
        
        Date: 2026-02-07
        Paper: "Conversational AI as an Intelligent Tutor"
        Issue: LLM returned plain text, response.parsed = None, AttributeError
        """
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock to return the problematic plain text response
        mock_response = LLMResponseFactory.plain_text_response(PLAIN_TEXT_RESPONSE_PAPER4)

        with patch.object(screener, "_make_llm_call") as mock:
            # First call fails (structured output), second succeeds (text)
            mock.return_value = mock_response

            # Mock the fallback to text parsing
            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # Should NOT crash, should handle gracefully
                result = screener.screen(
                    title="Conversational AI as an Intelligent Tutor",
                    abstract="A review of dialogue-based learning systems",
                    full_text="International Journal of Science...",
                    inclusion_criteria=["health science education"],
                    exclusion_criteria=["general education"],
                )

                # Should fall back to text parsing and work
                assert result is not None
                assert result.decision == InclusionDecision.EXCLUDE
                assert result.confidence >= 0.0
                assert "general education" in result.reasoning.lower()

    def test_malformed_json_response(self, sample_topic_context, sample_agent_config):
        """Test handling of malformed JSON response."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            # Structured parsing fails
            mock_schema.side_effect = Exception("Malformed JSON")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = MALFORMED_JSON_RESPONSE

                # Should not crash, should handle gracefully
                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result is not None
                assert result.decision is not None

    def test_empty_response_handling(self, sample_topic_context, sample_agent_config):
        """Test handling of empty LLM response."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Empty response")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = EMPTY_RESPONSE

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                # Should default to UNCERTAIN
                assert result is not None
                assert result.decision == InclusionDecision.UNCERTAIN

    def test_whitespace_only_response(self, sample_topic_context, sample_agent_config):
        """Test handling of whitespace-only response."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Whitespace only")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = WHITESPACE_ONLY_RESPONSE

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result is not None
                assert result.decision == InclusionDecision.UNCERTAIN

    def test_markdown_wrapped_json(self, sample_topic_context, sample_agent_config):
        """Test handling of JSON wrapped in markdown code blocks."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Markdown wrapped")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = MARKDOWN_WRAPPED_JSON

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                # Should handle gracefully
                assert result is not None
                assert result.decision is not None

    def test_title_abstract_agent_with_problematic_responses(
        self, sample_topic_context, sample_agent_config
    ):
        """Test title/abstract agent handles problematic responses."""
        screener = TitleAbstractScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Test with plain text response
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Schema failed")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                result = screener.screen(
                    title="Test Paper",
                    abstract="Test abstract",
                    inclusion_criteria=["health"],
                    exclusion_criteria=["general"],
                )

                assert result is not None
                assert result.decision == InclusionDecision.EXCLUDE

    def test_all_recorded_failure_modes(self, sample_topic_context, sample_agent_config):
        """Test all recorded failure modes don't crash."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        problematic_responses = [
            PLAIN_TEXT_RESPONSE_PAPER4,
            MALFORMED_JSON_RESPONSE,
            TEXT_BEFORE_JSON,
            TEXT_AFTER_JSON,
            WRONG_SCHEMA_RESPONSE,
            EMPTY_RESPONSE,
            WHITESPACE_ONLY_RESPONSE,
            MARKDOWN_WRAPPED_JSON,
        ]

        for response_text in problematic_responses:
            with patch.object(screener, "_call_llm_with_schema") as mock_schema:
                mock_schema.side_effect = Exception("Failure")

                with patch.object(screener, "_call_llm") as mock_text:
                    mock_text.return_value = response_text

                    # None of these should crash
                    result = screener.screen(
                        title="Test",
                        abstract="Test",
                        full_text="Test",
                        inclusion_criteria=[],
                        exclusion_criteria=[],
                    )

                    assert result is not None, f"Failed for response: {response_text[:50]}"
                    assert result.decision is not None


@pytest.mark.integration
@pytest.mark.fast
class TestValidResponseHandling:
    """Test that valid responses still work correctly."""

    def test_valid_include_response(self, sample_topic_context, sample_agent_config):
        """Test valid INCLUDE response is handled correctly."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Force fallback")

            with patch.object(screener, "_call_llm") as mock_text:
                # Extract JSON from the fixture
                import json
                response_dict = json.loads(VALID_INCLUDE_RESPONSE)
                formatted_response = f"""DECISION: {response_dict['decision']}
CONFIDENCE: {response_dict['confidence']}
REASONING: {response_dict['reasoning']}"""
                mock_text.return_value = formatted_response

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result.decision == InclusionDecision.INCLUDE
                assert result.confidence == 0.95

    def test_valid_exclude_response(self, sample_topic_context, sample_agent_config):
        """Test valid EXCLUDE response is handled correctly."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Force fallback")

            with patch.object(screener, "_call_llm") as mock_text:
                import json
                response_dict = json.loads(VALID_EXCLUDE_RESPONSE)
                formatted_response = f"""DECISION: {response_dict['decision']}
CONFIDENCE: {response_dict['confidence']}
REASONING: {response_dict['reasoning']}
EXCLUSION_REASON: {response_dict['exclusion_reason']}"""
                mock_text.return_value = formatted_response

                result = screener.screen(
                    title="Test",
                    abstract="Test",
                    full_text="Test",
                    inclusion_criteria=[],
                    exclusion_criteria=[],
                )

                assert result.decision == InclusionDecision.EXCLUDE
                assert result.confidence == 0.9
                assert result.exclusion_reason is not None


@pytest.mark.integration
class TestScreeningResilience:
    """Test screening resilience with multiple papers."""

    def test_mixed_response_types(self, sample_topic_context, sample_agent_config):
        """Test screening handles mixed response types in sequence."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        responses = [
            PLAIN_TEXT_RESPONSE_PAPER4,  # Plain text
            MALFORMED_JSON_RESPONSE,      # Malformed
            EMPTY_RESPONSE,               # Empty
            PLAIN_TEXT_RESPONSE_PAPER4,  # Plain text again
        ]

        results = []
        for response_text in responses:
            with patch.object(screener, "_call_llm_with_schema") as mock_schema:
                mock_schema.side_effect = Exception("Failure")

                with patch.object(screener, "_call_llm") as mock_text:
                    mock_text.return_value = response_text

                    result = screener.screen(
                        title="Test",
                        abstract="Test",
                        full_text="Test",
                        inclusion_criteria=[],
                        exclusion_criteria=[],
                    )
                    results.append(result)

        # All results should be valid
        assert all(r is not None for r in results)
        assert all(r.decision is not None for r in results)
        assert len(results) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
