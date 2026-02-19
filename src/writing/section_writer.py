"""Section writer for manuscript generation with citation lineage scaffolding."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
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
        """Build prompt for a section."""
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
        """Generate section content via LLM. Returns (content, metadata) for logging."""
        prompt = self._build_section_prompt(section, context, word_limit)
        agent_cfg = (
            self.settings.agents.get(agent_name)
            or self.settings.agents.get("writing")
            or self.settings.agents.get("extraction")
        )
        if not agent_cfg:
            agent_cfg = next(iter(self.settings.agents.values()))
        full_model = agent_cfg.model

        start = time.perf_counter()
        client = PydanticAIClient()
        content, tokens_in, tokens_out = await client.complete_with_usage(
            prompt,
            model=full_model,
            temperature=agent_cfg.temperature,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

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
