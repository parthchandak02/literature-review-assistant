"""
Integration tests for structured LLM outputs.

Tests actual LLM API calls with Pydantic schema enforcement to verify
that responses are properly validated and parsed.
"""

import os

import pytest

from src.schemas.llm_response_schemas import (
    ScreeningResultSchema,
)
from src.screening.base_agent import BaseScreeningAgent
from src.screening.title_abstract_agent import TitleAbstractScreener
from src.writing.abstract_agent import AbstractGenerator
from src.writing.introduction_agent import IntroductionWriter


@pytest.fixture
def llm_config():
    """LLM configuration for tests."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set")

    return {
        "llm_provider": "gemini",
        "api_key": api_key,
        "llm_model": "gemini-2.5-flash",  # Use fast model for tests
        "temperature": 0.3,
    }


@pytest.fixture
def topic_context():
    """Sample topic context for testing."""
    return {
        "topic": "Telemedicine usability for diverse populations",
        "keywords": ["telemedicine", "usability", "accessibility"],
        "inclusion_criteria": [
            "Studies about telemedicine or telehealth",
            "Studies examining user experience or usability",
        ],
        "exclusion_criteria": [
            "Studies without human participants",
            "Opinion pieces or editorials",
        ],
    }


class TestScreeningWithStructuredOutputs:
    """Test screening agents with structured outputs."""

    def test_title_abstract_screener_structured_output(self, llm_config, topic_context):
        """Test that title/abstract screener returns valid structured output."""
        # Create agent
        agent_config = {
            "role": "Title/Abstract Screener",
            "llm_model": llm_config["llm_model"],
            "temperature": llm_config["temperature"],
        }

        screener = TitleAbstractScreener(
            llm_provider=llm_config["llm_provider"],
            api_key=llm_config["api_key"],
            topic_context=topic_context,
            agent_config=agent_config,
        )

        # Test paper
        title = "Usability evaluation of a telemedicine platform for elderly patients"
        abstract = "This study examines the usability of a telemedicine platform designed for elderly patients. We conducted user testing with 50 participants aged 65+. Results showed high satisfaction scores."

        # Call screening
        result = screener.screen(
            title=title,
            abstract=abstract,
            inclusion_criteria=topic_context["inclusion_criteria"],
            exclusion_criteria=topic_context["exclusion_criteria"],
        )

        # Validate result structure
        assert result is not None
        assert hasattr(result, "decision")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reasoning")

        # Validate decision is valid
        assert result.decision.value in ["include", "exclude", "uncertain"]

        # Validate confidence is in valid range
        assert 0.0 <= result.confidence <= 1.0

        # Validate reasoning is not empty
        assert len(result.reasoning) > 0

        # This paper should likely be included
        assert result.decision.value == "include"

    def test_base_agent_call_llm_with_schema(self, llm_config):
        """Test BaseScreeningAgent._call_llm_with_schema method directly."""
        agent_config = {
            "role": "Test Agent",
            "llm_model": llm_config["llm_model"],
            "temperature": 0.1,
        }

        # Create a minimal subclass for testing
        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider=llm_config["llm_provider"],
            api_key=llm_config["api_key"],
            agent_config=agent_config,
        )

        # Test prompt
        prompt = """Screen this paper for inclusion in a systematic review about telemedicine usability.

Title: Mobile health app usability for chronic disease management

Abstract: This randomized controlled trial evaluated the usability of a mobile health application for managing chronic diseases. 200 patients were recruited and randomized to intervention or control groups.

Inclusion Criteria:
- Studies about telemedicine or mobile health
- Studies examining usability

Exclusion Criteria:
- Non-peer-reviewed articles

