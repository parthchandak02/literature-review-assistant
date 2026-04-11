"""Writing phase models."""

from __future__ import annotations

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


class StructuredManuscriptDraft(BaseModel):
    """Structured manuscript-level intermediate representation."""

    workflow_id: str
    sections: list[StructuredSectionDraft] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
