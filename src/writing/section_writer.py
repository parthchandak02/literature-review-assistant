"""Section writer for manuscript generation with citation lineage scaffolding."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import ReviewConfig, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.renderers import render_section_markdown

logger = logging.getLogger(__name__)


@dataclass
class SectionWriteMetadata:
    """Metadata from a section write LLM call for logging and cost tracking."""

    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


from src.writing.prompts.base import PROHIBITED_PHRASES, get_citation_catalog_constraint


class SectionWriter:
    """Writes manuscript sections using LLM with citation catalog and style constraints."""

    def __init__(
        self,
        review: ReviewConfig,
        settings: SettingsConfig,
        citation_catalog: str = "",
    ):
        self.review = review
        self.settings = settings
        self.citation_catalog = citation_catalog

    def _build_section_prompt(
        self,
        section: str,
        context: str,
        word_limit: int | None = None,
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

    def _build_structured_section_prompt(
        self,
        section: str,
        context: str,
        word_limit: int | None = None,
    ) -> str:
        parts = [
            "Role: Academic writer for a systematic review.",
            f"Topic: {self.review.research_question}",
            f"Section: {section}",
            "",
            "You must output structured section content as JSON matching the schema.",
            "Return only JSON. Do not return markdown outside JSON fields.",
            "Ignore prior marker instructions such as SECTION_BLOCK comments.",
            "Use paragraph and subheading blocks only when possible.",
            "Citations must use only keys provided in the citation catalog.",
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

    @staticmethod
    def _structured_schema() -> dict:
        """JSON schema for section intermediate representation output."""
        return {
            "type": "object",
            "properties": {
                "section_key": {"type": "string"},
                "section_title": {"type": "string"},
                "required_subsections": {"type": "array", "items": {"type": "string"}},
                "cited_keys": {"type": "array", "items": {"type": "string"}},
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "block_type": {
                                "type": "string",
                                "enum": [
                                    "paragraph",
                                    "subheading",
                                    "bullet_list",
                                    "table_ref",
                                    "figure_ref",
                                    "citation_group",
                                ],
                            },
                            "text": {"type": "string"},
                            "level": {"type": "integer", "minimum": 2, "maximum": 4},
                            "citations": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["block_type", "text"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["section_key", "blocks"],
            "additionalProperties": False,
        }

    @staticmethod
    def _fallback_structured_from_text(section: str, raw_text: str) -> StructuredSectionDraft:
        """Convert plain markdown-like text into structured draft blocks."""
        text = str(raw_text or "").strip()
        if not text:
            return StructuredSectionDraft(
                section_key=section,
                blocks=[SectionBlock(block_type="paragraph", text="No section content generated.")],
            )
        blocks: list[SectionBlock] = []
        lines = text.splitlines()
        paragraph_acc: list[str] = []

        def _flush_paragraph() -> None:
            if not paragraph_acc:
                return
            body = " ".join(s.strip() for s in paragraph_acc if s.strip()).strip()
            paragraph_acc.clear()
            if body:
                blocks.append(SectionBlock(block_type="paragraph", text=body))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                _flush_paragraph()
                continue
            m = re.match(r"^(#{3,4})\s+(.+)$", stripped)
            if m:
                _flush_paragraph()
                level = 3 if len(m.group(1)) == 3 else 4
                blocks.append(SectionBlock(block_type="subheading", text=m.group(2).strip(), level=level))
                continue
            paragraph_acc.append(stripped)
        _flush_paragraph()

        if not blocks:
            blocks = [SectionBlock(block_type="paragraph", text=text)]
        return StructuredSectionDraft(section_key=section, blocks=blocks)

    async def write_section_structured_async(
        self,
        section: str,
        context: str,
        word_limit: int | None = None,
        agent_name: str = "writing",
    ) -> tuple[StructuredSectionDraft, SectionWriteMetadata]:
        """Generate a structured section IR using schema-constrained output."""
        prompt = self._build_structured_section_prompt(section, context, word_limit)
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
        try:
            structured, tokens_in, tokens_out, cache_write, cache_read, retries = (
                await client.complete_validated(
                    prompt,
                    model=full_model,
                    temperature=agent_cfg.temperature,
                    response_model=StructuredSectionDraft,
                    json_schema=self._structured_schema(),
                )
            )
            if retries > 0:
                logger.info(
                    "Section '%s' structured output succeeded after %d validation retry(ies).",
                    section,
                    retries,
                )
        except Exception:
            # Last-resort fallback if validation retries are exhausted.
            content, tokens_in, tokens_out, cache_write, cache_read = await client.complete_with_usage(
                prompt,
                model=full_model,
                temperature=agent_cfg.temperature,
                json_schema=self._structured_schema(),
            )
            structured = self._fallback_structured_from_text(section, content)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        cost_usd = LLMProvider.estimate_cost_usd(full_model, tokens_in, tokens_out, cache_write, cache_read)

        metadata = SectionWriteMetadata(
            model=full_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        if not structured.section_key:
            structured.section_key = section
        return structured, metadata

    async def write_section_async(
        self,
        section: str,
        context: str,
        word_limit: int | None = None,
        agent_name: str = "writing",
    ) -> tuple[str, SectionWriteMetadata]:
        """Generate section content via structured IR, then render deterministically."""
        structured, metadata = await self.write_section_structured_async(
            section=section,
            context=context,
            word_limit=word_limit,
            agent_name=agent_name,
        )
        rendered = render_section_markdown(structured)
        return rendered, metadata
