"""
Base LLM Agent

Base class for all agents that use LLM functionality.
Provides common LLM calling logic, retry handling, and configuration.
"""

import logging
from abc import ABC
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from ..utils.logging_config import get_logger

T = TypeVar('T', bound=BaseModel)

logger = get_logger(__name__)


class BaseLLMAgent(ABC):
    """
    Base class for any agent using LLM functionality.
    
    Provides common LLM setup, calling logic, retries, and error handling.
    All agents that use LLMs should inherit from this class.
    """
    
    def __init__(
        self,
        llm_provider: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        role: Optional[str] = None,
        topic_context: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize base LLM agent.
        
        Args:
            llm_provider: LLM provider name (e.g., 'gemini', 'openai')
            api_key: API key for the LLM provider
            model: Model name to use
            temperature: Sampling temperature (0.0-1.0)
            role: Agent role for logging
            topic_context: Topic/research context
            agent_config: Additional agent configuration
            **kwargs: Additional arguments passed to subclasses
        """
        self.llm_provider = llm_provider
        self.api_key = api_key
        self.llm_model = model
        self.temperature = temperature
        self.role = role or self.__class__.__name__
        self.topic_context = topic_context or {}
        self.agent_config = agent_config or {}
        
        # Initialize LLM client
        self.llm_client = None
        self._initialize_llm_client()
    
    def _initialize_llm_client(self):
        """Initialize the LLM client based on provider"""
        try:
            if self.llm_provider == "gemini":
                import google.genai as genai
                genai.configure(api_key=self.api_key)
                self.llm_client = genai.Client()
                logger.info(f"[{self.role}] Initialized Gemini client")
            elif self.llm_provider == "openai":
                from openai import OpenAI
                self.llm_client = OpenAI(api_key=self.api_key)
                logger.info(f"[{self.role}] Initialized OpenAI client")
            else:
                logger.warning(f"[{self.role}] Unsupported LLM provider: {self.llm_provider}")
        except Exception as e:
            logger.error(f"[{self.role}] Failed to initialize LLM client: {e}")
            self.llm_client = None
    
    def _call_llm(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Call LLM with prompt.
        
        This method should be overridden by subclasses for specific implementations,
        but provides a basic fallback.
        
        Args:
            prompt: The prompt to send
            model: Optional model override
        
        Returns:
            LLM response text
        """
        if not self.llm_client:
            logger.warning(f"[{self.role}] LLM client not available, using fallback")
            return "LLM not available"
        
        # Subclasses should override this with their specific implementation
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _call_llm method"
        )
    
    def _call_llm_with_schema(
        self,
        prompt: str,
        response_model: Type[T],
        **kwargs
    ) -> T:
        """
        Call LLM with Pydantic schema enforcement.
        
        Subclasses should override this for provider-specific implementations.
        
        Args:
            prompt: The prompt to send
            response_model: Pydantic model class for response validation
            **kwargs: Additional arguments
        
        Returns:
            Validated response object
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _call_llm_with_schema method"
        )
    
    def _get_system_instruction(self) -> Optional[str]:
        """
        Get system instruction for the agent.
        
        Can be overridden by subclasses to provide custom system instructions.
        
        Returns:
            System instruction string or None
        """
        return None
    
    def _enhance_prompt_with_context(self, prompt: str) -> str:
        """
        Enhance prompt with topic context if available.
        
        Args:
            prompt: Original prompt
        
        Returns:
            Enhanced prompt with context
        """
        if not self.topic_context:
            return prompt
        
        context_parts = []
        
        if self.topic_context.get("research_question"):
            context_parts.append(
                f"Research Question: {self.topic_context['research_question']}"
            )
        
        if self.topic_context.get("topic"):
            context_parts.append(
                f"Topic: {self.topic_context['topic']}"
            )
        
        if context_parts:
            context_str = "\n".join(context_parts)
            return f"{context_str}\n\n{prompt}"
        
        return prompt
