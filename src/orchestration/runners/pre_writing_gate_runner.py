"""Runner for PreWritingGateNode."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import update_status as update_registry_status
from src.models import FailureCategory, RecoveryAction, StepStatus
from src.models.workflow import WorkflowRunResult
from src.orchestration.helpers.pre_writing_gate import (
    compute_pre_writing_gate_report,
    count_prior_pre_writing_failures,
    persist_pre_writing_gate_validation,
    rewind_pre_writing_phase,
)
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.step_journal import journal_step_complete, journal_step_start
from src.orchestration.state import ReviewState

logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


async def run_pre_writing_gate_node(state: ReviewState, ctx: GraphRunContext[ReviewState]):
    """Validate canonical prerequisites before writing and rewind automatically when safe.

    Returns the next node instance (WritingNode, ExtractionQualityNode,
    EmbeddingNode, SynthesisNode, or KnowledgeGraphNode). When blocking checks remain
    and rewinds are exhausted, marks the workflow failed and returns ``End`` with a
    GATE_BLOCKED ``WorkflowRunResult`` (gate ``pre_writing``).
    """
    rc = _rc(state)
    if rc:
        rc.emit_phase_start(
            "phase_5c_pre_writing_gate",
            f"Validating writing prerequisites ({len(state.included_papers)} papers)...",
            total=5,
        )

    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)

        policy = await repository.get_or_create_recovery_policy(
            state.workflow_id,
            "phase_5c_pre_writing_gate",
            "pre_writing_validation",
            max_retries=0,
            max_rewinds=1,
        )

        gate_step = await journal_step_start(
            repository,
            state.workflow_id,
            "phase_5c_pre_writing_gate",
            "pre_writing_validation",
            max_attempts=policy.max_rewinds + 1,
        )
        gate_step.attempt_number = policy.current_rewinds + 1

        prior_failures = await count_prior_pre_writing_failures(db, state.workflow_id)
        report = await compute_pre_writing_gate_report(
            state=state,
            repository=repository,
            db=db,
            attempt_number=prior_failures + 1,
        )
        await persist_pre_writing_gate_validation(repository=repository, report=report)

        if report.ready:
            await journal_step_complete(repository, gate_step)
            await repository.save_checkpoint(
                state.workflow_id,
                "phase_5c_pre_writing_gate",
                papers_processed=len(state.included_papers),
                status="completed",
            )
            if rc:
                rc.emit_phase_done(
                    "phase_5c_pre_writing_gate",
                    {"ready": True, "attempt": report.attempt_number},
                )
            from src.orchestration.nodes.writing import WritingNode

            return WritingNode()

        await repository.save_checkpoint(
            state.workflow_id,
            "phase_5c_pre_writing_gate",
            papers_processed=len(state.included_papers),
            status="blocked",
        )

        if report.rewind_phase and not policy.rewinds_exhausted:
            await repository.increment_rewind_count(
                state.workflow_id,
                "phase_5c_pre_writing_gate",
                "pre_writing_validation",
            )
            await journal_step_complete(
                repository,
                gate_step,
                status=StepStatus.FAILED,
                error_message="; ".join(report.blocking_reasons),
                failure_category=FailureCategory.REWINDABLE,
                recovery_action=RecoveryAction.REWIND,
            )
            await rewind_pre_writing_phase(
                repository=repository,
                workflow_id=state.workflow_id,
                rewind_phase=report.rewind_phase,
            )
            if report.rewind_phase == "phase_4_extraction_quality":
                state.extraction_records = []
            if rc:
                rc.log_status(
                    f"Pre-writing gate rewinding to {report.rewind_phase} "
                    f"({policy.status_label()}): {'; '.join(report.blocking_reasons)}"
                )
                rc.emit_phase_done(
                    "phase_5c_pre_writing_gate",
                    {
                        "ready": False,
                        "rewind_phase": report.rewind_phase,
                        "attempt": report.attempt_number,
                    },
                )
            if report.rewind_phase == "phase_4_extraction_quality":
                from src.orchestration.nodes.extraction_quality import ExtractionQualityNode

                return ExtractionQualityNode()
            if report.rewind_phase == "phase_4b_embedding":
                from src.orchestration.embedding_node import EmbeddingNode

                return EmbeddingNode()
            if report.rewind_phase == "phase_5_synthesis":
                from src.orchestration.nodes.synthesis import SynthesisNode

                return SynthesisNode()
            from src.orchestration.knowledge_graph_node import KnowledgeGraphNode

            return KnowledgeGraphNode()

        error_message = "pre-writing gate blocked manuscript generation: " + "; ".join(report.blocking_reasons)
        await journal_step_complete(
            repository,
            gate_step,
            status=StepStatus.FAILED,
            error_message="; ".join(report.blocking_reasons),
            failure_category=FailureCategory.TERMINAL,
            recovery_action=RecoveryAction.ABORT,
        )
        await repository.update_workflow_status(state.workflow_id, "failed")

    await update_registry_status(state.run_root, state.workflow_id, "failed")
    logger.error("PreWritingGateNode: %s", error_message)

    summary = {
        "workflow_id": state.workflow_id,
        "status": "failed",
        "gate_blocked": True,
        "error": error_message,
        "gate": "pre_writing",
        "phase": "phase_5c_pre_writing_gate",
        "db_path": state.db_path,
        "output_dir": state.output_dir or None,
        "blocking_reasons": list(report.blocking_reasons),
        "rewind_phase": report.rewind_phase,
        "attempt": report.attempt_number,
        "rewinds_exhausted": True,
    }
    summary_path = state.artifacts.get("run_summary")
    if summary_path:
        try:
            Path(summary_path).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        except OSError as exc:
            logger.warning("PreWritingGateNode: could not write run summary: %s", exc)

    if rc:
        rc.log_status(error_message)
        rc.emit_phase_done(
            "phase_5c_pre_writing_gate",
            {
                "ready": False,
                "rewind_phase": report.rewind_phase,
                "attempt": report.attempt_number,
                "blocked": True,
                "error": error_message,
            },
        )
    return End(WorkflowRunResult.from_summary(summary))