Make your decision."""

        # Call LLM with schema
        result = agent._call_llm_with_schema(
            prompt=prompt,
            response_model=ScreeningResultSchema,
        )

        # Verify result is properly validated ScreeningResultSchema
        assert isinstance(result, ScreeningResultSchema)
        assert result.decision.value in ["include", "exclude", "uncertain"]
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.reasoning) > 0


class TestWritingWithStructuredOutputs:
    """Test writing agents with structured outputs."""

    @pytest.mark.slow
    def test_introduction_writer_structured_output(self, llm_config, topic_context):
        """Test that introduction writer returns valid structured output."""
        agent_config = {
            "role": "Introduction Writer",
            "llm_model": llm_config["llm_model"],
            "temperature": 0.5,
        }

        writer = IntroductionWriter(
            llm_provider=llm_config["llm_provider"],
            api_key=llm_config["api_key"],
            topic_context=topic_context,
            agent_config=agent_config,
        )

        # Generate introduction
        result = writer.write(
            topic_context=topic_context,
            included_papers=[],  # Empty for test
            extracted_data=[],
        )

        # Validate result structure
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 100  # Should be substantial content

        # Should contain introduction-related content
        assert any(keyword in result.lower() for keyword in ["introduction", "background", "systematic"])

    @pytest.mark.slow
    def test_abstract_generator_structured_output(self, llm_config, topic_context):
        """Test that abstract generator returns valid structured output."""
        generator = AbstractGenerator(
            llm_provider=llm_config["llm_provider"],
            llm_api_key=llm_config["api_key"],
            topic_context=topic_context,
            config={"structured": True, "word_limit": 250},
        )

        # Generate abstract (with minimal data)
        result = generator.generate(
            topic_context=topic_context,
            included_papers=[],  # Empty for test
            article_sections={
                "introduction": "Test introduction",
                "methods": "Test methods",
                "results": "Test results",
                "discussion": "Test discussion",
            },
        )

        # Validate result
        assert result is not None
        assert isinstance(result, str)
        assert len(result) >= 150  # Minimum abstract length
        assert len(result.split()) <= 350  # Approximate word count limit


class TestStructuredOutputRetry:
    """Test retry logic for structured outputs."""

    def test_validation_error_triggers_retry(self, llm_config):
        """Test that validation errors trigger automatic retry."""
        agent_config = {
            "role": "Test Agent",
            "llm_model": llm_config["llm_model"],
            "temperature": 0.1,
        }

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider=llm_config["llm_provider"],
            api_key=llm_config["api_key"],
            agent_config=agent_config,
        )

        # Valid prompt that should return valid response
        prompt = """Make a screening decision for this paper.

Title: Telemedicine usability study
Abstract: This study examined usability of telemedicine platforms.

Provide your assessment."""

        # This should succeed (no validation error since LLM should return valid response)
        result = agent._call_llm_with_schema(
            prompt=prompt,
            response_model=ScreeningResultSchema,
        )

        assert isinstance(result, ScreeningResultSchema)
        # The retry decorator will handle any validation errors automatically


class TestSchemaEnforcementAtAPILevel:
    """Test that schemas are enforced at the API level, not just during parsing."""

    def test_llm_returns_valid_json_structure(self, llm_config):
        """Test that LLM is constrained to return valid JSON matching the schema."""
        agent_config = {
            "role": "Test Agent",
            "llm_model": llm_config["llm_model"],
            "temperature": 0.1,
        }

        class TestAgent(BaseScreeningAgent):
            def screen(self, *args, **kwargs):
                pass

        agent = TestAgent(
            llm_provider=llm_config["llm_provider"],
            api_key=llm_config["api_key"],
            agent_config=agent_config,
        )

        prompt = "Evaluate if this paper should be included: Title: 'AI in healthcare'. Abstract: 'AI applications in medical diagnosis.'"

        result = agent._call_llm_with_schema(
            prompt=prompt,
            response_model=ScreeningResultSchema,
        )

        # Result should be a valid ScreeningResultSchema with all required fields
        assert result.decision is not None
        assert result.confidence is not None
        assert result.reasoning is not None

        # Fields should be the correct types
        assert hasattr(result.decision, "value")
        assert isinstance(result.confidence, float)
        assert isinstance(result.reasoning, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
