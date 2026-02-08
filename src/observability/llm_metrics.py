"""
LLM Metrics and Observability

Tracks LLM call performance, parsing failures, and costs.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class LLMProvider(str, Enum):
    """LLM provider types"""
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    UNKNOWN = "unknown"


class ResponseFormat(str, Enum):
    """LLM response format types"""
    JSON = "json"
    PLAIN_TEXT = "plain_text"
    MALFORMED = "malformed"
    EMPTY = "empty"


@dataclass
class LLMCall:
    """Single LLM call record"""
    timestamp: datetime
    provider: LLMProvider
    model: str
    agent_type: str  # e.g., "fulltext_screener", "title_abstract_screener"
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    response_time_ms: float
    response_format: ResponseFormat
    parsing_success: bool
    fallback_used: bool
    retry_count: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None


@dataclass
class LLMMetrics:
    """Aggregated LLM metrics"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    parsing_failures: int = 0
    fallback_uses: int = 0
    total_retries: int = 0
    
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    
    avg_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    
    by_provider: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_agent_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_response_format: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    calls_history: List[LLMCall] = field(default_factory=list)


class LLMMetricsTracker:
    """Tracks and aggregates LLM call metrics"""
    
    # Token costs (per 1M tokens) - update these based on current pricing
    TOKEN_COSTS = {
        LLMProvider.OPENAI: {
            "gpt-4": {"prompt": 30.0, "completion": 60.0},
            "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
            "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
        },
        LLMProvider.GEMINI: {
            "gemini-pro": {"prompt": 0.5, "completion": 1.5},
            "gemini-1.5-pro": {"prompt": 3.5, "completion": 10.5},
        },
        LLMProvider.ANTHROPIC: {
            "claude-3-opus": {"prompt": 15.0, "completion": 75.0},
            "claude-3-sonnet": {"prompt": 3.0, "completion": 15.0},
        }
    }
    
    def __init__(self):
        self.metrics = LLMMetrics()
        self._start_time = None
    
    def start_call(self) -> float:
        """Mark start of LLM call, returns timestamp"""
        self._start_time = time.time()
        return self._start_time
    
    def record_call(
        self,
        provider: LLMProvider,
        model: str,
        agent_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        response_format: ResponseFormat,
        parsing_success: bool,
        fallback_used: bool = False,
        retry_count: int = 0,
        error: Optional[str] = None
    ):
        """Record a completed LLM call"""
        if self._start_time is None:
            logger.warning("start_call() was not called before record_call()")
            response_time_ms = 0.0
        else:
            response_time_ms = (time.time() - self._start_time) * 1000
            self._start_time = None
        
        total_tokens = prompt_tokens + completion_tokens
        cost = self._calculate_cost(provider, model, prompt_tokens, completion_tokens)
        
        call = LLMCall(
            timestamp=datetime.now(),
            provider=provider,
            model=model,
            agent_type=agent_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            response_time_ms=response_time_ms,
            response_format=response_format,
            parsing_success=parsing_success,
            fallback_used=fallback_used,
            retry_count=retry_count,
            cost_usd=cost,
            error=error
        )
        
        self._update_metrics(call)
        
        # Log notable events
        if not parsing_success:
            logger.warning(
                f"LLM parsing failure: {provider}/{model} for {agent_type}, "
                f"format={response_format}, fallback_used={fallback_used}"
            )
        
        if retry_count > 0:
            logger.info(f"LLM call required {retry_count} retries: {agent_type}")
        
        return call
    
    def _calculate_cost(
        self, 
        provider: LLMProvider, 
        model: str, 
        prompt_tokens: int, 
        completion_tokens: int
    ) -> float:
        """Calculate cost in USD for this call"""
        if provider not in self.TOKEN_COSTS:
            return 0.0
        
        # Find matching model (handle variations like "gpt-4-0613")
        model_costs = None
        for model_key, costs in self.TOKEN_COSTS[provider].items():
            if model.startswith(model_key):
                model_costs = costs
                break
        
        if not model_costs:
            return 0.0
        
        prompt_cost = (prompt_tokens / 1_000_000) * model_costs["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * model_costs["completion"]
        
        return prompt_cost + completion_cost
    
    def _update_metrics(self, call: LLMCall):
        """Update aggregate metrics with new call"""
        m = self.metrics
        
        m.total_calls += 1
        m.calls_history.append(call)
        
        if call.parsing_success and call.error is None:
            m.successful_calls += 1
        else:
            m.failed_calls += 1
        
        if not call.parsing_success:
            m.parsing_failures += 1
        
        if call.fallback_used:
            m.fallback_uses += 1
        
        m.total_retries += call.retry_count
        m.total_tokens += call.total_tokens
        m.total_cost_usd += call.cost_usd
        
        # Update timing stats
        if call.response_time_ms > m.max_response_time_ms:
            m.max_response_time_ms = call.response_time_ms
        if call.response_time_ms < m.min_response_time_ms:
            m.min_response_time_ms = call.response_time_ms
        
        # Recalculate average
        total_time = sum(c.response_time_ms for c in m.calls_history)
        m.avg_response_time_ms = total_time / len(m.calls_history)
        
        # Update categorical counts
        m.by_provider[call.provider.value] += 1
        m.by_agent_type[call.agent_type] += 1
        m.by_response_format[call.response_format.value] += 1
    
    def get_metrics(self) -> LLMMetrics:
        """Get current metrics snapshot"""
        return self.metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """Get human-readable metrics summary"""
        m = self.metrics
        
        return {
            "overview": {
                "total_calls": m.total_calls,
                "successful_calls": m.successful_calls,
                "failed_calls": m.failed_calls,
                "success_rate": f"{m.successful_calls / m.total_calls * 100:.1f}%" if m.total_calls > 0 else "0%",
            },
            "reliability": {
                "parsing_failures": m.parsing_failures,
                "parsing_failure_rate": f"{m.parsing_failures / m.total_calls * 100:.1f}%" if m.total_calls > 0 else "0%",
                "fallback_uses": m.fallback_uses,
                "total_retries": m.total_retries,
                "avg_retries_per_call": f"{m.total_retries / m.total_calls:.2f}" if m.total_calls > 0 else "0",
            },
            "performance": {
                "avg_response_time_ms": f"{m.avg_response_time_ms:.1f}",
                "max_response_time_ms": f"{m.max_response_time_ms:.1f}",
                "min_response_time_ms": f"{m.min_response_time_ms:.1f}" if m.min_response_time_ms != float('inf') else "N/A",
            },
            "costs": {
                "total_tokens": f"{m.total_tokens:,}",
                "total_cost_usd": f"${m.total_cost_usd:.4f}",
                "avg_cost_per_call": f"${m.total_cost_usd / m.total_calls:.4f}" if m.total_calls > 0 else "$0",
            },
            "breakdown": {
                "by_provider": dict(m.by_provider),
                "by_agent_type": dict(m.by_agent_type),
                "by_response_format": dict(m.by_response_format),
            }
        }
    
    def export_to_json(self, filepath: Path):
        """Export metrics to JSON file"""
        import json
        
        summary = self.get_summary()
        summary["exported_at"] = datetime.now().isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Exported LLM metrics to {filepath}")
    
    def reset(self):
        """Reset all metrics"""
        self.metrics = LLMMetrics()
        logger.info("LLM metrics reset")


# Global tracker instance
_global_tracker = LLMMetricsTracker()


def get_tracker() -> LLMMetricsTracker:
    """Get the global metrics tracker instance"""
    return _global_tracker


def log_metrics_summary():
    """Log current metrics summary"""
    tracker = get_tracker()
    summary = tracker.get_summary()
    
    logger.info("=== LLM Metrics Summary ===")
    logger.info(f"Total Calls: {summary['overview']['total_calls']}")
    logger.info(f"Success Rate: {summary['overview']['success_rate']}")
    logger.info(f"Parsing Failures: {summary['reliability']['parsing_failures']} "
                f"({summary['reliability']['parsing_failure_rate']})")
    logger.info(f"Total Cost: {summary['costs']['total_cost_usd']}")
    logger.info(f"Avg Response Time: {summary['performance']['avg_response_time_ms']}ms")
    logger.info("=" * 30)
