"""Backward-compatibility shim: GeminiClient -> PydanticAIClient.

All callers that previously imported GeminiClient will transparently use
PydanticAIClient, which supports Gemini and all other PydanticAI providers.
"""

from src.llm.pydantic_client import PydanticAIClient

GeminiClient = PydanticAIClient

__all__ = ["GeminiClient"]
