"""Writing phase models."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SectionBlock(BaseModel):
    """Deterministic block-level unit for section rendering."""

    block_type: Literal["paragraph", "subheading", "bullet_list", "table_ref", "figure_ref", "citation_group"]
    text: str = ""
    level: int = 3
    citations: list[str] = Field(default_factory=list)


class StructuredSectionDraft(BaseModel):
    """Structured intermediate representation emitted by section writing."""

    section_key: str
    section_title: str = ""
    required_subsections: list[str] = Field(default_factory=list)
    cited_keys: list[str] = Field(default_factory=list)
    blocks: list[SectionBlock] = Field(default_factory=list)


class StructuredAbstractOutput(BaseModel):
    """Typed structured abstract payload produced at generation time."""

    background: str = Field(min_length=20, max_length=900)
    objectives: str = Field(min_length=20, max_length=900)
    methods: str = Field(min_length=30, max_length=1200)
    results: str = Field(min_length=30, max_length=1400)
    conclusions: str = Field(min_length=20, max_length=1000)
    keywords: list[str] = Field(min_length=3, max_length=8)

    @staticmethod
    def _normalize_sentence(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
        return cleaned if cleaned[-1] in ".!?" else f"{cleaned}."

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(keyword or "")).strip(" ,.;:")
        return cleaned

    def normalized(self) -> "StructuredAbstractOutput":
        """Return a normalized copy with punctuation/whitespace normalization."""
        deduped_keywords: list[str] = []
        seen: set[str] = set()
        for keyword in self.keywords:
            normalized = self._normalize_keyword(keyword)
            if not normalized:
                continue
            lower = normalized.lower()
            if lower in seen:
                continue
            seen.add(lower)
            deduped_keywords.append(normalized)
        return StructuredAbstractOutput(
            background=self._normalize_sentence(self.background),
            objectives=self._normalize_sentence(self.objectives),
            methods=self._normalize_sentence(self.methods),
            results=self._normalize_sentence(self.results),
            conclusions=self._normalize_sentence(self.conclusions),
            keywords=deduped_keywords,
        )

    def body_word_count(self) -> int:
        body = " ".join(
            [
                self.background,
                self.objectives,
                self.methods,
                self.results,
                self.conclusions,
            ]
        )
        return len(re.findall(r"\b[\w'-]+\b", body))

    def validate_word_band(self, *, min_words: int, max_words: int) -> None:
        """Raise ValueError when body words are outside configured abstract band."""
        if min_words < 0 or max_words <= 0 or min_words > max_words:
            raise ValueError(f"Invalid abstract word band: min={min_words}, max={max_words}")
        word_count = self.body_word_count()
        if word_count < min_words:
            raise ValueError(
                f"Structured abstract under minimum word requirement: {word_count} < {min_words}"
            )
        if word_count > max_words:
            raise ValueError(
                f"Structured abstract exceeds maximum word requirement: {word_count} > {max_words}"
            )
        if len(self.keywords) < 3:
            raise ValueError("Structured abstract must include at least 3 keywords.")

    def to_markdown(self) -> str:
        """Render deterministic structured abstract markdown lines."""
        normalized = self.normalized()
        keywords_text = ", ".join(normalized.keywords)
        if keywords_text and keywords_text[-1] not in ".!?":
            keywords_text = f"{keywords_text}."
        lines = [
            f"**Background:** {normalized.background}",
            f"**Objectives:** {normalized.objectives}",
            f"**Methods:** {normalized.methods}",
            f"**Results:** {normalized.results}",
            f"**Conclusions:** {normalized.conclusions}",
            f"**Keywords:** {keywords_text}",
        ]
        return "\n".join(lines)

    def to_section_draft(self) -> StructuredSectionDraft:
        """Project structured abstract payload to section IR blocks."""
        markdown = self.to_markdown()
        blocks = [SectionBlock(block_type="paragraph", text=line) for line in markdown.splitlines() if line.strip()]
        return StructuredSectionDraft(section_key="abstract", blocks=blocks, cited_keys=[])


class StructuredManuscriptDraft(BaseModel):
    """Structured manuscript-level intermediate representation."""

    workflow_id: str
    sections: list[StructuredSectionDraft] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutlineNode(BaseModel):
    """One planned subsection node used to guide a section draft."""

    node_id: str
    heading: str
    intent: str
    required_citekeys: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class SectionOutline(BaseModel):
    """Deterministic or LLM-generated outline for one manuscript section."""

    section_key: str
    nodes: list[OutlineNode] = Field(default_factory=list)
    grounding_hash: str | None = None


class ManuscriptOutlinePlan(BaseModel):
    """Workflow-scoped set of section outlines generated before writing."""

    workflow_id: str
    outlines: dict[str, SectionOutline] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SectionDraft(BaseModel):
    workflow_id: str
    section: str
    version: int
    generation: int | None = None
    content: str
    claims_used: list[str] = Field(default_factory=list)
    citations_used: list[str] = Field(default_factory=list)
    word_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManuscriptSection(BaseModel):
    workflow_id: str
    section_key: str
    section_order: int
    version: int
    generation: int | None = None
    title: str
    status: str = "draft"
    source: str = "parser"
    boundary_confidence: float = 1.0
    content_hash: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManuscriptBlock(BaseModel):
    workflow_id: str
    section_key: str
    section_version: int
    generation: int | None = None
    block_order: int
    block_type: str
    text: str
    meta_json: str = "{}"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManuscriptAsset(BaseModel):
    workflow_id: str
    asset_key: str
    asset_type: str
    format: str
    content: str
    source_path: str | None = None
    version: int = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManuscriptAssembly(BaseModel):
    workflow_id: str
    assembly_id: str
    target_format: str
    generation: int | None = None
    content: str
    manifest_json: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WritingPrepOutput(BaseModel):
    """Contract between PrepWritingNode and SectionWriterNode.

    Encapsulates all pre-computed context that section writers need,
    so they never re-query the database or re-compute counts.
    """

    workflow_id: str
    citation_catalog: str
    valid_citekeys: list[str] = Field(default_factory=list)
    included_study_citekeys: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    already_completed: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SectionWriteResult(BaseModel):
    """Contract between SectionWriterNode and AssembleManuscriptNode.

    Each section emits a validated SectionWriteResult that carries the
    rendered markdown, structured IR, and citation coverage metadata.
    """

    section_key: str
    content_markdown: str
    structured_draft: StructuredSectionDraft
    cited_keys: list[str] = Field(default_factory=list)
    word_count: int = 0
    validation_retries: int = 0
    validation_issues: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    used_deterministic_fallback: bool = False
    ratchet_meta_json: str = "{}"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssemblyInput(BaseModel):
    """Contract for AssembleManuscriptNode input.

    Aggregates all section results plus global metadata needed to
    render the final manuscript in one deterministic pass.
    """

    workflow_id: str
    section_results: list[SectionWriteResult] = Field(default_factory=list)
    citation_catalog: str = ""
    valid_citekeys: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
