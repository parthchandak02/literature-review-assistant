"""Run-level readiness scorecard for export and finalize gates."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.manuscript.contracts import run_manuscript_contracts
from src.prisma.diagram import build_prisma_counts


class ReadinessCheck(BaseModel):
    """One deterministic readiness probe."""

    name: str
    ok: bool
    detail: str | None = None


class ReadinessScorecard(BaseModel):
    """Aggregate readiness for IEEE export and operational review."""

    workflow_id: str
    ready: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)
    contract_passed: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


async def compute_readiness_scorecard(
    *,
    db_path: str,
    workflow_id: str,
    manuscript_md_path: str,
    manuscript_tex_path: str | None,
    extra_artifact_paths: list[str] | None = None,
    contract_mode: str = "strict",
) -> ReadinessScorecard:
    """Compute readiness using finalize-phase contracts and DB invariants."""
    checks: list[ReadinessCheck] = []
    blocking: list[str] = []
    fin_ok = False
    prisma_ok = False
    contract_passed = False

    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)
        cite_repo = CitationRepository(db)
        checkpoints = await repo.get_checkpoints(workflow_id)
        fin = checkpoints.get("finalize")
        fin_ok = fin == "completed"
        checks.append(
            ReadinessCheck(
                name="finalize_checkpoint",
                ok=fin_ok,
                detail=str(fin) if fin is not None else "missing",
            )
        )
        if not fin_ok:
            blocking.append("finalize checkpoint is not completed")

        dedup = await repo.get_dedup_count(workflow_id)
        if dedup is None:
            dedup = 0
        sids = await repo.get_synthesis_included_paper_ids(workflow_id)
        if not sids:
            sids = await repo.get_included_paper_ids(workflow_id)
        prisma = await build_prisma_counts(repo, workflow_id, dedup, 0, len(sids))
        prisma_ok = bool(prisma.arithmetic_valid)
        checks.append(
            ReadinessCheck(
                name="prisma_arithmetic_valid",
                ok=prisma_ok,
                detail="PRISMA counts are internally consistent" if prisma_ok else "PRISMA counts failed arithmetic check",
            )
        )
        if not prisma_ok:
            blocking.append("PRISMA flow counts are not arithmetically valid")

        contract = await run_manuscript_contracts(
            repository=repo,
            citation_repository=cite_repo,
            workflow_id=workflow_id,
            manuscript_md_path=manuscript_md_path,
            manuscript_tex_path=manuscript_tex_path,
            extra_artifact_paths=extra_artifact_paths,
            mode=contract_mode,
            contract_phase="finalize",
        )
        contract_passed = contract.passed
        checks.append(
            ReadinessCheck(
                name="manuscript_contracts",
                ok=contract_passed,
                detail=f"{len(contract.violations)} violation(s)" if contract.violations else "none",
            )
        )
        if not contract_passed:
            codes = [v.code for v in contract.violations]
            blocking.append(f"manuscript contracts failed: {','.join(codes[:12])}")

    ready = fin_ok and prisma_ok and contract_passed
    return ReadinessScorecard(
        workflow_id=workflow_id,
        ready=ready,
        checks=checks,
        contract_passed=contract_passed,
        blocking_reasons=blocking,
    )
