"""Run-level readiness scorecard for export and finalize gates."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.export.prisma_checklist import validate_prisma
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
    fallback_event_count: int = 0
    blocking_reasons: list[str] = Field(default_factory=list)


async def compute_readiness_scorecard(
    *,
    db_path: str,
    workflow_id: str,
    manuscript_md_path: str,
    manuscript_tex_path: str | None,
    extra_artifact_paths: list[str] | None = None,
    contract_mode: str = "strict",
    abstract_word_limit: int = 250,
) -> ReadinessScorecard:
    """Compute readiness using finalize-phase contracts and DB invariants."""
    checks: list[ReadinessCheck] = []
    blocking: list[str] = []
    fin_ok = False
    prisma_ok = False
    contract_passed = False
    fallback_event_count = 0

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
            abstract_word_limit=abstract_word_limit,
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

        fallback_event_count = await repo.count_fallback_events(workflow_id)
        checks.append(
            ReadinessCheck(
                name="fallback_events",
                ok=fallback_event_count == 0,
                detail=str(fallback_event_count),
            )
        )

    pdf_ok = False
    pdf_detail = "missing"
    md_text = ""
    tex_text = ""
    if manuscript_md_path and Path(manuscript_md_path).exists():
        md_text = Path(manuscript_md_path).read_text(encoding="utf-8")
    if manuscript_tex_path and Path(manuscript_tex_path).exists():
        tex_text = Path(manuscript_tex_path).read_text(encoding="utf-8")
    prisma_check = validate_prisma(tex_text or None, md_text or None)
    prisma_check_ok = prisma_check.passed
    checks.append(
        ReadinessCheck(
            name="prisma_checklist",
            ok=prisma_check_ok,
            detail=(
                f"{prisma_check.reported_count}/{prisma_check.primary_total} reported"
                if prisma_check.items
                else "artifact_missing"
            ),
        )
    )
    if not prisma_check_ok:
        blocking.append(
            f"PRISMA checklist below threshold: {prisma_check.reported_count}/{prisma_check.primary_total} reported"
        )
    if manuscript_tex_path:
        pdf_path = str(Path(manuscript_tex_path).with_suffix(".pdf"))
        pdf_ok = Path(pdf_path).exists()
        pdf_detail = pdf_path if pdf_ok else "missing"
    checks.append(
        ReadinessCheck(
            name="submission_pdf_present",
            ok=pdf_ok,
            detail=pdf_detail,
        )
    )

    ready = fin_ok and prisma_ok and contract_passed and prisma_check_ok
    return ReadinessScorecard(
        workflow_id=workflow_id,
        ready=ready,
        checks=checks,
        contract_passed=contract_passed,
        fallback_event_count=fallback_event_count,
        blocking_reasons=blocking,
    )
