"""Canonical review facts IR — single source for cross-artifact numbers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models import PRISMACounts


class ReviewFacts(BaseModel):
    """Frozen factual snapshot for manuscript, protocol, PRISMA, and exports."""

    workflow_id: str
    prisma: PRISMACounts
    cohens_kappa: float | None = None
    kappa_n: int = 0
    included_study_ids: list[str] = Field(default_factory=list)
    synthesis_included_count: int = 0

    @property
    def total_included(self) -> int:
        return self.prisma.total_included or self.synthesis_included_count

    def validate_cross_artifact(self) -> list[str]:
        """Return human-readable violations when facts disagree internally."""
        issues: list[str] = []
        if self.synthesis_included_count and self.synthesis_included_count != self.total_included:
            issues.append(
                f"synthesis_included_count={self.synthesis_included_count} "
                f"!= prisma.total_included={self.total_included}"
            )
        if not self.prisma.arithmetic_valid:
            issues.append("prisma arithmetic_valid is false")
        return issues


async def build_review_facts(
    repo,
    workflow_id: str,
    *,
    dedup_count: int,
    included_qualitative: int = 0,
    included_quantitative: int = 0,
    cohens_kappa: float | None = None,
    kappa_n: int = 0,
) -> ReviewFacts:
    """Assemble ReviewFacts from repository + PRISMA builder."""
    from src.prisma import build_prisma_counts

    prisma = await build_prisma_counts(
        repo,
        workflow_id,
        dedup_count,
        included_qualitative=included_qualitative,
        included_quantitative=included_quantitative,
    )
    included_ids = sorted(await repo.get_synthesis_included_paper_ids(workflow_id))
    synthesis_count = len(included_ids)
    return ReviewFacts(
        workflow_id=workflow_id,
        prisma=prisma,
        cohens_kappa=cohens_kappa,
        kappa_n=kappa_n,
        included_study_ids=included_ids,
        synthesis_included_count=synthesis_count,
    )
