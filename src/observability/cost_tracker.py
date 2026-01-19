"""
Cost Tracking for LLM Usage

Tracks token usage and costs for LLM API calls.
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2024, approximate)
PRICING = {
    "openai": {
        "gpt-4": {"input": 30.0, "output": 60.0},  # $30/$60 per 1M tokens
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    },
    "anthropic": {
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    },
}


@dataclass
class TokenUsage:
    """Token usage for a single call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class CostEntry:
    """Cost entry for tracking."""

    provider: str
    model: str
    token_usage: TokenUsage
    cost: float
    timestamp: datetime
    agent_name: Optional[str] = None


class CostTracker:
    """Tracks costs across all LLM calls."""

    def __init__(self):
        self.entries: List[CostEntry] = []
        self.total_cost: float = 0.0
        self.by_provider: Dict[str, float] = defaultdict(float)
        self.by_model: Dict[str, float] = defaultdict(float)
        self.by_agent: Dict[str, float] = defaultdict(float)

    def record_call(
        self,
        provider: str,
        model: str,
        usage: Any,  # Can be OpenAI or Anthropic usage object
        agent_name: Optional[str] = None,
    ):
        """
        Record an LLM call and calculate cost.

        Args:
            provider: LLM provider ("openai" or "anthropic")
            model: Model name
            usage: Usage object (OpenAI or Anthropic format)
            agent_name: Optional agent name
        """
        # Convert usage to TokenUsage
        if provider == "openai":
            token_usage = TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
            )
        elif provider == "anthropic":
            token_usage = TokenUsage(
                prompt_tokens=getattr(usage, "input_tokens", 0),
                completion_tokens=getattr(usage, "output_tokens", 0),
                total_tokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
            )
        else:
            token_usage = TokenUsage()

        cost = self._calculate_cost(provider, model, token_usage)

        entry = CostEntry(
            provider=provider,
            model=model,
            token_usage=token_usage,
            cost=cost,
            timestamp=datetime.now(),
            agent_name=agent_name,
        )

        self.entries.append(entry)
        self.total_cost += cost
        self.by_provider[provider] += cost
        self.by_model[model] += cost
        if agent_name:
            self.by_agent[agent_name] += cost

    def _calculate_cost(self, provider: str, model: str, token_usage: TokenUsage) -> float:
        """
        Calculate cost for token usage.

        Args:
            provider: LLM provider
            model: Model name
            token_usage: Token usage

        Returns:
            Cost in USD
        """
        if provider not in PRICING:
            logger.warning(f"Unknown provider: {provider}")
            return 0.0

        provider_pricing = PRICING[provider]

        # Find matching model (handle variations)
        model_key = None
        for key in provider_pricing.keys():
            if key in model or model in key:
                model_key = key
                break

        if not model_key:
            logger.warning(f"Unknown model pricing: {provider}/{model}")
            return 0.0

        pricing = provider_pricing[model_key]

        input_cost = (token_usage.prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (token_usage.completion_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    def get_summary(self) -> Dict:
        """
        Get cost summary.

        Returns:
            Summary dictionary
        """
        return {
            "total_cost_usd": self.total_cost,
            "total_calls": len(self.entries),
            "by_provider": dict(self.by_provider),
            "by_model": dict(self.by_model),
            "by_agent": dict(self.by_agent),
            "total_tokens": sum(e.token_usage.total_tokens for e in self.entries),
        }


class LLMCostTracker:
    """Helper class for tracking LLM costs from API responses."""

    def __init__(self, cost_tracker: CostTracker):
        """
        Initialize LLM cost tracker.

        Args:
            cost_tracker: CostTracker instance
        """
        self.cost_tracker = cost_tracker

    def track_openai_response(self, response: Any, model: str, agent_name: Optional[str] = None):
        """
        Track cost from OpenAI API response.

        Args:
            response: OpenAI API response object
            model: Model name
            agent_name: Optional agent name
        """
        if hasattr(response, "usage"):
            usage = response.usage
            token_usage = TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            self.cost_tracker.record_call("openai", model, token_usage, agent_name)

    def track_anthropic_response(self, response: Any, model: str, agent_name: Optional[str] = None):
        """
        Track cost from Anthropic API response.

        Args:
            response: Anthropic API response object
            model: Model name
            agent_name: Optional agent name
        """
        if hasattr(response, "usage"):
            usage = response.usage
            token_usage = TokenUsage(
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            )
            self.cost_tracker.record_call("anthropic", model, token_usage, agent_name)


# Global cost tracker instance
_global_cost_tracker = CostTracker()


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance."""
    return _global_cost_tracker
