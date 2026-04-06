"""Canonical manuscript intermediate representation for contract checks.

Structured section drafts (StructuredManuscriptDraft) remain the writer output IR.
This module adds DB-grounded disclosure facts that Markdown and TeX must stay
aligned with, so integrity gates validate facts instead of a single prose regex.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.additional import PRISMACounts


class ManuscriptCanonicalDisclosures(BaseModel):
    """Deterministic disclosure facts derived from the run database.

    Renderers and manuscript contracts should consult this object (or equivalent
    repository queries) rather than inferring flow counts only from prose.
    """

    workflow_id: str
    prisma: PRISMACounts
    use_db_flow_checks: bool = Field(
        description="When True, PRISMA flow disclosures are checked against prisma counts.",
    )
