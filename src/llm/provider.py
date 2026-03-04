"""PydanticAI provider and cost logging hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from genai_prices import Usage as GPUsage
from genai_prices import calc_price
from genai_prices.update_prices import UpdatePrices

from src.db.repositories import WorkflowRepository
from src.llm.rate_limiter import RateLimiter
from src.models import CostRecord, SettingsConfig

_log = logging.getLogger(__name__)

# Start a background thread that refreshes the genai-prices snapshot from GitHub
# every hour. This ensures newly-launched models (e.g. Gemini 3.1 Flash-Lite
# released the same day) get accurate pricing as soon as the library's data.json
# is updated upstream -- without requiring a pip upgrade.
_price_updater = UpdatePrices(update_interval=3600)
_price_updater.start(wait=False)

# Static fallback prices (USD per 1M tokens) for models that were released so
# recently that neither the bundled nor the live genai-prices snapshot knows
# them yet. Keyed by the bare model ref after stripping the provider prefix.
# Remove entries here once genai-prices upstream adds the model.
# Prices sourced from: https://ai.google.dev/gemini-api/docs/pricing
_PRICE_FALLBACK_PER_MTOK: dict[str, tuple[float, float]] = {
    # (input_per_mtok, output_per_mtok)
    "gemini-3.1-flash-lite-preview": (0.25, 1.50),
}


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

    # Maps pydantic-ai model-string prefix -> genai-prices provider_id.
    _PROVIDER_ID_MAP: dict[str, str] = {
        "google-gla:": "google",
        "google-vertex:": "google",
        "anthropic:": "anthropic",
        "openai:": "openai",
        "groq:": "groq",
        "mistral:": "mistral",
        "cohere:": "cohere",
    }

    @classmethod
    def _parse_model_ref(cls, model: str) -> tuple[str, str | None]:
        """Split 'google-gla:gemini-2.5-flash' -> ('gemini-2.5-flash', 'google').

        Returns (model_ref, provider_id) where provider_id may be None for
        bare model strings with no recognized prefix.
        """
        for prefix, provider_id in cls._PROVIDER_ID_MAP.items():
            if model.startswith(prefix):
                return model[len(prefix) :], provider_id
        return model, None

    @classmethod
    def estimate_cost_usd(
        cls,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cache_write: int = 0,
        cache_read: int = 0,
    ) -> float:
        """Return accurate cost (USD) for any supported model.

        Resolution order:
        1. genai-prices (bundled snapshot, then live-updated snapshot from GitHub).
        2. _PRICE_FALLBACK_PER_MTOK static table for models too new for the library.
        3. 0.0 with a debug log -- callers are safe, but cost tracking will be inaccurate.

        Cache tokens are passed through to genai-prices when non-zero.
        """
        model_ref, provider_id = cls._parse_model_ref(model)
        try:
            price = calc_price(
                GPUsage(
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    cache_write_tokens=cache_write or None,
                    cache_read_tokens=cache_read or None,
                ),
                model_ref,
                provider_id=provider_id,
            )
            return float(price.total_price)
        except LookupError:
            # Model not yet in genai-prices; try the static fallback table.
            if model_ref in _PRICE_FALLBACK_PER_MTOK:
                in_rate, out_rate = _PRICE_FALLBACK_PER_MTOK[model_ref]
                cost = (tokens_in * in_rate + tokens_out * out_rate) / 1_000_000
                if cache_read:
                    # Cache reads are typically 25% of input price for Google models.
                    cost += cache_read * (in_rate * 0.1) / 1_000_000
                _log.debug("genai-prices: used static fallback for %r -> $%.6f", model_ref, cost)
                return cost
            _log.warning(
                "genai-prices: unknown model %r, no fallback price -- cost logged as 0.0. "
                "Add to _PRICE_FALLBACK_PER_MTOK in src/llm/provider.py.",
                model_ref,
            )
            return 0.0
        except Exception as exc:
            _log.debug("genai-prices: error pricing %r (%s) - cost set to 0.0", model, exc)
            return 0.0

    @staticmethod
    def _tier_from_model(model: str) -> str:
        """Map a model string to a rate-limiter tier key (flash / flash-lite / pro)."""
        lowered = model.lower()
        if "flash-lite" in lowered:
            return "flash-lite"
        if "flash" in lowered:
            return "flash"
        # All non-Gemini models fall through to the pro (slowest) bucket so
        # they are rate-limited conservatively by default.
        return "pro"

    def get_agent_config(self, agent_name: str) -> AgentRuntimeConfig:
        agent = self.settings.agents[agent_name]
        return AgentRuntimeConfig(
            model=agent.model,
            temperature=agent.temperature,
            tier=self._tier_from_model(agent.model),
        )

    def estimate_cost(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cache_write: int = 0,
        cache_read: int = 0,
    ) -> float:
        """Accurate cost via genai-prices. Delegates to estimate_cost_usd."""
        return self.estimate_cost_usd(model, tokens_in, tokens_out, cache_write, cache_read)

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
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        record = CostRecord(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            phase=phase,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        await self.repository.save_cost_record(record)
