"""Generic Gemini generateContent client shared across extraction, quality, and writing phases."""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import aiohttp


class GeminiClient:
    """Calls Gemini generateContent with exponential-backoff retry on 429.

    Supports structured JSON output via json_schema parameter.
    Callers should catch exceptions and apply heuristic fallbacks as needed.
    """

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _TIMEOUT = 120
    _MAX_RETRIES = 3

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.1,
        json_schema: dict | None = None,
    ) -> str:
        """Return the Gemini response text (or JSON string if json_schema is supplied)."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set; cannot call Gemini.")
        model_name = model.split(":", 1)[-1]
        url = f"{self._BASE_URL}/{model_name}:generateContent"
        gen_config: dict[str, Any] = {"temperature": temperature}
        if json_schema is not None:
            gen_config["responseMimeType"] = "application/json"
            gen_config["responseJsonSchema"] = json_schema
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        }
        params = {"key": api_key}
        last_error: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self._TIMEOUT)
                ) as session:
                    async with session.post(url, params=params, json=payload) as resp:
                        if resp.status == 429:
                            await resp.read()
                            await asyncio.sleep(2**attempt + random.uniform(0, 1))
                            continue
                        if resp.status != 200:
                            body = await resp.text()
                            raise RuntimeError(
                                f"Gemini API error {resp.status}: {body[:300]}"
                            )
                        data = await resp.json()
                    candidates = data.get("candidates") or []
                    if not candidates:
                        raise RuntimeError("Gemini returned no candidates.")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(str(p.get("text") or "") for p in parts).strip()
                    if not text:
                        raise RuntimeError("Gemini returned empty text.")
                    return text
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    await asyncio.sleep(2**attempt + random.uniform(0, 1))
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("GeminiClient: all retries exhausted.")
