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
