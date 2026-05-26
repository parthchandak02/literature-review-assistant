"""Runner helper for ManuscriptAuditNode."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.db.workflow_registry import update_status as update_registry_status
from src.llm.provider import LLMProvider
from src.manuscript.contracts import run_manuscript_contracts
from src.manuscript.reviewer import run_manuscript_audit, serialize_audit_context, serialize_contract_summary
from src.orchestration.helpers.manuscript_gate import (
    collect_manuscript_gate_failure_reasons,
    manuscript_gate_blocks_workflow,
    resolve_manuscript_gate_action,
)
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.writing_manuscript import refresh_manuscript_export_artifacts
from src.orchestration.state import ReviewState
from src.prisma import build_prisma_counts

logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


async def run_manuscript_audit_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> End[dict] | None:
    """Run bounded profile-based manuscript audit before finalize.

    Returns ``End(summary)`` when the manuscript gate blocks the workflow,
    otherwise returns ``None`` (caller should continue to FinalizeNode).
    """
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("phase_7_audit", "Running final manuscript audit...")
    assert state.review is not None
    assert state.settings is not None
    manuscript_path = state.artifacts.get("manuscript_md", "")
    if not manuscript_path or not os.path.isfile(manuscript_path):
        if rc:
            rc.emit_phase_done("phase_7_audit", {"status": "skipped", "reason": "manuscript_missing"})
        async with get_db(state.db_path) as db:
            await WorkflowRepository(db).save_checkpoint(
                state.workflow_id,
                "phase_7_audit",
                papers_processed=0,
                status="completed",
            )
        return None

    mode = str(getattr(state.settings.gates, "manuscript_audit_mode", "strict"))
    audit_gate_mode = str(getattr(state.settings.gates, "audit_gate_mode", "advisory"))
    contract_mode = str(getattr(state.settings.gates, "manuscript_contract_mode", "strict"))
    blocked_checkpoint_status = "partial"
    blocked_papers_processed = 0
    try:
        manuscript_text = Path(manuscript_path).read_text(encoding="utf-8")
        phase7_tex_path: str | None = None
        try:
            phase7_tex_path = await refresh_manuscript_export_artifacts(
                state,
                strict_export=contract_mode == "strict",
            )
        except Exception as tex_err:
            logger.warning("ManuscriptAuditNode: fresh LaTeX export unavailable; continuing without tex: %s", tex_err)
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            citation_repo = CitationRepository(db)
            provider = LLMProvider(state.settings, repository)
            contract_result = await run_manuscript_contracts(
                repository=repository,
                citation_repository=citation_repo,
                workflow_id=state.workflow_id,
                manuscript_md_path=manuscript_path,
                manuscript_tex_path=phase7_tex_path if phase7_tex_path and os.path.isfile(phase7_tex_path) else None,
                extra_artifact_paths=[
                    state.artifacts.get("protocol", ""),
                    state.artifacts.get("prospero_form_md", ""),
                ],
                mode=contract_mode,
                contract_phase="phase_7_audit",
                abstract_word_limit=state.settings.ieee_export.max_abstract_words,
                abstract_minimum_words=state.settings.writing.abstract_trim_floor_words,
                review_config=state.review,
            )
            contract_summary = {
                "mode": contract_result.mode,
                "passed": contract_result.passed,
                "violations": [v.model_dump() for v in contract_result.violations],
            }
            dedup_count = int(await repository.get_dedup_count(state.workflow_id) or 0)
            synthesis_ids = await repository.get_synthesis_included_paper_ids(state.workflow_id)
            if not synthesis_ids:
                synthesis_ids = await repository.get_included_paper_ids(state.workflow_id)
            prisma_counts = await build_prisma_counts(
                repository,
                state.workflow_id,
                dedup_count,
                included_qualitative=0,
                included_quantitative=len(synthesis_ids),
            )
            rob2_rows, robins_i_rows = await repository.load_rob_assessments(state.workflow_id)
            casp_rows = await repository.load_casp_assessments(state.workflow_id)
            mmat_rows = await repository.load_mmat_assessments(state.workflow_id)
            extraction_cursor = await db.execute(
                "SELECT COUNT(*) FROM extraction_records WHERE workflow_id = ?",
                (state.workflow_id,),
            )
            extraction_row = await extraction_cursor.fetchone()
            extraction_count = int(extraction_row[0] or 0) if extraction_row else 0
            grade_cursor = await db.execute(
                "SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?",
                (state.workflow_id,),
            )
            grade_row = await grade_cursor.fetchone()
            grade_count = int(grade_row[0] or 0) if grade_row else 0
            audit_context = {
                "review": {
                    "research_question": state.review.research_question,
                    "review_type": state.review.review_type.value,
                    "domain": state.review.domain,
                    "scope": state.review.scope,
                    "expert_topic": state.review.expert_topic(),
                    "target_databases": list(state.review.resolved_target_databases()),
                    "date_range": {
                        "start": state.review.date_range_start,
                        "end": state.review.date_range_end,
                    },
                    "protocol_registered": bool(state.review.protocol.registered),
                    "search_limitation": state.review.search_limitation or "",
                    "domain_brief_lines": state.review.domain_brief_lines(),
                    "methodology_expectations": state.review.methodology_expectations(limit=10),
                },
                "db_backed_counts": {
                    "deduplicated_records": dedup_count,
                    "included_primary_studies": len(synthesis_ids),
                    "extraction_records": extraction_count,
                    "grade_assessments": grade_count,
                    "fallback_events_current_generation": await repository.count_fallback_events(state.workflow_id),
                },
                "quality_assessment_counts": {
                    "rob2": len(rob2_rows),
                    "robins_i": len(robins_i_rows),
                    "casp": len(casp_rows),
                    "mmat": len(mmat_rows),
                },
                "prisma_counts": prisma_counts.model_dump(mode="json"),
                "manuscript_stats": {
                    "word_count": len(manuscript_text.split()),
                    "char_count": len(manuscript_text),
                },
            }
            audit_result, findings = await run_manuscript_audit(
                workflow_id=state.workflow_id,
                review=state.review,
                settings=state.settings,
                manuscript_text=manuscript_text,
                contract_summary_json=serialize_contract_summary(contract_summary),
                audit_context_json=serialize_audit_context(audit_context),
                provider=provider,
            )
            gate_failure_reasons = collect_manuscript_gate_failure_reasons(contract_result, audit_result)
            gate_blocked = len(gate_failure_reasons) > 0
            gate_action = resolve_manuscript_gate_action(audit_gate_mode, gate_blocked)
            await repository.save_manuscript_audit(
                audit_result,
                findings,
                contract_result=contract_result,
                gate_blocked=gate_blocked,
                gate_mode=audit_gate_mode,
                gate_action=gate_action,
                gate_failure_reasons=gate_failure_reasons,
            )

            if manuscript_gate_blocks_workflow(audit_gate_mode, gate_blocked):
                blocked_checkpoint_status = "blocked"
                blocked_papers_processed = len(findings)
                filtered_artifacts = {
                    k: v for k, v in state.artifacts.items() if k == "run_summary" or os.path.isfile(v)
                }
                error_message = "; ".join(gate_failure_reasons)
                summary = {
                    "workflow_id": state.workflow_id,
                    "status": "failed",
                    "error": error_message,
                    "gate": "manuscript_audit",
                    "phase": "phase_7_audit",
                    "output_dir": state.output_dir,
                    "artifacts": filtered_artifacts,
                    "manuscript_contract": contract_summary,
                    "manuscript_audit": {
                        **audit_result.model_dump(mode="json"),
                        "gate_blocked": True,
                        "gate_mode": audit_gate_mode,
                        "gate_action": gate_action,
                        "gate_failure_reasons": gate_failure_reasons,
                    },
                }
                Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
                await repository.save_checkpoint(
                    state.workflow_id,
                    "phase_7_audit",
                    papers_processed=blocked_papers_processed,
                    status=blocked_checkpoint_status,
                )
                await repository.update_workflow_status(state.workflow_id, "failed")
                await update_registry_status(state.run_root, state.workflow_id, "failed")
                if rc:
                    rc.emit_phase_done(
                        "phase_7_audit",
                        {
                            "passed": audit_result.passed,
                            "verdict": audit_result.verdict,
                            "findings": audit_result.total_findings,
                            "blocking": audit_result.blocking_count,
                            "profiles": list(audit_result.selected_profiles),
                            "cost_usd": audit_result.total_cost_usd,
                            "mode": mode,
                            "gate_mode": audit_gate_mode,
                            "contract_mode": contract_mode,
                            "contract_passed": contract_result.passed,
                            "gate_blocked": True,
                            "gate_action": gate_action,
                            "gate_failure_reasons": gate_failure_reasons,
                        },
                    )
                return End(summary)

            await repository.save_checkpoint(
                state.workflow_id,
                "phase_7_audit",
                papers_processed=len(findings),
                status="completed",
            )
            if rc:
                rc.emit_phase_done(
                    "phase_7_audit",
                    {
                        "passed": audit_result.passed,
                        "verdict": audit_result.verdict,
                        "findings": audit_result.total_findings,
                        "blocking": audit_result.blocking_count,
                        "profiles": list(audit_result.selected_profiles),
                        "cost_usd": audit_result.total_cost_usd,
                        "mode": mode,
                        "gate_mode": audit_gate_mode,
                        "gate_blocked": gate_blocked,
                        "gate_action": gate_action,
                        "gate_failure_reasons": gate_failure_reasons,
                    },
                )
        return None
    except Exception:
        async with get_db(state.db_path) as db:
            await WorkflowRepository(db).save_checkpoint(
                state.workflow_id,
                "phase_7_audit",
                papers_processed=blocked_papers_processed,
                status=blocked_checkpoint_status,
            )
        raise
