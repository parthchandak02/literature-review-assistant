"""Writing phase models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


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
