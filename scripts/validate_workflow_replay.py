from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rich.console import Console
from rich.table import Table

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path
from src.manuscript.contracts import run_manuscript_contracts
from src.models import ValidationCheckRecord, ValidationRunRecord

console = Console()
TOOL_VERSION = "workflow-replay-v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full-pipeline validation checks on an existing workflow.")
    parser.add_argument("--workflow-id", required=True, help="Workflow ID to validate, for example: wf-0046.")
    parser.add_argument(
        "--profile",
        choices=["quick", "standard", "deep"],
        default="standard",
        help="Validation profile depth.",
    )
    parser.add_argument(
        "--run-root",
        default="runs",
        help="Runs root used for registry lookups. Defaults to ./runs",
    )
    parser.add_argument(
        "--db-path",
        default="",
        help="Optional direct runtime.db path, bypassing registry lookup.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit non-zero when any error-level check fails.",
    )
    return parser.parse_args()


async def _resolve_runtime_db(workflow_id: str, run_root: str, db_path_override: str) -> Path:
    if db_path_override.strip():
        return Path(db_path_override).expanduser().resolve()
    roots = candidate_run_roots(run_root, anchor_file=__file__)
    resolved = await resolve_workflow_db_path(workflow_id, roots)
    if not resolved:
        raise RuntimeError(f"Could not resolve runtime.db for {workflow_id} using roots: {roots}")
    return Path(resolved).expanduser().resolve()


async def _count(db, query: str, params: tuple[object, ...]) -> int:
    cur = await db.execute(query, params)
    row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def _add_check(
    repo: WorkflowRepository,
    checks: list[ValidationCheckRecord],
    *,
    validation_run_id: str,
    workflow_id: str,
    phase: str,
    check_name: str,
    status: str,
    severity: str,
    metric_value: float | None,
    details: dict[str, int | float | str | bool],
    source_module: str,
) -> None:
    record = ValidationCheckRecord(
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase=phase,
        check_name=check_name,
        status=status,
        severity=severity,
        metric_value=metric_value,
        details_json=json.dumps(details, sort_keys=True),
        source_module=source_module,
    )
    await repo.save_validation_check(record)
    checks.append(record)


async def _run_checks(
    repo: WorkflowRepository,
    citation_repo: CitationRepository,
    *,
    validation_run_id: str,
    workflow_id: str,
    profile: str,
    runtime_db: Path,
) -> list[ValidationCheckRecord]:
    db = repo.db
    checks: list[ValidationCheckRecord] = []

    search_rows = await _count(db, "SELECT COUNT(*) FROM search_results WHERE workflow_id = ?", (workflow_id,))
    await _add_check(
        repo,
        checks,
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase="phase_2_search",
        check_name="search_rows_present",
        status="pass" if search_rows > 0 else "fail",
        severity="error",
        metric_value=float(search_rows),
        details={"search_rows": search_rows},
        source_module="src/search",
    )

    dedup_count = await _count(
        db, "SELECT COALESCE(MAX(dedup_count), 0) FROM workflows WHERE workflow_id = ?", (workflow_id,)
    )
    raw_records = await _count(
        db, "SELECT COALESCE(SUM(records_retrieved), 0) FROM search_results WHERE workflow_id = ?", (workflow_id,)
    )
    dedup_ok = dedup_count <= raw_records if raw_records > 0 else True
    await _add_check(
        repo,
        checks,
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase="phase_2_search",
        check_name="dedup_count_sane",
        status="pass" if dedup_ok else "fail",
        severity="error",
        metric_value=float(dedup_count),
        details={"dedup_count": dedup_count, "raw_records": raw_records},
        source_module="src/search/strategy.py",
    )

    final_decisions = await _count(
        db,
        "SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = ? AND stage = 'title_abstract'",
        (workflow_id,),
    )
    await _add_check(
        repo,
        checks,
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase="phase_3_screening",
        check_name="dual_screening_rows_present",
        status="pass" if final_decisions > 0 else "fail",
        severity="error",
        metric_value=float(final_decisions),
        details={"dual_screening_rows": final_decisions},
        source_module="src/screening/dual_screener.py",
    )

    included_primary = await _count(
        db,
        """
        SELECT COUNT(*)
        FROM study_cohort_membership
        WHERE workflow_id = ? AND synthesis_eligibility = 'included_primary'
        """,
        (workflow_id,),
    )
    extracted_primary = await _count(
        db,
        """
        SELECT COUNT(*)
        FROM extraction_records er
        JOIN study_cohort_membership scm ON scm.paper_id = er.paper_id
        WHERE er.workflow_id = ?
          AND scm.workflow_id = ?
          AND scm.synthesis_eligibility = 'included_primary'
        """,
        (workflow_id, workflow_id),
    )
    extraction_ok = included_primary == 0 or extracted_primary >= included_primary
    await _add_check(
        repo,
        checks,
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase="phase_4_extraction",
        check_name="extraction_coverage_primary",
        status="pass" if extraction_ok else "warn",
        severity="warn",
        metric_value=float(extracted_primary),
        details={"included_primary": included_primary, "extracted_primary": extracted_primary},
        source_module="src/extraction/extractor.py",
    )

    rob_count = await _count(db, "SELECT COUNT(*) FROM rob_assessments WHERE workflow_id = ?", (workflow_id,))
    casp_count = await _count(db, "SELECT COUNT(*) FROM casp_assessments WHERE workflow_id = ?", (workflow_id,))
    mmat_count = await _count(db, "SELECT COUNT(*) FROM mmat_assessments WHERE workflow_id = ?", (workflow_id,))
    quality_total = rob_count + casp_count + mmat_count
    quality_ok = quality_total > 0 if included_primary > 0 else True
    await _add_check(
        repo,
        checks,
        validation_run_id=validation_run_id,
        workflow_id=workflow_id,
        phase="phase_5_quality",
        check_name="quality_rows_present",
        status="pass" if quality_ok else "warn",
        severity="warn",
        metric_value=float(quality_total),
        details={"rob": rob_count, "casp": casp_count, "mmat": mmat_count},
        source_module="src/quality",
    )

    if profile in {"standard", "deep"}:
        run_dir = runtime_db.parent
        md_path = run_dir / "doc_manuscript.md"
        tex_path = run_dir / "doc_manuscript.tex"
        contracts_ok = True
        violations = 0
        if md_path.exists():
            result = await run_manuscript_contracts(
                repository=repo,
                citation_repository=citation_repo,
                workflow_id=workflow_id,
                manuscript_md_path=str(md_path),
                manuscript_tex_path=str(tex_path) if tex_path.exists() else None,
                extra_artifact_paths=None,
                mode="observe",
            )
            violations = len(result.violations)
            contracts_ok = result.passed
        await _add_check(
            repo,
            checks,
            validation_run_id=validation_run_id,
            workflow_id=workflow_id,
            phase="phase_7_writing",
            check_name="manuscript_contracts",
            status="pass" if contracts_ok else "fail",
            severity="error",
            metric_value=float(violations),
            details={"violations": violations, "manuscript_present": md_path.exists()},
            source_module="src/manuscript/contracts.py",
        )

    if profile == "deep":
        run_dir = runtime_db.parent
        has_tex = (run_dir / "doc_manuscript.tex").exists()
        has_bib = (run_dir / "references.bib").exists()
        has_prisma = (run_dir / "fig_prisma_flow_diagram.svg").exists()
        await _add_check(
            repo,
            checks,
            validation_run_id=validation_run_id,
            workflow_id=workflow_id,
            phase="phase_8_export",
            check_name="export_artifacts_present",
            status="pass" if (has_tex and has_bib) else "warn",
            severity="warn",
            metric_value=None,
            details={"has_tex": has_tex, "has_bib": has_bib, "has_prisma": has_prisma},
            source_module="src/export",
        )
    return checks


