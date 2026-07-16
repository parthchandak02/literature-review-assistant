from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from src.db.repositories import WorkflowRepository
from src.export.markdown_refs import is_extraction_failed
from src.models import (
    PreWritingGateCheck,
    PreWritingGateReport,
    ValidationCheckRecord,
    ValidationRunRecord,
)
from src.orchestration.phase_catalog import PRE_WRITING_PHASE_ORDER
from src.orchestration.state import ReviewState
from src.prisma import build_prisma_counts
from src.writing.orchestration import _citation_entries_from_papers


def pre_writing_phases_from(start_phase: str) -> list[str]:
    try:
        idx = PRE_WRITING_PHASE_ORDER.index(start_phase)
    except ValueError:
        return []
    return list(PRE_WRITING_PHASE_ORDER[idx:])


def select_pre_writing_rewind_phase(phases: list[str]) -> str | None:
    phase_set = set(phases)
    for phase in PRE_WRITING_PHASE_ORDER:
        if phase in phase_set:
            return phase
    return None


async def count_prior_pre_writing_failures(db, workflow_id: str) -> int:
    cursor = await db.execute(
        """
        SELECT COUNT(*)
        FROM validation_runs
        WHERE workflow_id = ?
          AND profile = 'pre_writing_gate'
          AND status = 'failed'
        """,
        (workflow_id,),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def compute_pre_writing_gate_report(
    *,
    state: ReviewState,
    repository: WorkflowRepository,
    db,
    attempt_number: int,
) -> PreWritingGateReport:
    included_ids = await repository.get_synthesis_included_paper_ids(state.workflow_id)
    if not included_ids:
        included_ids = await repository.get_included_paper_ids(state.workflow_id)

    included_papers = state.included_papers
    if not included_papers and included_ids:
        included_papers = await repository.get_papers_by_ids(included_ids)

    records = state.extraction_records or await repository.load_extraction_records(state.workflow_id)
    extraction_records = [record for record in records if not is_extraction_failed(record)]
    extraction_ids = {str(record.paper_id) for record in extraction_records if record.paper_id}

    rob2_rows, robins_i_rows = await repository.load_rob_assessments(state.workflow_id)
    casp_rows = await repository.load_casp_assessments(state.workflow_id)
    mmat_rows = await repository.load_mmat_assessments(state.workflow_id)
    quality_ids = {
        str(assessment.paper_id)
        for assessment in [*rob2_rows, *robins_i_rows, *casp_rows, *mmat_rows]
        if getattr(assessment, "paper_id", None)
    }

    chunk_cursor = await db.execute(
        """
        SELECT DISTINCT paper_id
        FROM paper_chunks_meta
        WHERE workflow_id = ?
        """,
        (state.workflow_id,),
    )
    chunk_rows = await chunk_cursor.fetchall()
    chunk_ids = {str(row[0]) for row in chunk_rows if row and row[0]}

    dedup_count = state.dedup_count
    if dedup_count <= 0:
        dedup_count = int(await repository.get_dedup_count(state.workflow_id) or 0)
    prisma = await build_prisma_counts(
        repository,
        state.workflow_id,
        dedup_count,
        included_qualitative=0,
        included_quantitative=len(included_ids),
    )

    citation_entries = _citation_entries_from_papers(included_papers)
    citekeys = [citekey for citekey, _paper in citation_entries]
    placeholder_citekeys = [citekey for citekey in citekeys if citekey.startswith("Ref")]

    missing_extraction = sorted(included_ids - extraction_ids)
    missing_quality = sorted(extraction_ids - quality_ids)
    missing_chunks = sorted(extraction_ids - chunk_ids)
    citation_catalog_ok = len(citekeys) == len(included_papers) and len(set(citekeys)) == len(citekeys)

    checks: list[PreWritingGateCheck] = []
    blocking_reasons: list[str] = []
    rewind_candidates: list[str] = []

    checks.append(
        PreWritingGateCheck(
            name="prisma_arithmetic_valid",
            ok=bool(prisma.arithmetic_valid),
            detail="valid" if prisma.arithmetic_valid else "invalid",
            rewind_phase=None if prisma.arithmetic_valid else "phase_4_extraction_quality",
        )
    )
    if not prisma.arithmetic_valid:
        blocking_reasons.append("PRISMA arithmetic is inconsistent before writing")
        rewind_candidates.append("phase_4_extraction_quality")

    checks.append(
        PreWritingGateCheck(
            name="extraction_coverage",
            ok=not missing_extraction,
            detail=f"missing={len(missing_extraction)}",
            rewind_phase=None if not missing_extraction else "phase_4_extraction_quality",
        )
    )
    if missing_extraction:
        blocking_reasons.append(f"missing extraction records for {len(missing_extraction)} included papers")
        rewind_candidates.append("phase_4_extraction_quality")

    checks.append(
        PreWritingGateCheck(
            name="quality_coverage",
            ok=not missing_quality,
            detail=f"missing={len(missing_quality)}",
            rewind_phase=None if not missing_quality else "phase_4_extraction_quality",
        )
    )
    if missing_quality:
        blocking_reasons.append(f"missing quality assessments for {len(missing_quality)} extracted papers")
        rewind_candidates.append("phase_4_extraction_quality")

    checks.append(
        PreWritingGateCheck(
            name="rag_chunk_coverage",
            ok=not missing_chunks,
            detail=f"missing={len(missing_chunks)}",
            rewind_phase=None if not missing_chunks else "phase_4b_embedding",
        )
    )
    if missing_chunks:
        blocking_reasons.append(f"missing RAG chunks for {len(missing_chunks)} extracted papers")
        rewind_candidates.append("phase_4b_embedding")

    checks.append(
        PreWritingGateCheck(
            name="citation_catalog_integrity",
            ok=citation_catalog_ok,
            detail=f"generated={len(citekeys)} placeholder_keys={len(placeholder_citekeys)}",
            rewind_phase=None if citation_catalog_ok else "phase_4_extraction_quality",
        )
    )
    if not citation_catalog_ok:
        blocking_reasons.append("citation catalog generation is not one-to-one with included papers")
        rewind_candidates.append("phase_4_extraction_quality")

    return PreWritingGateReport(
        workflow_id=state.workflow_id,
        ready=not blocking_reasons,
        checks=checks,
        blocking_reasons=blocking_reasons,
        rewind_phase=select_pre_writing_rewind_phase(rewind_candidates),
        attempt_number=attempt_number,
    )


async def persist_pre_writing_gate_validation(
    *,
    repository: WorkflowRepository,
    report: PreWritingGateReport,
) -> None:
    now = datetime.now(UTC)
    validation_run_id = f"prewrite-{uuid4().hex}"
    await repository.save_validation_run(
        ValidationRunRecord(
            validation_run_id=validation_run_id,
            workflow_id=report.workflow_id,
            profile="pre_writing_gate",
            status="passed" if report.ready else "failed",
            tool_version="pre_writing_gate_v1",
            summary_json=json.dumps(
                {
                    "ready": report.ready,
                    "rewind_phase": report.rewind_phase,
                    "blocking_reasons": report.blocking_reasons,
                    "attempt_number": report.attempt_number,
                },
                sort_keys=True,
            ),
            started_at=now,
            completed_at=now,
        )
    )
    for check in report.checks:
        await repository.save_validation_check(
            ValidationCheckRecord(
                validation_run_id=validation_run_id,
                workflow_id=report.workflow_id,
                phase="phase_5c_pre_writing_gate",
                check_name=check.name,
                status="pass" if check.ok else "fail",
                severity="error" if check.blocking else "warn",
                metric_value=None,
                details_json=json.dumps(
                    {"detail": check.detail, "rewind_phase": check.rewind_phase},
                    sort_keys=True,
                ),
                source_module="orchestration.helpers.pre_writing_gate",
                paper_id=None,
            )
        )


async def rewind_pre_writing_phase(
    *,
    repository: WorkflowRepository,
    workflow_id: str,
    rewind_phase: str,
) -> None:
    phases_to_clear = pre_writing_phases_from(rewind_phase)
    if phases_to_clear:
        await repository.delete_checkpoints_for_phases(workflow_id, phases_to_clear)
    await repository.rollback_phase_data(workflow_id, rewind_phase)
