"""
Unit tests for fulltext screening agent.
"""

from unittest.mock import Mock, patch
import json
import pytest
from pydantic import ValidationError

from src.screening.base_agent import InclusionDecision
from src.screening.fulltext_agent import FullTextScreener
from tests.fixtures.recorded_llm_responses import PLAIN_TEXT_RESPONSE_PAPER4
from tests.fixtures.llm_response_factory import LLMResponseFactory


class TestFullTextScreener:
    """Test FullTextScreener agent."""

    def test_fulltext_screener_initialization(self, sample_topic_context, sample_agent_config):
        """Test FullTextScreener initialization."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert screener.llm_provider == "openai"
        assert screener.topic_context is not None

    @patch("src.screening.base_agent.openai")
    def test_screen_with_fulltext(self, mock_openai, sample_topic_context, sample_agent_config):
        """Test screening with full text."""
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = """DECISION: INCLUDE
CONFIDENCE: 0.9
REASONING: Paper meets all inclusion criteria
EXCLUSION_REASON: None"""
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 300
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener.screen(
            title="Test Paper",
            abstract="Test abstract",
            full_text="This is the full text content of the paper...",
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
        )

        assert result.decision in [
            InclusionDecision.INCLUDE,
            InclusionDecision.EXCLUDE,
            InclusionDecision.UNCERTAIN,
        ]
        assert 0.0 <= result.confidence <= 1.0
        assert result.reasoning is not None

    def test_screen_without_fulltext(self, sample_topic_context, sample_agent_config):
        """Test screening without full text (falls back to title/abstract)."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key=None,  # No API key triggers fallback
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener.screen(
            title="Test Paper",
            abstract="Test abstract about telemedicine UX",
            full_text=None,
            inclusion_criteria=["Telemedicine", "UX"],
            exclusion_criteria=["Technical only"],
        )

        assert result.decision is not None
        assert result.confidence >= 0.0

    def test_screen_fallback(self, sample_topic_context, sample_agent_config):
        """Test screening with fallback (no LLM)."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener.screen(
            title="Telemedicine UX Design",
            abstract="User experience in telemedicine platforms",
            full_text="Full text about telemedicine and user experience design...",
            inclusion_criteria=["Telemedicine", "UX"],
            exclusion_criteria=["Technical only"],
        )

        assert result.decision is not None
        assert result.confidence >= 0.0
        assert result.reasoning is not None

    def test_build_fulltext_prompt(self, sample_topic_context, sample_agent_config):
        """Test fulltext prompt building."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        prompt = screener._build_fulltext_prompt(
            title="Test Paper",
            abstract="Test abstract",
            full_text="This is the full text content...",
            inclusion_criteria=["Criterion 1", "Criterion 2"],
            exclusion_criteria=["Exclusion 1"],
        )

        assert "Test Paper" in prompt
        assert "Test abstract" in prompt
        assert "Criterion 1" in prompt
        assert "Exclusion 1" in prompt
        assert "FULL TEXT" in prompt

    def test_build_fulltext_prompt_truncation(self, sample_topic_context, sample_agent_config):
        """Test fulltext prompt truncation for long text."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        long_text = "A" * 10000  # Very long text
        prompt = screener._build_fulltext_prompt(
            title="Test",
            abstract="Test",
            full_text=long_text,
            inclusion_criteria=[],
            exclusion_criteria=[],
        )

        # Should be truncated
        assert len(prompt) < len(long_text) + 1000
        assert "[truncated]" in prompt

    def test_parse_llm_response(self, sample_topic_context, sample_agent_config):
        """Test parsing LLM response."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        response = """DECISION: INCLUDE
CONFIDENCE: 0.85
REASONING: Paper meets inclusion criteria
EXCLUSION_REASON: None"""

        result = screener._parse_llm_response(response)

        assert result.decision == InclusionDecision.INCLUDE
        assert result.confidence == 0.85
        assert "meets inclusion criteria" in result.reasoning

    def test_parse_llm_response_exclude(self, sample_topic_context, sample_agent_config):
        """Test parsing LLM response with exclude decision."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        response = """DECISION: EXCLUDE
CONFIDENCE: 0.8
REASONING: Does not meet criteria
EXCLUSION_REASON: Editorial piece"""

        result = screener._parse_llm_response(response)

        assert result.decision == InclusionDecision.EXCLUDE
        assert result.confidence == 0.8
        assert result.exclusion_reason == "Editorial piece"

    def test_parse_llm_response_uncertain(self, sample_topic_context, sample_agent_config):
        """Test parsing LLM response with uncertain decision."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        response = """DECISION: UNCERTAIN
CONFIDENCE: 0.5
REASONING: Unclear if meets criteria"""

        result = screener._parse_llm_response(response)

        assert result.decision == InclusionDecision.UNCERTAIN
        assert result.confidence == 0.5

    def test_fallback_screen_exclusion(self, sample_topic_context, sample_agent_config):
        """Test fallback screening with exclusion."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._fallback_screen(
            title="Test Paper",
            abstract="This is an editorial piece about the topic",
            full_text="Editorial content...",
            inclusion_criteria=["Research study"],
            exclusion_criteria=["Editorial piece"],
        )

        assert result.decision == InclusionDecision.EXCLUDE
        assert result.exclusion_reason is not None

    def test_fallback_screen_inclusion(self, sample_topic_context, sample_agent_config):
        """Test fallback screening with inclusion."""
        screener = FullTextScreener(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = screener._fallback_screen(
            title="Telemedicine UX Research Study",
            abstract="A research study about telemedicine and user experience design",
            full_text="This research study examines telemedicine platforms and user experience...",
            inclusion_criteria=["Telemedicine", "Research study"],
            exclusion_criteria=["Editorial"],
        )

        # Should include if matches enough inclusion criteria
        assert result.decision in [InclusionDecision.INCLUDE, InclusionDecision.EXCLUDE]

    @pytest.mark.fast
    @pytest.mark.regression
    def test_convert_schema_to_result_with_none(self, sample_topic_context, sample_agent_config):
        """Test _convert_schema_to_result handles None gracefully (NEW)."""
        screener = FullTextScreener(
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
        """Test schema failure routes to UNCERTAIN manual review (NEW behavior)."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock structured output to fail
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            mock_schema.side_effect = ValidationError("Schema validation failed", [])

            result = screener.screen(
                title="Test Paper",
                abstract="Test abstract",
                full_text="Test full text",
                inclusion_criteria=["health science"],
                exclusion_criteria=["general education"],
            )

            assert result is not None
            assert result.decision == InclusionDecision.UNCERTAIN
            assert result.confidence == 0.0
            assert "manual" in result.reasoning.lower()

    @pytest.mark.fast
    @pytest.mark.regression
    def test_screen_handles_plain_text_response(self, sample_topic_context, sample_agent_config):
        """Test schema failure never crashes and returns UNCERTAIN."""
        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Simulate the exact Paper 4 crash scenario
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            # Structured output fails completely
            mock_schema.side_effect = Exception("response.parsed is None")

            # This MUST NOT crash
            result = screener.screen(
                title="Conversational AI as an Intelligent Tutor",
                abstract="A review of dialogue-based learning systems",
                full_text="Full text content...",
                inclusion_criteria=["health science education"],
                exclusion_criteria=["general education"],
            )

            assert result is not None
            assert result.decision == InclusionDecision.UNCERTAIN
            assert result.confidence == 0.0
            assert isinstance(result.reasoning, str)
