"""Section writer for manuscript generation with citation lineage scaffolding."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import ReviewConfig, SettingsConfig
from src.models.writing import SectionBlock, StructuredAbstractOutput, StructuredSectionDraft
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
        self._timeout_seconds = float(
            getattr(getattr(settings, "llm", None), "request_timeout_seconds", 180)
        )

    def _domain_guidance_lines(self) -> list[str]:
        lines = self.review.domain_brief_lines()
        signal_terms = self.review.domain_signal_terms(limit=12)
        preferred_terms = self.review.preferred_terminology()
        discouraged_terms = self.review.discouraged_terminology()
        out = [
            f"Topic focus: {self.review.expert_topic()}",
            f"Domain: {self.review.domain}",
        ]
        if signal_terms:
            out.append(f"Topic anchor terms: {', '.join(signal_terms)}")
        if preferred_terms:
            out.append(f"Preferred terminology: {', '.join(preferred_terms)}")
        if discouraged_terms:
            out.append(f"Avoid out-of-scope terminology: {', '.join(discouraged_terms)}")
        if lines:
            out.append("Domain brief:")
            out.extend(f"  - {item}" for item in lines)
        out.append(
            "Write like a field-native reviewer for this exact topic. Do not drift into generic academic prose "
            "or a neighboring domain unless the evidence explicitly supports that framing."
        )
        return out

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
            *self._domain_guidance_lines(),
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
            *self._domain_guidance_lines(),
            "",
            "You must output structured section content as JSON matching the schema.",
            "Return only JSON. Do not return markdown outside JSON fields.",
            "Ignore prior marker instructions such as SECTION_BLOCK comments.",
            "Use paragraph and subheading blocks only when possible.",
            "The text field must contain prose only and must not contain bracketed citekeys.",
            "Store every citation only in the citations arrays and cited_keys field.",
            "Citations must use only exact keys provided in the citation catalog.",
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

    def _build_structured_abstract_prompt(
        self,
        context: str,
        *,
        min_words: int,
        max_words: int,
    ) -> str:
        parts = [
            "Role: Academic writer for a systematic review.",
            f"Topic: {self.review.research_question}",
            "Section: abstract",
            "",
            *self._domain_guidance_lines(),
            "",
            "You must output a structured abstract as JSON matching the schema.",
            "Return only JSON. Do not return markdown outside JSON fields.",
            "Do not use inline citation tokens such as [AuthorYear] in any field.",
            f"The combined word count of background+objectives+methods+results+conclusions must be between {min_words} and {max_words}.",
            "Write each field as concise, publication-ready sentences with no placeholders.",
            "keywords must contain 3-8 concise terms relevant to the review topic.",
            "",
            "Context:",
            context,
            "",
            PROHIBITED_PHRASES,
        ]
        if self.citation_catalog:
            parts.append("")
            parts.append(get_citation_catalog_constraint(self.citation_catalog))
        return "\n".join(parts)

    def _catalog_citekeys(self) -> list[str]:
        keys: list[str] = []
        for line in self.citation_catalog.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and "]" in stripped:
                keys.append(stripped[1 : stripped.index("]")].strip())
        return list(dict.fromkeys(k for k in keys if k))

    def _structured_schema(self) -> dict:
        """JSON schema for section intermediate representation output."""
        valid_citekeys = self._catalog_citekeys()
        citation_item_schema: dict[str, object] = {"type": "string"}
        if valid_citekeys and len(valid_citekeys) <= 500:
            citation_item_schema = {"type": "string", "enum": valid_citekeys}
        return {
            "type": "object",
            "properties": {
                "section_key": {"type": "string"},
                "section_title": {"type": "string"},
                "required_subsections": {"type": "array", "items": {"type": "string"}},
                "cited_keys": {"type": "array", "items": citation_item_schema},
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
                            "citations": {"type": "array", "items": citation_item_schema},
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
            if stripped.startswith("### ") or stripped.startswith("#### "):
                _flush_paragraph()
                level = 4 if stripped.startswith("#### ") else 3
                heading_text = stripped[5:].strip() if level == 4 else stripped[4:].strip()
                blocks.append(SectionBlock(block_type="subheading", text=heading_text, level=level))
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
        if section == "abstract":
            return await self._write_abstract_structured_async(
                context=context,
                agent_name=agent_name,
            )
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
        client = PydanticAIClient(timeout_seconds=self._timeout_seconds)
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
        except Exception as exc:
            raise RuntimeError(
                f"Section '{section}' failed structured output validation after bounded retries."
            ) from exc

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

    async def _write_abstract_structured_async(
        self,
        *,
        context: str,
        agent_name: str,
    ) -> tuple[StructuredSectionDraft, SectionWriteMetadata]:
        agent_cfg = (
            self.settings.agents.get(agent_name)
            or self.settings.agents.get("writing")
            or self.settings.agents.get("extraction")
        )
        if not agent_cfg:
            agent_cfg = next(iter(self.settings.agents.values()))
        full_model = agent_cfg.model

        min_words = int(getattr(getattr(self.settings, "writing", None), "abstract_trim_floor_words", 210))
        max_words = int(getattr(getattr(self.settings, "ieee_export", None), "max_abstract_words", 250))
        prompt = self._build_structured_abstract_prompt(context, min_words=min_words, max_words=max_words)
        retry_prompt = prompt

        total_tokens_in = 0
        total_tokens_out = 0
        total_cache_write = 0
        total_cache_read = 0
        elapsed_ms = 0

        client = PydanticAIClient(timeout_seconds=self._timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                parsed, tok_in, tok_out, cache_write, cache_read, retries = await client.complete_validated(
                    retry_prompt,
                    model=full_model,
                    temperature=agent_cfg.temperature,
                    response_model=StructuredAbstractOutput,
                )
                total_tokens_in += tok_in
                total_tokens_out += tok_out
                total_cache_write += cache_write
                total_cache_read += cache_read
                elapsed_ms += int((time.perf_counter() - started) * 1000)
                if retries > 0:
                    logger.info(
                        "Abstract structured output succeeded after %d schema retry(ies).",
                        retries,
                    )
                normalized = parsed.normalized()
                normalized.validate_word_band(min_words=min_words, max_words=max_words)
                structured = normalized.to_section_draft()
                cost_usd = LLMProvider.estimate_cost_usd(
                    full_model,
                    total_tokens_in,
                    total_tokens_out,
                    total_cache_write,
                    total_cache_read,
                )
                metadata = SectionWriteMetadata(
                    model=full_model,
                    tokens_in=total_tokens_in,
                    tokens_out=total_tokens_out,
                    cost_usd=cost_usd,
                    latency_ms=elapsed_ms,
                    cache_read_tokens=total_cache_read,
                    cache_write_tokens=total_cache_write,
                )
                return structured, metadata
            except Exception as exc:
                elapsed_ms += int((time.perf_counter() - started) * 1000)
                last_error = exc
                if attempt == 0:
                    retry_prompt = (
                        prompt
                        + "\n\nRETRY: Previous output failed abstract word-band or schema constraints. "
                        + f"Ensure body word count is strictly between {min_words} and {max_words}, include all fields, "
                        + "and keep keywords concise and non-empty."
                    )
                    continue
                raise RuntimeError(
                    "Section 'abstract' failed structured output validation after bounded retries."
                ) from exc
        raise RuntimeError("Section 'abstract' failed structured output validation.") from last_error

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
