"""
Cost Tracking for LLM Usage

Tracks token usage and costs for LLM API calls.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2026)
PRICING = {
    "gemini": {
        "gemini-2.5-pro": {
            "input_under_200k": 1.25,
            "input_over_200k": 2.50,
            "output_under_200k": 10.00,
            "output_over_200k": 15.00,
        },
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
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
        self.audit_file_path: Optional[Path] = None

        # Historical data (loaded from audit trail)
        self.historical_entries: List[CostEntry] = []
        self.historical_total_cost: float = 0.0
        self.historical_by_provider: Dict[str, float] = defaultdict(float)
        self.historical_by_model: Dict[str, float] = defaultdict(float)
        self.historical_by_agent: Dict[str, float] = defaultdict(float)

    def record_call(
        self,
        provider: str,
        model: str,
        usage: Any,  # Gemini usage object
        agent_name: Optional[str] = None,
    ):
        """
        Record an LLM call and calculate cost.

        Args:
            provider: LLM provider ("gemini" only)
            model: Model name
            usage: Usage object (Gemini format)
            agent_name: Optional agent name
        """
        # Convert usage to TokenUsage (Gemini only)
        if provider == "gemini":
            token_usage = TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", 0),
            )
        else:
            logger.warning(
                f"Unsupported provider for cost tracking: {provider}. Only 'gemini' is supported."
            )
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

        # Write to audit trail if enabled
        if self.audit_file_path:
            self._append_to_audit_trail(entry)

    def enable_audit_trail(self, output_dir: str):
        """
        Enable audit trail logging to a JSON file.

        Args:
            output_dir: Directory where audit trail file will be created
        """
        self.audit_file_path = Path(output_dir) / "llm_calls_audit.json"
        logger.info(f"Audit trail enabled: {self.audit_file_path}")

    def _append_to_audit_trail(self, entry: CostEntry):
        """
        Append a cost entry to the audit trail file.

        Args:
            entry: CostEntry to append
        """
        if not self.audit_file_path:
            return

        try:
            # Create audit entry
            audit_entry = {
                "timestamp": entry.timestamp.isoformat(),
                "agent": entry.agent_name or "Unknown",
                "model": entry.model,
                "provider": entry.provider,
                "prompt_tokens": entry.token_usage.prompt_tokens,
                "completion_tokens": entry.token_usage.completion_tokens,
                "total_tokens": entry.token_usage.total_tokens,
                "cost_usd": entry.cost,
            }

            # Append to file (create if doesn't exist)
            if self.audit_file_path.exists():
                # Read existing entries
                with open(self.audit_file_path) as f:
                    entries = json.load(f)
            else:
                entries = []

            # Append new entry
            entries.append(audit_entry)

            # Write back
            with open(self.audit_file_path, "w") as f:
                json.dump(entries, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to write to audit trail: {e}")

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

        # Handle tiered pricing for Gemini Pro models
        if provider == "gemini" and "pro" in model_key.lower():
            # Gemini Pro models have tiered pricing based on prompt token count
            threshold = 200000  # 200K tokens threshold
            if token_usage.prompt_tokens <= threshold:
                input_rate = pricing.get("input_under_200k", pricing.get("input", 0))
                output_rate = pricing.get("output_under_200k", pricing.get("output", 0))
            else:
                input_rate = pricing.get("input_over_200k", pricing.get("input", 0))
                output_rate = pricing.get("output_over_200k", pricing.get("output", 0))
        elif provider == "gemini" and "flash" in model_key.lower():
            # Flash models use simple pricing (no tiering)
            input_rate = pricing.get("input", 0)
            output_rate = pricing.get("output", 0)
        else:
            # Standard pricing for OpenAI and Anthropic
            input_rate = pricing.get("input", 0)
            output_rate = pricing.get("output", 0)

        input_cost = (token_usage.prompt_tokens / 1_000_000) * input_rate
        output_cost = (token_usage.completion_tokens / 1_000_000) * output_rate

        return input_cost + output_cost

    def load_from_audit_trail(self, audit_file_path: Path) -> Dict[str, Any]:
        """
        Load historical metrics from audit trail file.

        Args:
            audit_file_path: Path to audit trail JSON file

        Returns:
            Dictionary with loaded metrics summary
        """
        try:
            if not audit_file_path.exists():
                logger.debug(f"No audit trail found at {audit_file_path}")
                return {
                    "historical_calls": 0,
                    "historical_cost": 0.0,
                    "historical_tokens": 0,
                }

            with open(audit_file_path) as f:
                audit_entries = json.load(f)

            if not audit_entries:
                logger.debug("Audit trail is empty")
                return {
                    "historical_calls": 0,
                    "historical_cost": 0.0,
                    "historical_tokens": 0,
                }

            # Reconstruct historical entries
            self.historical_entries = []
            self.historical_total_cost = 0.0
            self.historical_by_provider = defaultdict(float)
            self.historical_by_model = defaultdict(float)
            self.historical_by_agent = defaultdict(float)

            for audit_entry in audit_entries:
                try:
                    # Parse timestamp
                    timestamp_str = audit_entry.get("timestamp", "")
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except (ValueError, AttributeError):
                        timestamp = datetime.now()

                    # Create TokenUsage
                    token_usage = TokenUsage(
                        prompt_tokens=audit_entry.get("prompt_tokens", 0),
                        completion_tokens=audit_entry.get("completion_tokens", 0),
                        total_tokens=audit_entry.get("total_tokens", 0),
                    )

                    # Create CostEntry
                    cost_entry = CostEntry(
                        provider=audit_entry.get("provider", "gemini"),
                        model=audit_entry.get("model", "unknown"),
                        token_usage=token_usage,
                        cost=audit_entry.get("cost_usd", 0.0),
                        timestamp=timestamp,
                        agent_name=audit_entry.get("agent", "Unknown"),
                    )

                    # Add to historical data
                    self.historical_entries.append(cost_entry)
                    self.historical_total_cost += cost_entry.cost
                    self.historical_by_provider[cost_entry.provider] += cost_entry.cost
                    self.historical_by_model[cost_entry.model] += cost_entry.cost
                    if cost_entry.agent_name:
                        self.historical_by_agent[cost_entry.agent_name] += cost_entry.cost

                except Exception as entry_error:
                    logger.warning(f"Failed to parse audit entry: {entry_error}")
                    continue

            logger.info(
                f"Loaded {len(self.historical_entries)} historical calls "
                f"(${self.historical_total_cost:.4f}) from audit trail"
            )

            return {
                "historical_calls": len(self.historical_entries),
                "historical_cost": self.historical_total_cost,
                "historical_tokens": sum(e.token_usage.total_tokens for e in self.historical_entries),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted audit trail JSON: {e}")
            return {
                "historical_calls": 0,
                "historical_cost": 0.0,
                "historical_tokens": 0,
            }
        except Exception as e:
            logger.error(f"Failed to load audit trail: {e}")
            return {
                "historical_calls": 0,
                "historical_cost": 0.0,
                "historical_tokens": 0,
            }

    def get_summary(self) -> Dict:
        """
        Get cost summary with historical and current breakdown.

        Returns:
            Summary dictionary
        """
        return {
            # Current session
            "total_cost_usd": self.total_cost,
            "total_calls": len(self.entries),
            "by_provider": dict(self.by_provider),
            "by_model": dict(self.by_model),
            "by_agent": dict(self.by_agent),
            "total_tokens": sum(e.token_usage.total_tokens for e in self.entries),

            # Historical (if loaded from audit trail)
            "historical_cost": self.historical_total_cost,
            "historical_calls": len(self.historical_entries),
            "historical_tokens": sum(e.token_usage.total_tokens for e in self.historical_entries),
            "historical_by_provider": dict(self.historical_by_provider),
            "historical_by_model": dict(self.historical_by_model),
            "historical_by_agent": dict(self.historical_by_agent),
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

    def track_gemini_response(self, response: Any, model: str, agent_name: Optional[str] = None):
        """
        Track cost from Gemini API response.

        Args:
            response: Gemini API response object
            model: Model name
            agent_name: Optional agent name
        """
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage_metadata = response.usage_metadata
            prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0)
            completion_tokens = getattr(usage_metadata, "candidates_token_count", 0)
            total_tokens = getattr(usage_metadata, "total_token_count", 0)

            # Create usage object compatible with record_call
            usage_obj = type(
                "Usage",
                (),
                {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            )()
            self.cost_tracker.record_call("gemini", model, usage_obj, agent_name)


# Global cost tracker instance
_global_cost_tracker = CostTracker()


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance."""
    return _global_cost_tracker
