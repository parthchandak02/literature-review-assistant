"""
Base Writing Agent

Base class for all manuscript writing agents.
"""

from abc import abstractmethod
from typing import Any, Dict

from .base_llm_agent import BaseLLMAgent
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class BaseWritingAgent(BaseLLMAgent):
    """
    Base class for manuscript writing agents.
    
    All writing agents (Introduction, Methods, Results, Discussion, Abstract)
    should inherit from this class. Provides common structure for writing sections.
    """
    
    def __init__(
        self,
        llm_provider: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,  # Higher temperature for creative writing
        role: str = "WritingAgent",
        topic_context: Dict[str, Any] = None,
        **kwargs
    ):
        """
        Initialize writing agent.
        
        Args:
            llm_provider: LLM provider name
            api_key: API key
            model: Model name
            temperature: Temperature for generation (default 0.7 for writing)
            role: Agent role
            topic_context: Research context
            **kwargs: Additional arguments
        """
        super().__init__(
            llm_provider=llm_provider,
            api_key=api_key,
            model=model,
            temperature=temperature,
            role=role,
            topic_context=topic_context,
            **kwargs
        )
    
    @abstractmethod
    def write_section(self, context: Dict[str, Any]) -> str:
        """
        Write a manuscript section.
        
        Args:
            context: Context dictionary containing data needed for writing
                    (e.g., papers, extracted_data, etc.)
        
        Returns:
            Written section text
        """
        pass
    
    def _format_section_header(self, title: str, level: int = 1) -> str:
        """
        Format section header.
        
        Args:
            title: Section title
            level: Heading level (1-6)
        
        Returns:
            Formatted header
        """
        prefix = "#" * level
        return f"{prefix} {title}\n\n"
    
    def _validate_section_length(self, text: str, min_words: int = 100) -> bool:
        """
        Validate that section meets minimum length requirements.
        
        Args:
            text: Section text
            min_words: Minimum word count
        
        Returns:
            True if valid, False otherwise
        """
        word_count = len(text.split())
        if word_count < min_words:
            logger.warning(
                f"[{self.role}] Section only has {word_count} words "
                f"(minimum: {min_words})"
            )
            return False
        return True
