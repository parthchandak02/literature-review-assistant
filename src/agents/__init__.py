"""
Agent Base Classes

Base classes for all LLM-powered agents in the system.
"""

from .base_llm_agent import BaseLLMAgent
from .base_writing_agent import BaseWritingAgent

__all__ = [
    "BaseLLMAgent",
    "BaseWritingAgent",
]
