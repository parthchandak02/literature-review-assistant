"""PydanticAI provider and cost logging hooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.db.repositories import WorkflowRepository
from src.llm.rate_limiter import RateLimiter
from src.models import CostRecord, SettingsConfig


@dataclass
class AgentRuntimeConfig:
    model: str
    temperature: float
    tier: str


class LLMProvider:
    def __init__(
        self,
        settings: SettingsConfig,
        repository: WorkflowRepository,
        on_waiting: Callable[[str, int, int], None] | None = None,
    ):
        self.settings = settings
        self.repository = repository
        llm_cfg = getattr(settings, "llm", None)
        flash_rpm = llm_cfg.flash_rpm if llm_cfg else 10
        flash_lite_rpm = llm_cfg.flash_lite_rpm if llm_cfg else 15
        pro_rpm = llm_cfg.pro_rpm if llm_cfg else 5
        self.rate_limiter = RateLimiter(
            flash_rpm=flash_rpm,
            flash_lite_rpm=flash_lite_rpm,
            pro_rpm=pro_rpm,
            on_waiting=on_waiting,
        )

    # Gemini tiers (input/output per 1M tokens in USD)
    # Anthropic Claude prices (approx Feb 2026)
    # OpenAI prices (approx Feb 2026)
    # Groq prices (approx Feb 2026)
    _PRICE_PER_1M: dict[str, tuple[float, float]] = {
        # Gemini tiers
        "flash-lite": (0.10, 0.40),
        "flash": (0.30, 2.50),
        "pro": (1.25, 10.00),
        # Anthropic Claude
        "claude-opus": (15.00, 75.00),
        "claude-sonnet": (3.00, 15.00),
        "claude-haiku": (0.80, 4.00),
        # OpenAI
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "o3": (10.00, 40.00),
        "o3-mini": (1.10, 4.40),
        # Groq (estimates -- varies by model)
        "groq": (0.05, 0.08),
    }

    @classmethod
    def estimate_cost_usd(cls, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost from token counts for any supported provider."""
        tier = cls._tier_from_model(model)
        prices = cls._PRICE_PER_1M.get(tier, (0.30, 2.50))
        return (tokens_in / 1e6) * prices[0] + (tokens_out / 1e6) * prices[1]

    @staticmethod
    def _tier_from_model(model: str) -> str:
        """Map a model string to a pricing tier key."""
        lowered = model.lower()
        # Gemini tiers
        if "flash-lite" in lowered:
            return "flash-lite"
        if "flash" in lowered:
            return "flash"
        # Anthropic Claude
        if "claude-opus" in lowered or "claude-3-opus" in lowered:
            return "claude-opus"
        if "claude-sonnet" in lowered or "claude-3-5-sonnet" in lowered:
            return "claude-sonnet"
        if "claude-haiku" in lowered:
            return "claude-haiku"
        # OpenAI
        if "gpt-4o-mini" in lowered:
            return "gpt-4o-mini"
        if "gpt-4o" in lowered:
            return "gpt-4o"
        if "o3-mini" in lowered:
            return "o3-mini"
        if "o3" in lowered:
            return "o3"
        # Groq
        if "groq:" in lowered or model.startswith("groq:"):
            return "groq"
        # Default to Gemini Pro pricing for unknown models
        return "pro"

    def get_agent_config(self, agent_name: str) -> AgentRuntimeConfig:
        agent = self.settings.agents[agent_name]
        return AgentRuntimeConfig(
            model=agent.model,
            temperature=agent.temperature,
            tier=self._tier_from_model(agent.model),
        )

    def estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost for display. Use after actual call with token estimates."""
        return self.estimate_cost_usd(model, tokens_in, tokens_out)

    async def reserve_call_slot(self, agent_name: str) -> AgentRuntimeConfig:
        config = self.get_agent_config(agent_name)
        await self.rate_limiter.acquire(config.tier)
        return config

    async def log_cost(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
        phase: str,
    ) -> None:
        record = CostRecord(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            phase=phase,
        )
        await self.repository.save_cost_record(record)
