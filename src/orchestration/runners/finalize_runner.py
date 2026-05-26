"""Runner helper for FinalizeNode."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic_graph import GraphRunContext

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.db.workflow_registry import update_status as update_registry_status
from src.models import StepStatus, WorkflowStepRecord
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.runtime import rc_print as helper_rc_print
from src.orchestration.helpers.step_journal import journal_step_complete, journal_step_start
from src.orchestration.helpers.writing_manuscript import refresh_manuscript_export_artifacts
from src.orchestration.state import ReviewState
from src.protocol.generator import ProtocolGenerator

logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


def _rc_print(rc, message: object) -> None:
    helper_rc_print(rc, message)


async def run_finalize_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> dict:
    """Generate run summary, LaTeX, PROSPERO docx, and submission package.

    Returns the summary dict; the calling node wraps it in ``End()``.
    """
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("finalize", "Writing run summary...")

    _finalize_step: WorkflowStepRecord | None = None
    try:
        async with get_db(state.db_path) as _jdb:
            _finalize_step = await journal_step_start(
                WorkflowRepository(_jdb),
                state.workflow_id,
                "finalize",
                "finalize_phase",
            )
    except Exception:
        pass

    _finalize_errors: list[str] = []

    _mmd_path = state.artifacts.get("manuscript_md", "")
    if _mmd_path and os.path.isfile(_mmd_path):
        try:
            await refresh_manuscript_export_artifacts(
                state,
                strict_export=False,
                persist_assembly=True,
            )
            logger.info("FinalizeNode: wrote doc_manuscript.tex and references.bib")
        except Exception as _tex_err:  # noqa: BLE001
            logger.warning("FinalizeNode: LaTeX artifact generation failed (non-fatal): %s", _tex_err)

    if state.review and state.output_dir:
        try:
            from src.export.docx_exporter import generate_docx as _generate_docx
            from src.models import ProsperoRunData

            _proto_gen = ProtocolGenerator(output_dir=state.output_dir)
            _placeholder_fields = _proto_gen.validate_prospero_inputs(state.review)
            if _placeholder_fields:
                _msg = "PROSPERO preflight warning: placeholder-like values detected in " + ", ".join(
                    sorted(set(_placeholder_fields))
                )
                logger.warning("FinalizeNode: %s", _msg)
                if rc and hasattr(rc, "log_status"):
                    rc.log_status(_msg)
            _protocol_doc = _proto_gen.generate(state.workflow_id, state.review, state.settings)
            _protocol_md = _proto_gen.render_markdown(_protocol_doc, state.review)
            _protocol_md_path = _proto_gen.write_markdown(state.workflow_id, _protocol_md)
            state.artifacts["protocol"] = str(_protocol_md_path)
            _protocol = _protocol_doc
            _synthesis_method: str = _protocol.planned_synthesis_method
            _included_ids: set[str] = set()
            try:
                async with get_db(state.db_path) as _inc_db:
                    _inc_repo = WorkflowRepository(_inc_db)
                    _included_ids = await _inc_repo.get_synthesis_included_paper_ids(state.workflow_id)
            except Exception:
                _included_ids = set()
            if not _included_ids:
                _included_ids = {str(p.paper_id) for p in (state.included_papers or []) if getattr(p, "paper_id", "")}
            _fulltext_ids: set[str] = set()
            _manifest_path = Path(state.artifacts.get("papers_manifest", ""))
            if _manifest_path.exists():
                try:
                    _manifest = json.loads(_manifest_path.read_text(encoding="utf-8"))
                    for _pid, _entry in (_manifest or {}).items():
                        if (_entry or {}).get("file_path"):
                            _fulltext_ids.add(str(_pid))
                except Exception as _manifest_err:  # noqa: BLE001
                    logger.warning(
                        "FinalizeNode: could not derive fulltext IDs from papers manifest: %s",
                        _manifest_err,
                    )
            _fulltext_retrieved = len(_fulltext_ids.intersection(_included_ids)) if _included_ids else 0
            if _fulltext_retrieved <= 0:
                if _manifest_path.exists():
                    try:
                        _manifest = json.loads(_manifest_path.read_text(encoding="utf-8"))
                        _fulltext_retrieved = sum(1 for _entry in _manifest.values() if (_entry or {}).get("file_path"))
                    except Exception as _manifest_err:  # noqa: BLE001
                        logger.warning(
                            "FinalizeNode: could not derive fulltext count from papers manifest: %s",
                            _manifest_err,
                        )
                if _fulltext_retrieved <= 0:
                    _papers_dir = Path(state.output_dir) / "papers"
                    if _papers_dir.exists():
                        _fulltext_retrieved = sum(
                            1
                            for _pf in _papers_dir.iterdir()
                            if _pf.suffix in {".pdf", ".txt"} and _pf.stat().st_size > 0
                        )

            _run_data = ProsperoRunData(
                search_counts=state.search_counts,
                search_queries=state.search_queries,
                included_count=len(_included_ids),
                fulltext_retrieved_count=max(0, _fulltext_retrieved),
                run_id=state.run_id,
                synthesis_method=_synthesis_method,
                other_methods_searched=sorted(
                    {
                        str(name)
                        for name in (state.search_counts or {}).keys()
                        if str(name) not in {str(db) for db in state.review.resolved_target_databases()}
                    }
                ),
            )
            _prospero_md = _proto_gen.render_prospero_markdown(_protocol, state.review, _run_data)
            _prospero_md_path = _proto_gen.write_prospero_markdown(_prospero_md)
            state.artifacts["prospero_form_md"] = str(_prospero_md_path)
            _prospero_docx_path = Path(state.output_dir) / "doc_prospero_registration.docx"
            _generate_docx(_prospero_md_path, _prospero_docx_path)
            state.artifacts["prospero_form"] = str(_prospero_docx_path)
            logger.info("FinalizeNode: wrote doc_prospero_registration.md and .docx")
        except Exception as _pros_err:  # noqa: BLE001
            logger.warning("FinalizeNode: PROSPERO DOCX generation failed (non-fatal): %s", _pros_err)

    if state.workflow_id and state.run_root:
        try:
            from src.export.submission_packager import package_submission as _pkg_sub

            await _pkg_sub(state.workflow_id, state.run_root)
            logger.info("FinalizeNode: submission/ pre-populated")
        except Exception as _sub_err:  # noqa: BLE001
            logger.warning("FinalizeNode: submission pre-packaging failed (non-fatal): %s", _sub_err)

    run_summary_key = "run_summary"
    filtered_artifacts = {k: v for k, v in state.artifacts.items() if k == run_summary_key or os.path.isfile(v)}
    _canonical_included_count = len(state.included_papers)
    try:
        async with get_db(state.db_path) as _cohort_db:
            _cohort_repo = WorkflowRepository(_cohort_db)
            _canonical_ids = await _cohort_repo.get_synthesis_included_paper_ids(state.workflow_id)
            if _canonical_ids:
                _canonical_included_count = len(_canonical_ids)
    except Exception:
        pass
    summary: dict[str, str | int | float | bool | dict[str, int] | dict[str, str]] = {
        "run_id": state.run_id,
        "workflow_id": state.workflow_id,
        "status": "done",
        "log_dir": state.log_dir,
        "output_dir": state.output_dir,
        "search_counts": state.search_counts,
        "search_queries": state.search_queries,
        "dedup_count": state.dedup_count,
        "connector_init_failures": state.connector_init_failures,
        "included_papers": _canonical_included_count,
        "extraction_records": len(state.extraction_records),
        "artifacts": filtered_artifacts,
        "rag_sections_total": state.rag_sections_total,
        "rag_sections_success": state.rag_sections_success,
        "rag_sections_empty": state.rag_sections_empty,
        "rag_sections_error": state.rag_sections_error,
        "rag_sections_skipped": state.rag_sections_skipped,
        "rag_threshold_breached": state.rag_threshold_breached,
    }
    _manuscript_path = state.artifacts.get("manuscript_md", "")
    if _manuscript_path and os.path.isfile(_manuscript_path):
        try:
            _manuscript_text = Path(_manuscript_path).read_text(encoding="utf-8")
            async with get_db(state.db_path) as _cit_db:
                _ledger = CitationLedger(CitationRepository(_cit_db))
                _validation = await _ledger.validate_manuscript(_manuscript_text)
                _lineage_invalid = bool(_validation.unresolved_claims or _validation.unresolved_citations)
                summary["citation_lineage"] = {
                    "valid": not _lineage_invalid,
                    "unresolved_claim_count": len(_validation.unresolved_claims),
                    "unresolved_citation_count": len(_validation.unresolved_citations),
                }
                summary["citation_lineage_valid"] = not _lineage_invalid
        except Exception as _cit_err:
            logger.warning("Citation lineage check skipped: %s", _cit_err)

    async with get_db(state.db_path) as _cost_db:
        _cost_row = await (await _cost_db.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_records")).fetchone()
        summary["total_cost"] = float(_cost_row[0]) if _cost_row else 0.0

    if _finalize_errors:
        summary["status"] = "failed"
        summary["error"] = "; ".join(_finalize_errors)
    Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    await update_registry_status(state.run_root, state.workflow_id, "failed" if _finalize_errors else "completed")
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.update_workflow_status(state.workflow_id, "failed" if _finalize_errors else "completed")
        await repo.save_checkpoint(
            state.workflow_id,
            "finalize",
            papers_processed=summary.get("included_papers", 0),
            status="blocked" if _finalize_errors else "completed",
        )
    if rc and rc.verbose:
        _rc_print(rc, f"  Run summary: {state.artifacts['run_summary']}")
        _rc_print(rc, f"  Output dir: {state.output_dir}")
    if rc:
        if _finalize_errors:
            rc.emit_phase_done("finalize", {"error": "; ".join(_finalize_errors)})
        else:
            rc.emit_phase_done("finalize")
    if _finalize_errors:
        summary["status"] = "failed"
        summary["error"] = "; ".join(_finalize_errors)

    if _finalize_step:
        try:
            async with get_db(state.db_path) as _jdb:
                _f_status = StepStatus.FAILED if _finalize_errors else StepStatus.SUCCEEDED
                _f_err = "; ".join(_finalize_errors) if _finalize_errors else None
                await journal_step_complete(
                    WorkflowRepository(_jdb),
                    _finalize_step,
                    status=_f_status,
                    error_message=_f_err,
                )
        except Exception:
            logger.warning("FinalizeNode: step journal write failed", exc_info=True)

    return summary
