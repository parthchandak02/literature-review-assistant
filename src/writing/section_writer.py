"""Section writer for manuscript generation with citation lineage scaffolding."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import aiohttp

from src.llm.provider import LLMProvider
from src.models import ReviewConfig, SectionDraft, SettingsConfig


@dataclass
class SectionWriteMetadata:
    """Metadata from a section write LLM call for logging and cost tracking."""

    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int

from src.writing.prompts.base import PROHIBITED_PHRASES, get_citation_catalog_constraint


class SectionWriter:
    """Writes manuscript sections using LLM with citation catalog and style constraints."""

    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    timeout_seconds = 120

    def __init__(
        self,
        review: ReviewConfig,
        settings: SettingsConfig,
        citation_catalog: str = "",
        style_patterns: Optional[object] = None,
    ):
        self.review = review
        self.settings = settings
        self.citation_catalog = citation_catalog
        self.style_patterns = style_patterns

    def _build_section_prompt(
        self,
        section: str,
        context: str,
        word_limit: Optional[int] = None,
    ) -> str:
        """Build prompt for a section. Override per section type."""
        parts = [
            "Role: Academic writer for a systematic review.",
            f"Topic: {self.review.research_question}",
            f"Section: {section}",
            "",
            "Context:",
            context,
            "",
            PROHIBITED_PHRASES,
        ]
        if self.citation_catalog:
            parts.append("")
            parts.append(get_citation_catalog_constraint(self.citation_catalog))
        if word_limit:
            parts.append(f"\nWord limit: {word_limit} words.")
        return "\n".join(parts)

    async def write_section_async(
        self,
        section: str,
        context: str,
        word_limit: Optional[int] = None,
        agent_name: str = "writing",
    ) -> Tuple[str, SectionWriteMetadata]:
        """Generate section content via Gemini. Returns (content, metadata) for logging."""
        prompt = self._build_section_prompt(section, context, word_limit)
        agent_cfg = (
            self.settings.agents.get(agent_name)
            or self.settings.agents.get("writing")
            or self.settings.agents.get("extraction")
        )
        if not agent_cfg:
            agent_cfg = next(iter(self.settings.agents.values()))
        model_name = agent_cfg.model.split(":", 1)[-1]
        full_model = agent_cfg.model
        url = f"{self.base_url}/{model_name}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": agent_cfg.temperature,
            },
        }
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return (
                f"[{section} placeholder - GEMINI_API_KEY not set]",
                SectionWriteMetadata(
                    model=full_model,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=0,
                ),
            )
        params = {"key": api_key}
        timeout = getattr(
            getattr(self.settings, "writing", None),
            "llm_timeout",
            self.timeout_seconds,
        )
        start = time.perf_counter()
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.post(url, params=params, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"Gemini section write failed: status={response.status}, body={body[:250]}"
                    )
                data = await response.json()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini section write response had no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(str(part.get("text") or "") for part in parts).strip()

        usage = data.get("usageMetadata") or {}
        tokens_in = usage.get("promptTokenCount") or max(1, len(prompt.split()))
        tokens_out = usage.get("candidatesTokenCount") or max(1, len(content.split()))
        cost_usd = LLMProvider.estimate_cost_usd(full_model, tokens_in, tokens_out)

        metadata = SectionWriteMetadata(
            model=full_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
        )
        return content, metadata


def write_section(
    section: str,
    context: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    citation_catalog: str = "",
    word_limit: Optional[int] = None,
) -> SectionDraft:
    """Synchronous wrapper for section writing. Returns SectionDraft.

    For now returns a placeholder draft; full async integration is in workflow.
    """
    word_count = len(re.split(r"\s+", context.strip())) if context else 0
    return SectionDraft(
        workflow_id="",
        section=section,
        version=1,
        content="[Section placeholder - use SectionWriter.write_section_async in workflow]",
        claims_used=[],
        citations_used=[],
        word_count=word_count,
    )
