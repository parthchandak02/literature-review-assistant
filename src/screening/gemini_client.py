"""Gemini-backed screening client with retry for rate limits."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp

from src.screening.dual_screener import ScreeningResponse


class GeminiScreeningClient:
    """Real Gemini API client for screening. Uses generateContent with retry on 429."""

    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    timeout_seconds = 45
    max_retries = 3

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini screening client.")
        model_name = model.split(":", 1)[-1]
        url = f"{self.base_url}/{model_name}:generateContent"
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": ScreeningResponse.model_json_schema(),
            },
        }
        params = {"key": api_key}
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as session:
                    async with session.post(url, params=params, json=payload) as response:
                        if response.status == 429:
                            await response.read()
                            delay = 2**attempt
                            await asyncio.sleep(delay)
                            continue
                        if response.status != 200:
                            body = await response.text()
                            raise RuntimeError(
                                f"Gemini screening request failed: status={response.status}, body={body[:250]}"
                            )
                        data = await response.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError("Gemini screening response had no candidates.")
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(str(part.get("text") or "") for part in parts).strip()
                if not text:
                    raise RuntimeError("Gemini screening response had no text payload.")
                return text
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    delay = 2**attempt
                    await asyncio.sleep(delay)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Gemini screening request failed after retries.")
