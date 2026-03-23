"""Canonical cohort resolver for manuscript-facing semantics."""

from __future__ import annotations

from src.db.repositories import WorkflowRepository
from src.models import CohortMembershipRecord

_NON_PRIMARY_DESIGNS = frozenset({"secondary_review", "protocol_only", "non_empirical"})


class IncludedSetResolver:
    """Resolve and persist one canonical included-study cohort."""

    def __init__(self, repository: WorkflowRepository, workflow_id: str):
        self.repository = repository
        self.workflow_id = workflow_id

    async def persist_screening_outcome(
        self,
        paper_id: str,
        *,
        fulltext_decision: str,
        exclusion_reason_code: str | None = None,
        source_phase: str = "phase_3_screening",
    ) -> None:
        screening_status = "included" if fulltext_decision in {"include", "uncertain"} else "excluded"
        fulltext_status = "not_retrieved" if exclusion_reason_code == "no_full_text" else "assessed"
        synthesis_eligibility = "pending" if screening_status == "included" else "excluded_screening"
        await self.repository.upsert_cohort_membership(
            CohortMembershipRecord(
                workflow_id=self.workflow_id,
                paper_id=paper_id,
                screening_status=screening_status,
                fulltext_status=fulltext_status,
                synthesis_eligibility=synthesis_eligibility,
                exclusion_reason_code=(
                    None
                    if screening_status == "included"
                    else (exclusion_reason_code or "screening_excluded")
                ),
                source_phase=source_phase,
            )
        )

    async def persist_extraction_outcome(
        self,
        paper_id: str,
        *,
        primary_study_status: str,
        extraction_failed: bool,
        source_phase: str = "phase_4_extraction_quality",
    ) -> None:
        if primary_study_status in _NON_PRIMARY_DESIGNS:
            eligibility = "excluded_non_primary"
            reason = primary_study_status
        elif extraction_failed:
            eligibility = "excluded_failed_extraction"
            reason = "failed_extraction"
        else:
            eligibility = "included_primary"
            reason = None

        await self.repository.upsert_cohort_membership(
            CohortMembershipRecord(
                workflow_id=self.workflow_id,
                paper_id=paper_id,
                screening_status="included",
                fulltext_status="assessed",
                synthesis_eligibility=eligibility,
                exclusion_reason_code=reason,
                source_phase=source_phase,
            )
        )

    async def get_synthesis_included_ids(self) -> set[str]:
        return await self.repository.get_synthesis_included_paper_ids(self.workflow_id)

