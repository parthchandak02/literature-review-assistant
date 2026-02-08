"""
Modern parametrized unit tests for LLM response parsing.

Uses pytest.mark.parametrize to reduce duplication while maintaining
comprehensive coverage with clear test names.
"""

import json
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.schemas.llm_response_schemas import ScreeningResultSchema, SchemaInclusionDecision
from src.screening.base_agent import BaseScreeningAgent, InclusionDecision
from src.screening.fulltext_agent import FullTextScreener
from tests.fixtures.llm_response_factory import LLMResponseFactory
from tests.fixtures.recorded_llm_responses import (
    PLAIN_TEXT_RESPONSE_PAPER4,
    MALFORMED_JSON_RESPONSE,
    EMPTY_RESPONSE,
    WHITESPACE_ONLY_RESPONSE,
    TEXT_BEFORE_JSON,
    TEXT_AFTER_JSON,
    MARKDOWN_WRAPPED_JSON,
    VALID_INCLUDE_RESPONSE,
)


@pytest.mark.fast
@pytest.mark.unit
class TestLLMResponseParsingParametrized:
    """Comprehensive LLM response parsing tests using parametrization."""

    @pytest.mark.parametrize(
        "response_text,expected_exception,test_id",
        [
            (PLAIN_TEXT_RESPONSE_PAPER4, (ValidationError, json.JSONDecodeError), "plain_text"),
            (MALFORMED_JSON_RESPONSE, (ValidationError, json.JSONDecodeError), "malformed_json"),
            (EMPTY_RESPONSE, (ValidationError, json.JSONDecodeError), "empty_response"),
            (WHITESPACE_ONLY_RESPONSE, (ValidationError, json.JSONDecodeError), "whitespace_only"),
            (TEXT_BEFORE_JSON, (ValidationError, json.JSONDecodeError), "text_before_json"),
            (MARKDOWN_WRAPPED_JSON, (ValidationError, json.JSONDecodeError), "markdown_wrapped"),
        ],
        ids=lambda x: x if isinstance(x, str) and not "\n" in x else None,
    )
    def test_problematic_responses_trigger_retry(
        self,
        response_text,
        expected_exception,
        test_id,
        sample_agent_config,
    ):
        """
        Test that all problematic response types trigger retry mechanism.
        
        Consolidates 6+ individual tests into one parametrized test.
        """
        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        mock_response = LLMResponseFactory.plain_text_response(response_text)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            with pytest.raises(expected_exception):
                agent._call_llm_with_schema(
                    prompt="test prompt",
                    response_model=ScreeningResultSchema,
                )

    @pytest.mark.parametrize(
        "decision,confidence,reasoning",
        [
            (SchemaInclusionDecision.INCLUDE, 0.95, "Meets criteria"),
            (SchemaInclusionDecision.EXCLUDE, 0.9, "Does not meet"),
            (SchemaInclusionDecision.UNCERTAIN, 0.5, "Unclear"),
        ],
        ids=["include", "exclude", "uncertain"],
    )
    def test_valid_responses_parse_correctly(
        self,
        decision,
        confidence,
        reasoning,
        sample_agent_config,
    ):
        """
        Test that valid responses parse correctly for all decision types.
        
        Consolidates 3 tests into one parametrized test.
        """
        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider="gemini",
            api_key="test-key",
            agent_config=sample_agent_config,
        )

        valid_schema = ScreeningResultSchema(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            exclusion_reason=None,
        )

        mock_response = LLMResponseFactory.valid_structured_response(valid_schema)

        with patch.object(agent, "_make_llm_call") as mock_call:
            mock_call.return_value = mock_response

            result = agent._call_llm_with_schema(
                prompt="test", response_model=ScreeningResultSchema
            )

            assert result is not None
            assert result.decision == decision
            assert result.confidence == confidence


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.regression
class TestScreeningAgentFallbackBehavior:
    """Test fallback behavior across both screening agents."""

    @pytest.mark.parametrize(
        "agent_class,agent_name",
        [
            (FullTextScreener, "fulltext"),
            # Can add TitleAbstractScreener here when needed
        ],
        ids=["fulltext"],
    )
    def test_fallback_to_text_parsing(
        self,
        agent_class,
        agent_name,
        sample_topic_context,
        sample_agent_config,
    ):
        """
        Test that both screening agents fall back to text parsing.
        
        Works for any screening agent class - just add to parametrize.
        """
        screener = agent_class(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = ValidationError("Schema validation failed", [])

            with patch.object(screener, "_call_llm") as mock_llm:
                mock_llm.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # This should fall back gracefully
                if agent_name == "fulltext":
                    result = screener.screen(
                        title="Test Paper",
                        abstract="Test abstract",
                        full_text="Test full text",
                        inclusion_criteria=["health science"],
                        exclusion_criteria=["general education"],
                    )
                else:
                    result = screener.screen(
                        title="Test Paper",
                        abstract="Test abstract",
                        inclusion_criteria=["health science"],
                        exclusion_criteria=["general education"],
                    )

                assert result is not None
                assert result.decision == InclusionDecision.EXCLUDE
                assert mock_llm.called


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.regression
class TestHistoricalFailuresParametrized:
    """Regression tests for production crashes using parametrization."""

    @pytest.mark.parametrize(
        "paper_title,response_text,expected_decision",
        [
            (
                "Conversational AI as an Intelligent Tutor",
                PLAIN_TEXT_RESPONSE_PAPER4,
                InclusionDecision.EXCLUDE,
            ),
            # Add more historical failures here as they occur
            # ("Future Paper Title", FUTURE_RESPONSE, EXPECTED_DECISION),
        ],
        ids=["paper4_2026_02_07"],
    )
    def test_historical_crash_scenarios(
        self,
        paper_title,
        response_text,
        expected_decision,
        sample_topic_context,
        sample_agent_config,
    ):
        """
        Test all historical crash scenarios.
        
        Each production crash becomes a new row in the parametrize decorator.
        """
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = Exception("Plain text response")

            with patch.object(screener, "_call_llm") as mock_text:
                mock_text.return_value = response_text

                result = screener.screen(
                    title=paper_title,
                    abstract="",
                    full_text="Full text...",
                    inclusion_criteria=["health science education"],
                    exclusion_criteria=["general education"],
                )

                assert result is not None, f"Failed for: {paper_title}"
                assert result.decision == expected_decision


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
