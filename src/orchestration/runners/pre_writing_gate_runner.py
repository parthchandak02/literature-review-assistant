"""Runner for PreWritingGateNode."""

from __future__ import annotations

import logging

from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import FailureCategory, RecoveryAction, StepStatus
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
    EmbeddingNode, SynthesisNode, or KnowledgeGraphNode), or raises RuntimeError.
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

        await journal_step_complete(
            repository,
            gate_step,
            status=StepStatus.FAILED,
            error_message="; ".join(report.blocking_reasons),
            failure_category=FailureCategory.TERMINAL,
            recovery_action=RecoveryAction.ABORT,
        )

    if rc:
        rc.emit_phase_done(
            "phase_5c_pre_writing_gate",
            {
                "ready": False,
                "rewind_phase": report.rewind_phase,
                "attempt": report.attempt_number,
                "blocked": True,
            },
        )
    raise RuntimeError("pre-writing gate blocked manuscript generation: " + "; ".join(report.blocking_reasons))
