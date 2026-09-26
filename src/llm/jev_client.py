"""TypeSafe Jev (System One) decision client for typed classification/scoring."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Iterable
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
from pydantic import BaseModel, Field

from src.config.env_context import get_env

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository
    from src.models.config import JevConfig

logger = logging.getLogger(__name__)

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

_T = TypeVar("_T")


class JevQuestionChoice(BaseModel):
    type: str = "choice"
    instructions: str
    criteria: dict[str, str]


class JevAskResult(BaseModel):
    answers: dict[str, Any]
    model: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = 0


def resolve_typesafe_api_key() -> str | None:
    return get_env("TYPESAFE_API_KEY")


async def ask_jev(
    *,
    model: str,
    state: str | dict[str, Any],
    questions: dict[str, JevQuestionChoice | dict[str, Any]],
    timeout_seconds: float = 120.0,
) -> JevAskResult:
    """POST to TypeSafe /v1/systemone. Raises on HTTP or schema errors."""
    api_key = resolve_typesafe_api_key()
    if not api_key:
        raise RuntimeError("TYPESAFE_API_KEY is not configured")

    payload_questions: dict[str, Any] = {}
    for name, q in questions.items():
        payload_questions[name] = q.model_dump() if isinstance(q, JevQuestionChoice) else q

    payload = {"model": model, "state": state, "questions": payload_questions}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    started = time.perf_counter()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(JEV_ENDPOINT, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
    if not isinstance(data, dict) or "answers" not in data:
        raise ValueError(f"Jev response missing answers: keys={list(data.keys()) if isinstance(data, dict) else type(data)}")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return JevAskResult(
        answers=data["answers"],
        model=str(data.get("model") or model),
        usage={str(k): int(v) for k, v in usage.items() if isinstance(v, (int, float))},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


def jev_mode(settings: Any, surface: str) -> str:
    """Resolve off|shadow|live for a surface; anything unexpected is off."""
    cfg = getattr(settings, "jev", None)
    mode_for = getattr(cfg, "mode_for", None)
    if mode_for is None:
        return "off"
    try:
        return str(mode_for(surface))
    except Exception:
        return "off"


def jev_key_available() -> bool:
    return bool(resolve_typesafe_api_key())


def jev_tokens(result: JevAskResult) -> tuple[int, int]:
    return int(result.usage.get("input_tokens", 0)), int(result.usage.get("output_tokens", 0))


def jev_cost_phase(base_phase: str, mode: str) -> str:
    """Cost-record phase label: live -> '<phase>_jev', shadow -> 'jev_shadow_<phase>'."""
    return f"jev_shadow_{base_phase}" if mode == "shadow" else f"{base_phase}_jev"


async def log_jev_cost(
    repository: WorkflowRepository | None,
    *,
    jev: JevConfig,
    result: JevAskResult,
    phase: str,
    workflow_id: str,
) -> float:
    """Persist one cost_records row for a Jev call using JevConfig pricing. Never raises."""
    tok_in, tok_out = jev_tokens(result)
    cost = jev.cost_usd(tok_in, tok_out)
    if repository is None:
        return cost
    try:
        from src.models.additional import CostRecord

        await repository.save_cost_record(
            CostRecord(
                workflow_id=workflow_id,
                model=result.model or jev.model,
                tokens_in=tok_in,
                tokens_out=tok_out,
                cost_usd=cost,
                latency_ms=result.latency_ms,
                phase=phase,
            )
        )
    except Exception:
        logger.debug("jev cost record skipped", exc_info=True)
    return cost


async def record_jev_decision(
    repository: WorkflowRepository | None,
    *,
    workflow_id: str,
    phase: str,
    surface: str,
    paper_id: str | None,
    choice: str,
    confidence: float,
    routed: str,
    mode: str,
    result: JevAskResult | None = None,
    cost_usd: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write a jev_decisions row; latency/tokens/cost/mode go in details_json. Never raises."""
    if repository is None or not workflow_id:
        return
    payload: dict[str, Any] = {"mode": mode}
    if result is not None:
        tok_in, tok_out = jev_tokens(result)
        payload.update(
            {
                "latency_ms": result.latency_ms,
                "tokens_in": tok_in,
                "tokens_out": tok_out,
                "model": result.model,
            }
        )
    if cost_usd is not None:
        payload["cost_usd"] = cost_usd
    payload.update(details or {})
    try:
        await repository.save_jev_decision(
            workflow_id=workflow_id,
            phase=phase,
            surface=surface,
            paper_id=paper_id,
            choice=choice,
            confidence=confidence,
            routed=routed,
            details_json=json.dumps(payload, sort_keys=True, default=str),
        )
    except Exception:
        logger.debug("jev_decisions persist skipped", exc_info=True)


async def bounded_gather(coros: Iterable[Awaitable[_T]], limit: int) -> list[_T]:
    """asyncio.gather with a concurrency cap. Callers must make coros non-raising."""
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _run(coro: Awaitable[_T]) -> _T:
        async with semaphore:
            return await coro

    return list(await asyncio.gather(*(_run(c) for c in coros)))
