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
    content: str
    manifest_json: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
