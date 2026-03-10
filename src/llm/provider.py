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
        on_waiting: Callable[[str, int, int, float], None] | None = None,
        on_resolved: Callable[[str, float], None] | None = None,
    ):
        self.settings = settings
        self.repository = repository
        llm_cfg = settings.llm
        self.rate_limiter = RateLimiter(
            flash_rpm=llm_cfg.flash_rpm,
            flash_lite_rpm=llm_cfg.flash_lite_rpm,
            pro_rpm=llm_cfg.pro_rpm,
            on_waiting=on_waiting,
            on_resolved=on_resolved,
        )
        self._price_fallback_per_mtok: dict[str, tuple[float, float, float]] = {
            model_ref: (
                cfg.input_per_mtok,
                cfg.output_per_mtok,
                cfg.cache_read_input_multiplier,
            )
            for model_ref, cfg in llm_cfg.price_fallback_per_mtok.items()
        }

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
        """Split '<provider-prefix><model-ref>' -> ('<model-ref>', '<provider_id>').

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
        price_fallback_per_mtok: dict[str, tuple[float, float, float]] | None = None,
    ) -> float:
        """Return accurate cost (USD) for any supported model.

        Resolution order:
        1. genai-prices (bundled snapshot, then live-updated snapshot from GitHub).
        2. settings.yaml llm.price_fallback_per_mtok for models too new for the library.
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
            # Model not yet in genai-prices; try YAML-configured fallback table.
            fallback = price_fallback_per_mtok or {}
            if model_ref in fallback:
                in_rate, out_rate, cache_read_multiplier = fallback[model_ref]
                cost = (tokens_in * in_rate + tokens_out * out_rate) / 1_000_000
                if cache_read:
                    cost += cache_read * (in_rate * cache_read_multiplier) / 1_000_000
                _log.debug("genai-prices: used YAML fallback for %r -> $%.6f", model_ref, cost)
                return cost
            _log.warning(
                "genai-prices: unknown model %r, no fallback price -- cost logged as 0.0. "
                "Add to llm.price_fallback_per_mtok in config/settings.yaml.",
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
        return self.estimate_cost_usd(
            model,
            tokens_in,
            tokens_out,
            cache_write,
            cache_read,
            self._price_fallback_per_mtok,
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
        workflow_id: str = "",
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        record = CostRecord(
            workflow_id=workflow_id,
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
