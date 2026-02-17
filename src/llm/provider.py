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

    _PRICE_PER_1M: dict[str, tuple[float, float]] = {
        "flash-lite": (0.10, 0.40),
        "flash": (0.30, 2.50),
        "pro": (1.25, 10.00),
    }

    @classmethod
    def estimate_cost_usd(cls, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost from token counts. Uses word count as rough token proxy."""
        tier = cls._tier_from_model(model)
        prices = cls._PRICE_PER_1M.get(tier, (0.30, 2.50))
        return (tokens_in / 1e6) * prices[0] + (tokens_out / 1e6) * prices[1]

    @staticmethod
    def _tier_from_model(model: str) -> str:
        lowered = model.lower()
        if "flash-lite" in lowered:
            return "flash-lite"
        if "flash" in lowered:
            return "flash"
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
