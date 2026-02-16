"""PydanticAI provider and cost logging hooks."""

from __future__ import annotations

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
    def __init__(self, settings: SettingsConfig, repository: WorkflowRepository):
        self.settings = settings
        self.repository = repository
        self.rate_limiter = RateLimiter()

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
