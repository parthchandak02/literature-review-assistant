"""TypeSafe Jev (System One) decision client for typed classification/scoring."""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
from pydantic import BaseModel, Field

from src.config.env_context import get_env

logger = logging.getLogger(__name__)

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


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
