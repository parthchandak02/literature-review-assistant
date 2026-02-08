"""
Factory for creating mock LLM responses for testing.

This factory creates mock response objects that match the structure of actual
LLM API responses (Gemini, OpenAI, etc.) for deterministic testing.
"""

from typing import Any, Optional
from unittest.mock import Mock


class LLMResponseFactory:
    """Create mock LLM response objects for testing."""

    @staticmethod
    def create_response(
        content: str,
        parsed: Optional[Any] = None,
        usage_tokens: int = 150,
        model: str = "gemini-2.5-flash-lite",
    ) -> Mock:
        """
        Create a mock response object matching Gemini API structure.

        Args:
            content: The raw text content from the LLM
            parsed: The parsed Pydantic object (None if parsing failed)
            usage_tokens: Total token count for the response
            model: Model name that generated the response

        Returns:
            Mock object matching LLM API response structure
        """
        mock_response = Mock()
        mock_response.content = content
        mock_response.parsed = parsed
        mock_response.model = model

        # Usage tracking (matches real API structure)
        mock_usage = Mock()
        mock_usage.prompt_tokens = int(usage_tokens * 0.67)  # ~67% for prompt
        mock_usage.completion_tokens = int(usage_tokens * 0.33)  # ~33% for completion
        mock_usage.total_tokens = usage_tokens
        mock_response.usage = mock_usage

        # Additional metadata
        mock_response.finish_reason = "stop"
        mock_response.safety_ratings = []

        return mock_response

    @classmethod
    def plain_text_response(cls, text: str, model: str = "gemini-2.5-flash-lite") -> Mock:
        """
        Create response with plain text (parsed=None).
        Simulates when LLM ignores JSON instruction and returns plain text.
        """
        return cls.create_response(content=text, parsed=None, model=model)

    @classmethod
    def malformed_json_response(cls, json_text: str) -> Mock:
        """
        Create response with malformed JSON.
        Simulates JSON syntax errors from LLM.
        """
        return cls.create_response(content=json_text, parsed=None)

    @classmethod
    def valid_structured_response(cls, schema_obj: Any, model: str = "gemini-2.5-flash-lite") -> Mock:
        """
        Create response with valid Pydantic object.
        Simulates successful structured output.

        Args:
            schema_obj: A validated Pydantic model instance
            model: Model name

        Returns:
            Mock response with both content (JSON string) and parsed (Pydantic object)
        """
        import json

        content = json.dumps(schema_obj.model_dump())
        return cls.create_response(content=content, parsed=schema_obj, model=model)

    @classmethod
    def response_with_extra_text(cls, json_text: str, prefix: str = "", suffix: str = "") -> Mock:
        """
        Create response with extra text before/after JSON.
        Simulates when LLM adds explanatory text around the JSON.
        """
        content = f"{prefix}{json_text}{suffix}"
        return cls.create_response(content=content, parsed=None)

    @classmethod
    def empty_response(cls) -> Mock:
        """Create empty response (edge case)."""
        return cls.create_response(content="", parsed=None)

    @classmethod
    def whitespace_only_response(cls) -> Mock:
        """Create response with only whitespace."""
        return cls.create_response(content="   \n\n   ", parsed=None)


class OpenAIMockFactory:
    """Factory for creating OpenAI-style mock responses."""

    @staticmethod
    def create_openai_response(content: str, model: str = "gpt-4o") -> Mock:
        """Create mock OpenAI response."""
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = content
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        # Usage
        mock_usage = Mock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150
        mock_response.usage = mock_usage

        mock_response.model = model
        return mock_response


class GeminiMockFactory:
    """Factory for creating Gemini-style mock responses with candidates structure."""

    @staticmethod
    def create_gemini_response(
        content: str,
        parsed: Optional[Any] = None,
        finish_reason: str = "STOP",
    ) -> Mock:
        """
        Create mock Gemini response matching actual API structure.

        Gemini responses have a 'candidates' list structure.
        """
        mock_response = Mock()

        # Create candidate
        mock_candidate = Mock()
        mock_candidate.content = Mock()
        mock_candidate.content.parts = [Mock(text=content)]
        mock_candidate.finish_reason = finish_reason

        mock_response.candidates = [mock_candidate]
        mock_response.text = content
        mock_response.parsed = parsed

        # Usage info
        mock_usage = Mock()
        mock_usage.prompt_token_count = 100
        mock_usage.candidates_token_count = 50
        mock_usage.total_token_count = 150
        mock_response.usage_metadata = mock_usage

        return mock_response
