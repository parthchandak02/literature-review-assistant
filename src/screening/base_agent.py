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

from rich.console import Console
from rich.panel import Panel

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
console = Console()


def get_default_model_for_provider(provider: str) -> str:
    """
    Get default model name for a given LLM provider.
    
    Args:
        provider: LLM provider name ('openai', 'anthropic', 'gemini', 'perplexity')
        
    Returns:
        Default model name for the provider
    """
    defaults = {
        "openai": "gpt-4",
        "anthropic": "claude-3-opus-20240229",
        "gemini": "gemini-2.5-pro",
        "perplexity": "sonar-pro",
    }
    return defaults.get(provider.lower(), "gpt-4")


def validate_model_provider_compatibility(model: str, provider: str) -> bool:
    """
    Validate that a model name is compatible with the provider.
    
    Args:
        model: Model name
        provider: LLM provider name
        
    Returns:
        True if compatible, False otherwise
    """
    provider_lower = provider.lower()
    model_lower = model.lower()
    
    # OpenAI models
    if provider_lower == "openai":
        return any(
            model_lower.startswith(prefix)
            for prefix in ["gpt-4", "gpt-3.5", "gpt-4o", "o1"]
        )
    
    # Anthropic models
    elif provider_lower == "anthropic":
        return any(
            model_lower.startswith(prefix)
            for prefix in ["claude-3", "claude-2", "claude"]
        )
    
    # Gemini models
    elif provider_lower == "gemini":
        return any(
            model_lower.startswith(prefix)
            for prefix in ["gemini", "gemma"]
        )
    
    # Perplexity models
    elif provider_lower == "perplexity":
        return any(
            model_lower.startswith(prefix)
            for prefix in ["sonar", "llama", "mistral"]
        )
    
    # Unknown provider - allow but warn
    return True


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
            llm_provider: LLM provider ('gemini', 'perplexity')
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

        self._setup_llm()
        self._register_tools_from_config()

    def _setup_llm(self):
        """Setup LLM client."""
        import os

        if self.llm_provider == "openai":
            try:
                import openai

                self.llm_client = openai.OpenAI(api_key=self.api_key) if self.api_key else None
            except ImportError:
                self.llm_client = None
                print("Warning: OpenAI library not installed")
        elif self.llm_provider == "anthropic":
            try:
                import anthropic

                self.llm_client = (
                    anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
                )
            except ImportError:
                self.llm_client = None
                print("Warning: Anthropic library not installed")
        elif self.llm_provider == "gemini":
            try:
                from google import genai

                # Use GEMINI_API_KEY
                api_key = self.api_key or os.getenv("GEMINI_API_KEY")
                if api_key:
                    self.llm_client = genai.Client(api_key=api_key)
                    # Store model name separately for use in generate_content calls
                    self.llm_model_name = self.llm_model
                else:
                    self.llm_client = None
                    print("Warning: Gemini API key not found")
            except ImportError:
                self.llm_client = None
                print("Warning: google-genai library not installed")
        elif self.llm_provider == "perplexity":
            try:
                from perplexity import Perplexity

                self.llm_client = Perplexity(api_key=self.api_key) if self.api_key else None
            except ImportError:
                self.llm_client = None
                print("Warning: perplexityai library not installed")
        else:
            self.llm_client = None

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
            console.print(
                Panel(
                    f"[bold cyan]LLM Call[/bold cyan]\n"
                    f"[yellow]Model:[/yellow] {model_to_use} ({self.llm_provider})\n"
                    f"[yellow]Agent:[/yellow] {self.role}\n"
                    f"[yellow]Temperature:[/yellow] {self.temperature}\n"
                    f"[yellow]Prompt length:[/yellow] {len(enhanced_prompt)} chars\n"
                    f"[yellow]Prompt preview:[/yellow]\n{prompt_preview}",
                    title="[bold]→ LLM Request[/bold]",
                    border_style="cyan",
                )
            )

        # Wrap LLM call with circuit breaker and retry
        @self.retry_decorator
        def _make_llm_call():
            """Internal function to make LLM call with retry."""
            call_start_time = time.time()

            try:
                if self.llm_provider == "openai":
                    response = self.llm_client.chat.completions.create(
                        model=model_to_use,
                        messages=[{"role": "user", "content": enhanced_prompt}],
                        temperature=self.temperature,
                    )

                    # Track cost if enabled
                    if self.debug_config.show_costs and hasattr(response, "usage"):
                        from ..observability.cost_tracker import get_cost_tracker

                        cost_tracker = get_cost_tracker()
                        cost_tracker.record_call(
                            "openai",
                            model_to_use,
                            type(
                                "Usage",
                                (),
                                {
                                    "prompt_tokens": response.usage.prompt_tokens,
                                    "completion_tokens": response.usage.completion_tokens,
                                    "total_tokens": response.usage.total_tokens,
                                },
                            )(),
                            agent_name=self.role,
                        )

                    duration = time.time() - call_start_time
                    content = response.choices[0].message.content or ""
                    tokens = response.usage.total_tokens if hasattr(response, "usage") else None

                    # Enhanced logging with Rich console
                    if self.debug_config.show_llm_calls or self.debug_config.enabled:
                        response_preview = content[:200] + "..." if len(content) > 200 else content
                        token_info = f"\n[yellow]Tokens:[/yellow] {tokens}" if tokens else ""
                        console.print(
                            Panel(
                                f"[bold green]LLM Response[/bold green]\n"
                                f"[yellow]Duration:[/yellow] {duration:.2f}s{token_info}\n"
                                f"[yellow]Response preview:[/yellow]\n{response_preview}",
                                title="[bold]← LLM Response[/bold]",
                                border_style="green",
                            )
                        )

                    return content
                elif self.llm_provider == "anthropic":
                    # Map OpenAI model names to Anthropic equivalents
                    anthropic_model = model_to_use
                    if model_to_use.startswith("gpt-4"):
                        anthropic_model = "claude-3-opus-20240229"
                    elif model_to_use.startswith("gpt-3.5") or "mini" in model_to_use:
                        anthropic_model = "claude-3-haiku-20240307"

                    response = self.llm_client.messages.create(
                        model=anthropic_model,
                        max_tokens=1000,
                        temperature=self.temperature,
                        messages=[{"role": "user", "content": enhanced_prompt}],
                    )

                    # Track cost if enabled
                    if self.debug_config.show_costs and hasattr(response, "usage"):
                        from ..observability.cost_tracker import get_cost_tracker

                        cost_tracker = get_cost_tracker()
                        cost_tracker.record_call(
                            "anthropic",
                            anthropic_model,
                            type(
                                "Usage",
                                (),
                                {
                                    "input_tokens": response.usage.input_tokens,
                                    "output_tokens": response.usage.output_tokens,
                                    "total_tokens": response.usage.input_tokens
                                    + response.usage.output_tokens,
                                },
                            )(),
                            agent_name=self.role,
                        )

                    duration = time.time() - call_start_time
                    content = response.content[0].text if response.content else ""

                    # Enhanced logging with Rich console
                    if self.debug_config.show_llm_calls or self.debug_config.enabled:
                        response_preview = content[:200] + "..." if len(content) > 200 else content
                        console.print(
                            Panel(
                                f"[bold green]LLM Response[/bold green]\n"
                                f"[yellow]Duration:[/yellow] {duration:.2f}s\n"
                                f"[yellow]Response preview:[/yellow]\n{response_preview}",
                                title="[bold]← LLM Response[/bold]",
                                border_style="green",
                            )
                        )

                    return content
                elif self.llm_provider == "gemini":
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

                    # Track cost if enabled
                    if self.debug_config.show_costs:
                        from ..observability.cost_tracker import get_cost_tracker

                        cost_tracker = get_cost_tracker()
                        # Google GenAI cost tracking would need usage info if available
                        # For now, we'll skip detailed cost tracking

                    duration = time.time() - call_start_time
                    content = response.text if hasattr(response, "text") else str(response)

                    # Enhanced logging with Rich console
                    if self.debug_config.show_llm_calls or self.debug_config.enabled:
                        response_preview = content[:200] + "..." if len(content) > 200 else content
                        console.print(
                            Panel(
                                f"[bold green]LLM Response[/bold green]\n"
                                f"[yellow]Duration:[/yellow] {duration:.2f}s\n"
                                f"[yellow]Response preview:[/yellow]\n{response_preview}",
                                title="[bold]← LLM Response[/bold]",
                                border_style="green",
                            )
                        )

                    return content
                elif self.llm_provider == "perplexity":
                    # Perplexity uses OpenAI-compatible API
                    response = self.llm_client.chat.completions.create(
                        model=self.llm_model,
                        messages=[{"role": "user", "content": enhanced_prompt}],
                        temperature=self.temperature,
                    )

                    # Track cost if enabled
                    if self.debug_config.show_costs and hasattr(response, "usage"):
                        from ..observability.cost_tracker import get_cost_tracker

                        cost_tracker = get_cost_tracker()
                        cost_tracker.record_call(
                            "perplexity",
                            self.llm_model,
                            type(
                                "Usage",
                                (),
                                {
                                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                                    "completion_tokens": getattr(
                                        response.usage, "completion_tokens", 0
                                    ),
                                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                                },
                            )(),
                            agent_name=self.role,
                        )

                    duration = time.time() - call_start_time
                    content = response.choices[0].message.content or ""

                    # Enhanced logging with Rich console
                    if self.debug_config.show_llm_calls or self.debug_config.enabled:
                        response_preview = content[:200] + "..." if len(content) > 200 else content
                        console.print(
                            Panel(
                                f"[bold green]LLM Response[/bold green]\n"
                                f"[yellow]Duration:[/yellow] {duration:.2f}s\n"
                                f"[yellow]Response preview:[/yellow]\n{response_preview}",
                                title="[bold]← LLM Response[/bold]",
                                border_style="green",
                            )
                        )

                    return content
                else:
                    raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")
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
                console.print(f"[dim]Total LLM call time (including overhead): {total_duration:.2f}s[/dim]")
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
        Call LLM with tool calling support (ReAct pattern).
        Includes debug logging for tool calls.

        Args:
            prompt: Original prompt
            model: Optional model override
            max_iterations: Maximum tool calling iterations

        Returns:
            Final LLM response text
        """
        if self.debug_config.show_tool_calls:
            logger.info(
                f"[{self.role}] Starting tool calling loop (max {max_iterations} iterations)"
            )
        """
        Call LLM with tool calling support (ReAct pattern).
        
        Args:
            prompt: Original prompt
            model: Optional model override
            max_iterations: Maximum tool calling iterations
            
        Returns:
            Final LLM response text
        """
        if not self.llm_client:
            logger.warning("LLM client not available")
            return "LLM not available"

        model_to_use = model or self.llm_model
        enhanced_prompt = self._inject_topic_context(prompt)

        # Get tools for LLM
        tools = self.tool_registry.get_tools_for_llm(self.llm_provider)

        messages = [{"role": "user", "content": enhanced_prompt}]

        for iteration in range(max_iterations):
            try:
                if self.llm_provider == "openai":
                    response = self.llm_client.chat.completions.create(
                        model=model_to_use,
                        messages=messages,
                        temperature=self.temperature,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                    )

                    message = response.choices[0].message
                    messages.append(message)

                    # Check if tool calls were made
                    if message.tool_calls:
                        if self.debug_config.show_tool_calls:
                            logger.info(
                                f"[{self.role}] Tool calls requested: {len(message.tool_calls)}"
                            )

                        # Execute tools
                        for tool_call in message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args = json.loads(tool_call.function.arguments)

                            if self.debug_config.show_tool_calls:
                                logger.debug(
                                    f"[{self.role}] Executing tool: {tool_name} with args: {tool_args}"
                                )

                            # Execute tool
                            tool_result = self.tool_registry.execute_tool(tool_name, tool_args)

                            if self.debug_config.show_tool_calls:
                                if tool_result.status.value == "success":
                                    logger.info(
                                        f"[{self.role}] Tool {tool_name} succeeded in {tool_result.execution_time:.2f}s"
                                    )
                                else:
                                    logger.warning(
                                        f"[{self.role}] Tool {tool_name} failed: {tool_result.error}"
                                    )

                            # Add tool result to messages
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(
                                        {
                                            "status": tool_result.status.value,
                                            "result": tool_result.result,
                                            "error": tool_result.error,
                                        }
                                    ),
                                }
                            )
                        # Continue loop to get LLM response with tool results
                        continue
                    else:
                        # No tool calls, return final response
                        return message.content or ""

                elif self.llm_provider == "anthropic":
                    # Anthropic tool use format
                    response = self.llm_client.messages.create(
                        model="claude-3-opus-20240229"
                        if "gpt-4" in model_to_use
                        else "claude-3-haiku-20240307",
                        max_tokens=2000,
                        temperature=self.temperature,
                        messages=messages,
                        tools=tools if tools else None,
                    )

                    message = response.content[0]

                    # Check if tool use was requested
                    if hasattr(message, "type") and message.type == "tool_use":
                        # Execute tool
                        tool_name = message.name
                        tool_args = message.input

                        tool_result = self.tool_registry.execute_tool(tool_name, tool_args)

                        # Add tool result
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": message.id,
                                        "content": json.dumps(
                                            {
                                                "status": tool_result.status.value,
                                                "result": tool_result.result,
                                                "error": tool_result.error,
                                            }
                                        ),
                                    }
                                ],
                            }
                        )
                        continue
                    else:
                        # Text response
                        return message.text if hasattr(message, "text") else str(message)
                elif self.llm_provider == "gemini":
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
                elif self.llm_provider == "perplexity":
                    # Perplexity uses OpenAI-compatible API
                    response = self.llm_client.chat.completions.create(
                        model=model_to_use,
                        messages=messages,
                        temperature=self.temperature,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                    )

                    message = response.choices[0].message
                    messages.append(message)

                    # Check if tool calls were made
                    if message.tool_calls:
                        if self.debug_config.show_tool_calls:
                            logger.info(
                                f"[{self.role}] Tool calls requested: {len(message.tool_calls)}"
                            )

                        # Execute tools
                        for tool_call in message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args = json.loads(tool_call.function.arguments)

                            if self.debug_config.show_tool_calls:
                                logger.debug(
                                    f"[{self.role}] Executing tool: {tool_name} with args: {tool_args}"
                                )

                            # Execute tool
                            tool_result = self.tool_registry.execute_tool(tool_name, tool_args)

                            if self.debug_config.show_tool_calls:
                                if tool_result.status.value == "success":
                                    logger.info(
                                        f"[{self.role}] Tool {tool_name} succeeded in {tool_result.execution_time:.2f}s"
                                    )
                                else:
                                    logger.warning(
                                        f"[{self.role}] Tool {tool_name} failed: {tool_result.error}"
                                    )

                            # Add tool result to messages
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(
                                        {
                                            "status": tool_result.status.value,
                                            "result": tool_result.result,
                                            "error": tool_result.error,
                                        }
                                    ),
                                }
                            )
                        # Continue loop to get LLM response with tool results
                        continue
                    else:
                        # No tool calls, return final response
                        return message.content or ""

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
