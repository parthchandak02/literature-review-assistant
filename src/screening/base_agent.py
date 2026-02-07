"""
Base Agent for Screening

Base classes for LLM-powered screening agents.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
import logging
import time

from ..utils.rich_utils import (
    console,
    print_llm_request_panel,
    print_llm_response_panel,
)
from ..utils.retry_strategies import (
    create_llm_retry_decorator,
    LLM_RETRY_CONFIG,
    RetryConfig,
)
from ..utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from ..tools.tool_registry import ToolRegistry, Tool
from ..config.debug_config import get_debug_config_from_env

logger = logging.getLogger(__name__)


def get_default_model_for_provider(provider: str) -> str:
    """
    Get default model for Gemini provider.

    Args:
        provider: LLM provider name ('gemini')

    Returns:
        Default model name for Gemini
    """
    return "gemini-2.5-pro"


def validate_model_provider_compatibility(model: str, provider: str) -> bool:
    """
    Validate that a model name is compatible with Gemini provider.

    Args:
        model: Model name
        provider: LLM provider name ('gemini')

    Returns:
        True if compatible, False otherwise
    """
    provider_lower = provider.lower()
    model_lower = model.lower()

    # Gemini models only
    if provider_lower == "gemini":
        return any(model_lower.startswith(prefix) for prefix in ["gemini", "gemma"])

    # Only gemini is supported for LLM calls
    logger.warning(f"Unsupported LLM provider: {provider}. Only 'gemini' is supported.")
    return False


class InclusionDecision(Enum):
    """Screening decision types."""

    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


@dataclass
class ScreeningResult:
    """Result of screening a paper."""

    decision: InclusionDecision
    confidence: float  # 0.0 to 1.0
    reasoning: str
    exclusion_reason: Optional[str] = None


class BaseScreeningAgent(ABC):
    """Base class for screening agents."""

    def __init__(
        self,
        llm_provider: str = "openai",
        api_key: Optional[str] = None,
        topic_context: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        """
        Initialize screening agent.

        Args:
            llm_provider: LLM provider ('gemini')
            api_key: API key for LLM provider
            topic_context: Topic context dictionary
            agent_config: Agent configuration from YAML (role, goal, backstory, llm_model, temperature, etc.)
            retry_config: Retry configuration (uses defaults if None)
            circuit_breaker_config: Circuit breaker configuration (uses defaults if None)
        """
        self.llm_provider = llm_provider
        self.api_key = api_key
        self.topic_context = topic_context or {}
        self.agent_config = agent_config or {}

        # Extract agent config values
        self.role = self.agent_config.get("role", "Research Agent")
        self.goal = self.agent_config.get("goal", "Perform research tasks")
        self.backstory = self.agent_config.get("backstory", "Experienced researcher")

        # Get model from config or use provider-specific default
        self.llm_model = self.agent_config.get("llm_model")
        if not self.llm_model:
            self.llm_model = get_default_model_for_provider(self.llm_provider)
            logger.debug(
                f"No model specified in config, using provider default: {self.llm_model} for {self.llm_provider}"
            )

        # Validate model/provider compatibility
        if not validate_model_provider_compatibility(self.llm_model, self.llm_provider):
            logger.warning(
                f"Model '{self.llm_model}' may not be compatible with provider '{self.llm_provider}'. "
                f"This may cause errors."
            )

        self.temperature = self.agent_config.get("temperature", 0.3)
        self.max_iterations = self.agent_config.get("max_iterations", 5)

        # Initialize retry and circuit breaker
        self.retry_config = retry_config or LLM_RETRY_CONFIG
        self.retry_decorator = create_llm_retry_decorator(self.retry_config)
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config or CircuitBreakerConfig())

        # Initialize tool registry
        self.tool_registry = tool_registry or ToolRegistry()

        # Load debug configuration
        self.debug_config = get_debug_config_from_env()

        # Track generated files from tool executions
        self._generated_files = []

        self._setup_llm()
        self._register_tools_from_config()

    def _setup_llm(self):
        """Setup LLM client (gemini only)."""
        import os

        if self.llm_provider == "gemini":
            try:
                from google import genai
                from google.genai import types

                # Use GEMINI_API_KEY
                api_key = self.api_key or os.getenv("GEMINI_API_KEY")
                if api_key:
                    # Get timeout from agent config (default: 120 seconds)
                    timeout_seconds = (
                        self.agent_config.get("llm_timeout", 120) if self.agent_config else 120
                    )
                    timeout_ms = timeout_seconds * 1000  # Convert to milliseconds

                    # Create client with timeout configured
                    self.llm_client = genai.Client(
                        api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms)
                    )
                    # Store model name separately for use in generate_content calls
                    self.llm_model_name = self.llm_model
                    logger.debug(f"Initialized Gemini client with {timeout_seconds}s timeout")
                else:
                    self.llm_client = None
                    print("Warning: Gemini API key not found")
            except ImportError:
                self.llm_client = None
                print("Warning: google-genai library not installed")
        else:
            self.llm_client = None
            logger.warning(
                f"Unsupported LLM provider: {self.llm_provider}. Only 'gemini' is supported."
            )

    def _register_tools_from_config(self):
        """Register tools from agent config."""
        tools_list = self.agent_config.get("tools", [])

        for tool_name in tools_list:
            if tool_name == "exa_search":
                try:
                    from ..tools.exa_tool import create_exa_search_tool

                    tool = create_exa_search_tool()
                    self.register_tool(tool)
                except ImportError:
                    logger.warning("Exa tool not available (exa_py not installed)")
            elif tool_name == "exa_answer":
                try:
                    from ..tools.exa_tool import create_exa_answer_tool

                    tool = create_exa_answer_tool()
                    self.register_tool(tool)
                except ImportError:
                    logger.warning("Exa tool not available (exa_py not installed)")
            elif tool_name == "tavily_search":
                try:
                    from ..tools.tavily_tool import create_tavily_search_tool

                    tool = create_tavily_search_tool()
                    self.register_tool(tool)
                except ImportError:
                    logger.warning("Tavily tool not available (tavily-python not installed)")
            elif tool_name == "tavily_extract":
                try:
                    from ..tools.tavily_tool import create_tavily_extract_tool

                    tool = create_tavily_extract_tool()
                    self.register_tool(tool)
                except ImportError:
                    logger.warning("Tavily tool not available (tavily-python not installed)")
            # Other tools (database_search, query_builder, etc.) are registered elsewhere
            # or handled by specific agent implementations

    @abstractmethod
    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> ScreeningResult:
        """Screen a paper based on title and abstract."""
        pass

    def _inject_topic_context(self, prompt: str) -> str:
        """
        Inject topic context and agent role/goal/backstory into prompt.

        Args:
            prompt: Original prompt

        Returns:
            Prompt with topic context and agent identity injected
        """
        # Build agent identity header
        agent_header_parts = []
        agent_header_parts.append(f"You are: {self.role}")
        agent_header_parts.append(f"Your goal: {self.goal}")
        agent_header_parts.append(f"Your background: {self.backstory}")

        # Add topic context
        if self.topic_context:
            topic_info = []
            if "topic" in self.topic_context:
                topic_info.append(f"Research Topic: {self.topic_context['topic']}")
            if "research_question" in self.topic_context:
                topic_info.append(f"Research Question: {self.topic_context['research_question']}")
            if "domain" in self.topic_context:
                topic_info.append(f"Domain: {self.topic_context['domain']}")
            if "keywords" in self.topic_context and self.topic_context["keywords"]:
                topic_info.append(f"Keywords: {', '.join(self.topic_context['keywords'])}")

            if topic_info:
                agent_header_parts.append("\nContext:")
                agent_header_parts.extend(topic_info)

        if agent_header_parts:
            context_header = "\n".join(agent_header_parts)
            return f"{context_header}\n\n{prompt}"

        return prompt

    def _get_system_instruction(self) -> Optional[str]:
        """
        Get system instruction for the agent.

        Override this method in subclasses to provide agent-specific system instructions.
        Writing agents should return academic writing system instruction.

        Returns:
            System instruction string, or None if no system instruction is needed
        """
        return None

    def _get_academic_writing_system_instruction(self) -> str:
        """
        Get the standard academic writing system instruction for writing agents.

        This system instruction prohibits conversational meta-commentary and ensures
        direct, professional academic content output.

        Returns:
            Academic writing system instruction string
        """
        return """You are an expert academic writer specializing in systematic reviews. Your role is to generate precise, structured academic content without conversational preamble, acknowledgments, or meta-commentary.

