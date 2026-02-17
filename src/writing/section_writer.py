"""Section writer for manuscript generation with citation lineage scaffolding."""

from __future__ import annotations

import os
import re
import time
from typing import List, Optional

import aiohttp

from src.models import ReviewConfig, SectionDraft, SettingsConfig
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
            f"Role: Academic writer for a systematic review.",
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
    ) -> str:
        """Generate section content via Gemini. Returns plain text."""
        prompt = self._build_section_prompt(section, context, word_limit)
        agent_cfg = self.settings.agents.get(agent_name, self.settings.agents["writing"])
        model_name = agent_cfg.model.split(":", 1)[-1]
        url = f"{self.base_url}/{model_name}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": agent_cfg.temperature,
            },
        }
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for section writing.")
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
        _ = elapsed_ms
        return content


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
