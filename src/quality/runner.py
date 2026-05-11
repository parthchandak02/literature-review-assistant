"""Shared LLM execution path for quality assessment modules."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models.config import SettingsConfig

_T = TypeVar("_T", bound=BaseModel)


@dataclass
class QualityRunnerResult:
    tokens_in: int = 0
    tokens_out: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0


class QualityLLMRunner:
    """Execute quality prompts with a consistent client + provider flow."""

    def __init__(
        self,
        llm_client: LLMBackend | None,
        settings: SettingsConfig | None,
        provider: object | None,
    ) -> None:
        self._llm_client = llm_client
        self._settings = settings
        self._provider = provider

    async def run_validated(
        self,
        *,
        agent_key: str,
        phase_name: str,
        prompt: str,
        response_model: type[_T],
    ) -> tuple[_T, QualityRunnerResult]:
        if self._llm_client is None or self._settings is None:
            raise RuntimeError("LLM client/settings unavailable")
        agent = self._settings.agents.get(agent_key)
        if agent is None:
            raise RuntimeError(f"{agent_key} agent not configured in settings")
        model = agent.model
        temperature = agent.temperature
        if self._provider is not None:
            await self._provider.reserve_call_slot(agent_key)
        started = time.monotonic()
        if self._provider is not None and isinstance(self._llm_client, PydanticAIClient):
            parsed, tok_in, tok_out, cw, cr, _retries = await self._llm_client.complete_validated(
                prompt,
                model=model,
                temperature=temperature,
                response_model=response_model,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            result = QualityRunnerResult(
                tokens_in=tok_in,
                tokens_out=tok_out,
                cache_write_tokens=cw,
                cache_read_tokens=cr,
                latency_ms=latency_ms,
            )
            cost = self._provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
            await self._provider.log_cost(
                model,
                tok_in,
                tok_out,
                cost,
                latency_ms,
                phase=phase_name,
                cache_read_tokens=cr,
                cache_write_tokens=cw,
            )
            return parsed, result
        schema = response_model.model_json_schema()
        raw = await self._llm_client.complete(prompt, model=model, temperature=temperature, json_schema=schema)
        return response_model.model_validate_json(raw), QualityRunnerResult()