CRITICAL OUTPUT REQUIREMENTS:
1. Generate ONLY academic content - no conversational preamble, acknowledgments, or meta-commentary whatsoever
2. Begin IMMEDIATELY with substantive content in each section - never precede content with phrases like "Here is," "Of course," "As an expert," "Certainly," or similar conversational framing
3. Do not include any self-referential statements, separator lines, or decorative elements not essential to academic content
4. Maintain formal academic tone and third-person perspective throughout
5. Ensure absolute consistency across all sections - identical formatting principles apply to every section

Output must be suitable for direct insertion into an academic publication without any modification or cleanup of unwanted preambles."""

    def _call_llm(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Call LLM with prompt (topic context and agent config automatically injected).
        Includes retry logic and circuit breaker protection.

        Args:
            prompt: Original prompt
            model: Optional model override (uses agent_config['llm_model'] if not provided)

        Returns:
            LLM response text

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            Exception: If LLM call fails after retries
        """
        if not self.llm_client:
            logger.warning(f"[{self.role}] LLM client not available, using fallback")
            return "LLM not available"

        # Use configured model or override
        model_to_use = model or self.llm_model

        # Inject topic context and agent identity
        enhanced_prompt = self._inject_topic_context(prompt)

        # Enhanced logging with Rich console
        start_time = time.time()
        if self.debug_config.show_llm_calls or self.debug_config.enabled:
            prompt_preview = (
                enhanced_prompt[:200] + "..." if len(enhanced_prompt) > 200 else enhanced_prompt
            )
            print_llm_request_panel(
                model=model_to_use,
                provider=self.llm_provider,
                agent=self.role,
                temperature=self.temperature,
                prompt_length=len(enhanced_prompt),
                prompt_preview=prompt_preview,
            )

        # Wrap LLM call with circuit breaker and retry
        @self.retry_decorator
        def _make_llm_call():
            """Internal function to make LLM call with retry."""
            call_start_time = time.time()

            try:
                if self.llm_provider == "gemini":
                    from google.genai import types

                    # Get system instruction if available
                    system_instruction = self._get_system_instruction()

                    # Build config with temperature and optional system instruction
                    config_dict = {"temperature": self.temperature}
                    if system_instruction:
                        config_dict["system_instruction"] = system_instruction

                    config = types.GenerateContentConfig(**config_dict)

                    response = self.llm_client.models.generate_content(
                        model=getattr(self, "llm_model_name", self.llm_model),
                        contents=enhanced_prompt,
                        config=config,
                    )

                    duration = time.time() - call_start_time
                    content = response.text if hasattr(response, "text") else str(response)
                    model_name = getattr(self, "llm_model_name", self.llm_model)

                    # Extract usage_metadata and track cost
                    cost = 0.0
                    if self.debug_config.show_costs:
                        from ..observability.cost_tracker import (
                            get_cost_tracker,
                            TokenUsage,
                            LLMCostTracker,
                        )

                        cost_tracker = get_cost_tracker()
                        llm_cost_tracker = LLMCostTracker(cost_tracker)

                        # Extract usage_metadata from Gemini response
                        if hasattr(response, "usage_metadata") and response.usage_metadata:
                            usage_metadata = response.usage_metadata
                            prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0)
                            completion_tokens = getattr(usage_metadata, "candidates_token_count", 0)
                            total_tokens = getattr(usage_metadata, "total_token_count", 0)

                            # Track cost
                            llm_cost_tracker.track_gemini_response(
                                response, model_name, agent_name=self.role
                            )

                            # Calculate cost for display
                            cost = cost_tracker._calculate_cost(
                                "gemini",
                                model_name,
                                TokenUsage(
                                    prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens,
                                    total_tokens=total_tokens,
                                ),
                            )

                    # Enhanced logging with Rich console
                    if self.debug_config.show_llm_calls or self.debug_config.enabled:
                        response_preview = content[:200] + "..." if len(content) > 200 else content
                        print_llm_response_panel(
                            duration=duration,
                            response_preview=response_preview,
                            tokens=None,
                            cost=cost,
                        )

                    return content
                else:
                    raise ValueError(
                        f"Unsupported LLM provider: {self.llm_provider}. Only 'gemini' is supported."
                    )
            except Exception as e:
                duration = time.time() - call_start_time
                logger.debug(f"[{self.role}] LLM call failed after {duration:.2f}s: {e}")
                raise

        try:
            # Check circuit breaker state
            if self.circuit_breaker.is_open() and self.debug_config.enabled:
                logger.warning(f"[{self.role}] Circuit breaker is OPEN")

            # Execute with circuit breaker protection
            result = self.circuit_breaker.call(_make_llm_call)

            # Log total duration (includes retry/circuit breaker overhead)
            total_duration = time.time() - start_time
            if self.debug_config.show_llm_calls or self.debug_config.enabled:
                console.print(
                    f"[dim]Total LLM call time (including overhead): {total_duration:.2f}s[/dim]"
                )
                console.print()  # Add spacing after LLM call display

            # Track metrics
            if self.debug_config.show_metrics:
                from ..observability.metrics import get_metrics_collector

                metrics = get_metrics_collector()
                # Note: Duration tracking would need to be added to circuit breaker
                metrics.record_call(self.role, total_duration, success=True)

            return result
        except CircuitBreakerOpenError:
            logger.error(
                f"[{self.role}] Circuit breaker is OPEN. LLM service appears to be failing."
            )
            # Track failure
            if self.debug_config.show_metrics:
                from ..observability.metrics import get_metrics_collector

                metrics = get_metrics_collector()
                metrics.record_call(
                    self.role, 0.0, success=False, error_type="CircuitBreakerOpenError"
                )
            # Graceful degradation: return error message instead of crashing
            return "Error: LLM service temporarily unavailable"
        except Exception as e:
            logger.error(f"[{self.role}] Error calling LLM after retries: {e}", exc_info=True)
            # Track failure
            if self.debug_config.show_metrics:
                from ..observability.metrics import get_metrics_collector

                metrics = get_metrics_collector()
                metrics.record_call(self.role, 0.0, success=False, error_type=type(e).__name__)
            # Graceful degradation
            return f"Error: {str(e)}"

    def _call_llm_with_tools(
        self, prompt: str, model: Optional[str] = None, max_iterations: int = 5
    ) -> str:
        """
        Call LLM with tool calling support (Gemini only).

        Args:
            prompt: Original prompt
            model: Optional model override
            max_iterations: Maximum tool calling iterations

        Returns:
            Final LLM response text
        """
        if self.llm_provider != "gemini":
            raise ValueError(
                f"Tool calling is only supported with Gemini provider. "
                f"Current provider: {self.llm_provider}"
            )

        if not self.llm_client:
            logger.warning("LLM client not available")
            return "LLM not available"

        if self.debug_config.show_tool_calls:
            logger.info(
                f"[{self.role}] Starting tool calling loop (max {max_iterations} iterations)"
            )

        model_to_use = model or self.llm_model
        enhanced_prompt = self._inject_topic_context(prompt)

        # Get tools for LLM
        tools = self.tool_registry.get_tools_for_llm(self.llm_provider)

        messages = [{"role": "user", "content": enhanced_prompt}]

        for _iteration in range(max_iterations):
            try:
                # Gemini tool calling
                # Google GenAI tool calling format
                from google.genai import types

                # Convert messages to Google GenAI format
                contents = []
                for msg in messages:
                    if msg.get("role") == "user":
                        contents.append(
                            types.UserContent(parts=[types.Part.from_text(text=msg["content"])])
                        )
                    elif msg.get("role") == "assistant":
                        if "tool_calls" in msg or "function_calls" in msg:
                            # Handle tool call responses
                            continue
                        contents.append(
                            types.ModelContent(
                                parts=[types.Part.from_text(text=msg.get("content", ""))]
                            )
                        )

                # Prepare tools for Google GenAI
                google_tools = None
                if tools:
                    # Google GenAI supports automatic function calling with Python functions
                    # For now, we'll use manual function declarations
                    function_declarations = []
                    for tool_def in tools:
                        if isinstance(tool_def, dict) and "function" in tool_def:
                            func_def = tool_def["function"]
                            function_declarations.append(
                                types.FunctionDeclaration(
                                    name=func_def["name"],
                                    description=func_def.get("description", ""),
                                    parameters=func_def.get("parameters", {}),
                                )
                            )
                    if function_declarations:
                        google_tools = [types.Tool(function_declarations=function_declarations)]

                response = self.llm_client.models.generate_content(
                    model=getattr(self, "llm_model_name", model_to_use),
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature, tools=google_tools
                    ),
                )

                # Check for function calls
                if hasattr(response, "function_calls") and response.function_calls:
                    # Execute tools
                    for func_call in response.function_calls:
                        tool_name = func_call.name
                        tool_args = func_call.args if hasattr(func_call, "args") else {}

                        tool_result = self.tool_registry.execute_tool(tool_name, tool_args)

                        # Track generated files
                        self._track_generated_file(tool_result)

                        # Add tool result to messages
                        messages.append(
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "status": tool_result.status.value,
                                        "result": tool_result.result,
                                        "error": tool_result.error,
                                    }
                                ),
                            }
                        )
                    continue
                else:
                    # Text response
                    return response.text

            except Exception as e:
                logger.error(f"Error in tool calling loop: {e}", exc_info=True)
                return f"Error: {str(e)}"

        # Max iterations reached
        logger.warning(f"[{self.role}] Max tool calling iterations ({max_iterations}) reached")
        return messages[-1].get("content", "Max iterations reached") if messages else ""

    def register_tool(self, tool: Tool):
        """
        Register a tool for this agent.

        Args:
            tool: Tool to register
        """
        self.tool_registry.register(tool)
        if self.debug_config.show_tool_calls:
            logger.info(f"[{self.role}] Registered tool: {tool.name}")

    def _track_generated_file(self, tool_result) -> None:
        """
        Track generated files from tool execution results.

        Args:
            tool_result: Tool execution result object
        """
        if tool_result.status.value == "success" and tool_result.result:
            result_str = str(tool_result.result)
            # Check if result is a file path
            if result_str and any(
                result_str.endswith(ext) for ext in [".svg", ".html", ".png", ".jpg", ".pdf", ".md"]
            ):
                from pathlib import Path

                if Path(result_str).exists():
                    self._generated_files.append(result_str)
                    logger.debug(f"[{self.role}] Tracked generated file: {result_str}")

    def get_generated_files(self) -> List[str]:
        """
        Get list of files generated by tool executions.

        Returns:
            List of file paths
        """
        return self._generated_files.copy()

    def clear_generated_files(self) -> None:
        """Clear the list of tracked generated files."""
        self._generated_files = []