def _print_summary(workflow_id: str, runtime_db: Path, validation_run_id: str, checks: list[ValidationCheckRecord]) -> None:
    error_count = sum(1 for c in checks if c.status == "fail" and c.severity == "error")
    warn_count = sum(1 for c in checks if c.status in {"fail", "warn"} and c.severity == "warn")
    table = Table(title=f"Workflow replay validation: {workflow_id}")
    table.add_column("phase")
    table.add_column("check")
    table.add_column("status")
    table.add_column("severity")
    table.add_column("metric")
    for check in checks:
        metric = "" if check.metric_value is None else f"{check.metric_value:.2f}"
        table.add_row(check.phase, check.check_name, check.status, check.severity, metric)
    console.print(f"runtime_db: {runtime_db}")
    console.print(f"validation_run_id: {validation_run_id}")
    console.print(f"errors: {error_count} | warnings: {warn_count}")
    console.print(table)


async def _run() -> int:
    args = _parse_args()
    runtime_db = await _resolve_runtime_db(args.workflow_id, args.run_root, args.db_path)
    if not runtime_db.exists():
        raise FileNotFoundError(f"runtime.db not found: {runtime_db}")
    validation_run_id = f"val-{uuid4().hex[:12]}"
    async with get_db(str(runtime_db)) as db:
        repo = WorkflowRepository(db)
        citation_repo = CitationRepository(db)
        started = datetime.now(UTC)
        await repo.save_validation_run(
            ValidationRunRecord(
                validation_run_id=validation_run_id,
                workflow_id=args.workflow_id,
                profile=args.profile,
                status="running",
                tool_version=TOOL_VERSION,
                started_at=started,
            )
        )
        checks = await _run_checks(
            repo,
            citation_repo,
            validation_run_id=validation_run_id,
            workflow_id=args.workflow_id,
            profile=args.profile,
            runtime_db=runtime_db,
        )
        error_count = sum(1 for c in checks if c.status == "fail" and c.severity == "error")
        status = "passed" if error_count == 0 else "failed"
        summary_json = json.dumps(
            {"errors": error_count, "checks_total": len(checks), "profile": args.profile},
            sort_keys=True,
        )
        await repo.save_validation_run(
            ValidationRunRecord(
                validation_run_id=validation_run_id,
                workflow_id=args.workflow_id,
                profile=args.profile,
                status=status,
                tool_version=TOOL_VERSION,
                summary_json=summary_json,
                started_at=started,
                completed_at=datetime.now(UTC),
            )
        )
        _print_summary(args.workflow_id, runtime_db, validation_run_id, checks)
        if args.fail_on_error and error_count > 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
