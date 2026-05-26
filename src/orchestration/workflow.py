"""Single-path workflow orchestration for `run`.

Thin graph-definition file: imports all node classes (for backward compat),
defines RUN_GRAPH, and exposes run_workflow / run_workflow_resume / run_workflow_sync.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from pydantic_graph import Graph

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import (
    find_by_topic,
    find_by_workflow_id,
    find_by_workflow_id_fallback,
)
from src.db.workflow_registry import (
    register as register_workflow,
)
from src.models import (
    ExtractionRecord,
    FailureCategory,
    PreWritingGateReport,
    RecoveryAction,
    ReviewConfig,
    StepStatus,
    WorkflowStepRecord,
)
from src.orchestration.context import RunContext
from src.orchestration.embedding_node import EmbeddingNode
from src.orchestration.helpers.extraction_metrics import (
    ABSTRACT_ONLY_EXTRACTION_SOURCES as HELPER_ABSTRACT_ONLY_EXTRACTION_SOURCES,
)
from src.orchestration.helpers.extraction_metrics import (
    compute_extraction_quality_metrics as helper_compute_extraction_quality_metrics,
)
from src.orchestration.helpers.extraction_metrics import (
    has_participant_evidence as helper_has_participant_evidence,
)
from src.orchestration.helpers.extraction_metrics import (
    load_fulltext_artifact_paper_ids as helper_load_fulltext_artifact_paper_ids,
)
from src.orchestration.helpers.manuscript_gate import (
    collect_manuscript_gate_failure_reasons as helper_collect_manuscript_gate_failure_reasons,
)
from src.orchestration.helpers.manuscript_gate import (
    manuscript_gate_blocks_workflow as helper_manuscript_gate_blocks_workflow,
)
from src.orchestration.helpers.manuscript_gate import (
    resolve_manuscript_gate_action as helper_resolve_manuscript_gate_action,
)
from src.orchestration.helpers.pre_writing_gate import (
    PRE_WRITING_PHASE_ORDER as HELPER_PRE_WRITING_PHASE_ORDER,
)
from src.orchestration.helpers.pre_writing_gate import (
    compute_pre_writing_gate_report as helper_compute_pre_writing_gate_report,
)
from src.orchestration.helpers.pre_writing_gate import (
    count_prior_pre_writing_failures as helper_count_prior_pre_writing_failures,
)
from src.orchestration.helpers.pre_writing_gate import (
    persist_pre_writing_gate_validation as helper_persist_pre_writing_gate_validation,
)
from src.orchestration.helpers.pre_writing_gate import (
    pre_writing_phases_from as helper_pre_writing_phases_from,
)
from src.orchestration.helpers.pre_writing_gate import (
    rewind_pre_writing_phase as helper_rewind_pre_writing_phase,
)
from src.orchestration.helpers.pre_writing_gate import (
    select_pre_writing_rewind_phase as helper_select_pre_writing_rewind_phase,
)
from src.orchestration.helpers.runtime import evaluate_rag_health as helper_evaluate_rag_health
from src.orchestration.helpers.runtime import hash_config as helper_hash_config
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.helpers.runtime import now_utc as helper_now_utc
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.runtime import rc_print as helper_rc_print
from src.orchestration.helpers.search_connectors import build_connectors as helper_build_connectors
from src.orchestration.helpers.step_journal import journal_step_complete as helper_journal_step_complete
from src.orchestration.helpers.step_journal import journal_step_start as helper_journal_step_start
from src.orchestration.helpers.writing_manuscript import (
    build_citation_coverage_patch as helper_build_citation_coverage_patch,
)
from src.orchestration.helpers.writing_manuscript import (
    build_minimal_sections_for_zero_papers as helper_build_minimal_sections_for_zero_papers,
)
from src.orchestration.helpers.writing_manuscript import (
    refresh_manuscript_export_artifacts as helper_refresh_manuscript_export_artifacts,
)
from src.orchestration.helpers.writing_manuscript import (
    replace_template_tokens as helper_replace_template_tokens,
)
from src.orchestration.helpers.writing_manuscript import (
    trim_abstract_to_limit as helper_trim_abstract_to_limit,
)
from src.orchestration.helpers.writing_manuscript import (
    validate_writing_persistence_invariant as helper_validate_writing_persistence_invariant,
)
from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
from src.orchestration.nodes.extraction_quality import ExtractionQualityNode
from src.orchestration.nodes.finalize import FinalizeNode
from src.orchestration.nodes.human_review import HumanReviewCheckpointNode
from src.orchestration.nodes.manuscript_audit import ManuscriptAuditNode
from src.orchestration.nodes.pre_writing_gate import PreWritingGateNode
from src.orchestration.nodes.resume_start import ResumeStartNode
from src.orchestration.nodes.screening import ScreeningNode
from src.orchestration.nodes.search import SearchNode
from src.orchestration.nodes.start import StartNode
from src.orchestration.nodes.synthesis import SynthesisNode
from src.orchestration.nodes.writing import WritingNode
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState
from src.search.base import SearchConnector
from src.writing.context_builder import sanitize_summary_text_for_writing

_log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared wrapper functions (used by multiple runners or imported by tests)
# ---------------------------------------------------------------------------


def _now_utc() -> str:
    return helper_now_utc()


def _hash_config(path: str) -> str:
    return helper_hash_config(path)


def _evaluate_rag_health(
    *,
    empty_sections: int,
    error_sections: int,
    max_empty_sections: int,
) -> tuple[bool, str]:
    """Return (breached, message) for run-level RAG health gate."""
    return helper_evaluate_rag_health(
        empty_sections=empty_sections,
        error_sections=error_sections,
        max_empty_sections=max_empty_sections,
    )


def _llm_available(settings: ReviewState | None = None, settings_cfg=None) -> bool:
    return helper_llm_available(settings=settings, settings_cfg=settings_cfg)


def _build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list[SearchConnector], dict[str, str]]:
    return helper_build_connectors(workflow_id, target_databases)


def _rc(state: ReviewState) -> RunContext | None:
    return helper_rc(state)


def _rc_print(rc: RunContext | None, message: object) -> None:
    """Safely print for CLI contexts; no-op safe for web contexts."""
    helper_rc_print(rc, message)


async def _journal_step_start(
    repo: WorkflowRepository,
    workflow_id: str,
    phase: str,
    step_name: str,
    *,
    paper_id: str | None = None,
    parent_step_id: str | None = None,
    max_attempts: int = 1,
) -> WorkflowStepRecord:
    """Record a step execution start in the workflow journal."""
    return await helper_journal_step_start(
        repo,
        workflow_id,
        phase,
        step_name,
        paper_id=paper_id,
        parent_step_id=parent_step_id,
        max_attempts=max_attempts,
    )


async def _journal_step_complete(
    repo: WorkflowRepository,
    record: WorkflowStepRecord,
    *,
    status: StepStatus = StepStatus.SUCCEEDED,
    error_message: str | None = None,
    failure_category: FailureCategory | None = None,
    recovery_action: RecoveryAction | None = None,
) -> None:
    await helper_journal_step_complete(
        repo,
        record,
        status=status,
        error_message=error_message,
        failure_category=failure_category,
        recovery_action=recovery_action,
    )


def _should_exclude_low_quality_record(
    record: ExtractionRecord,
    *,
    mmat_score: int,
    mmat_minimum_score: int,
) -> bool:
    """Return True when MMAT is below threshold and findings sanitize to NR."""
    if mmat_minimum_score <= 0 or mmat_score >= mmat_minimum_score:
        return False
    summary_text = ""
    try:
        summary_text = (record.results_summary or {}).get("summary", "")
    except Exception:
        summary_text = ""
    return sanitize_summary_text_for_writing(summary_text) == "NR"


_ABSTRACT_ONLY_EXTRACTION_SOURCES = HELPER_ABSTRACT_ONLY_EXTRACTION_SOURCES


def _has_participant_evidence(record: ExtractionRecord) -> bool:
    return helper_has_participant_evidence(record)


def _compute_extraction_quality_metrics(
    records: list[ExtractionRecord],
    included_papers: list,
    fulltext_paper_ids: set[str] | None = None,
) -> tuple[float, float, str]:
    """Return composite extraction quality, weak-evidence rate, and metric details."""
    return helper_compute_extraction_quality_metrics(records, included_papers, fulltext_paper_ids)


def _load_fulltext_artifact_paper_ids(run_artifacts: dict[str, str], db_path: str) -> set[str]:
    """Return paper IDs with saved PDF/TXT artifacts for the current run."""
    return helper_load_fulltext_artifact_paper_ids(run_artifacts, db_path)


def _build_citation_coverage_patch(
    uncited_keys: list[str],
    citekey_to_design: dict[str, str] | None = None,
    chunk_size: int = 8,
) -> str:
    return helper_build_citation_coverage_patch(
        uncited_keys, citekey_to_design=citekey_to_design, chunk_size=chunk_size
    )


def _replace_template_tokens(text: str, review: ReviewConfig | None) -> str:
    return helper_replace_template_tokens(text, review)


def _trim_abstract_to_limit(abstract: str, limit: int | None = None) -> str:
    return helper_trim_abstract_to_limit(abstract, limit=limit)


def _build_minimal_sections_for_zero_papers(
    research_question: str,
    minimal_paragraph: str,
    sections: list[str],
) -> list[str]:
    return helper_build_minimal_sections_for_zero_papers(research_question, minimal_paragraph, sections)


def _validate_writing_persistence_invariant(
    required_sections: list[str],
    persisted_sections: set[str],
    failed_sections: list[str],
) -> tuple[bool, list[str]]:
    return helper_validate_writing_persistence_invariant(required_sections, persisted_sections, failed_sections)


_PRE_WRITING_PHASE_ORDER = HELPER_PRE_WRITING_PHASE_ORDER


def _pre_writing_phases_from(start_phase: str) -> list[str]:
    return helper_pre_writing_phases_from(start_phase)


def _select_pre_writing_rewind_phase(phases: list[str]) -> str | None:
    return helper_select_pre_writing_rewind_phase(phases)


async def _count_prior_pre_writing_failures(db, workflow_id: str) -> int:
    return await helper_count_prior_pre_writing_failures(db, workflow_id)


async def _compute_pre_writing_gate_report(
    *,
    state: ReviewState,
    repository: WorkflowRepository,
    db,
    attempt_number: int,
) -> PreWritingGateReport:
    return await helper_compute_pre_writing_gate_report(
        state=state,
        repository=repository,
        db=db,
        attempt_number=attempt_number,
    )


async def _persist_pre_writing_gate_validation(
    *,
    repository: WorkflowRepository,
    report: PreWritingGateReport,
) -> None:
    await helper_persist_pre_writing_gate_validation(repository=repository, report=report)


async def _rewind_pre_writing_phase(
    *,
    repository: WorkflowRepository,
    workflow_id: str,
    rewind_phase: str,
) -> None:
    await helper_rewind_pre_writing_phase(repository=repository, workflow_id=workflow_id, rewind_phase=rewind_phase)


def _collect_manuscript_gate_failure_reasons(contract_result, audit_result) -> list[str]:
    return helper_collect_manuscript_gate_failure_reasons(contract_result, audit_result)


def _resolve_manuscript_gate_action(audit_gate_mode: str, gate_blocked: bool) -> str:
    return helper_resolve_manuscript_gate_action(audit_gate_mode, gate_blocked)


def _manuscript_gate_blocks_workflow(audit_gate_mode: str, gate_blocked: bool) -> bool:
    return helper_manuscript_gate_blocks_workflow(audit_gate_mode, gate_blocked)


async def _refresh_manuscript_export_artifacts(
    state: ReviewState,
    *,
    strict_export: bool,
    persist_assembly: bool = False,
) -> str | None:
    return await helper_refresh_manuscript_export_artifacts(
        state,
        strict_export=strict_export,
        persist_assembly=persist_assembly,
    )


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

RUN_GRAPH = Graph(
    nodes=[
        StartNode,
        ResumeStartNode,
        SearchNode,
        ScreeningNode,
        HumanReviewCheckpointNode,
        ExtractionQualityNode,
        EmbeddingNode,
        SynthesisNode,
        KnowledgeGraphNode,
        PreWritingGateNode,
        WritingNode,
        ManuscriptAuditNode,
        FinalizeNode,
    ],
    state_type=ReviewState,
    run_end_type=dict,
)


# ---------------------------------------------------------------------------
# Workflow entry points
# ---------------------------------------------------------------------------


def _make_sigint_handler(rc: RunContext):
    """Return a SIGINT handler that sets proceed_with_partial on first Ctrl+C, aborts on second."""

    def handler() -> None:
        if rc.should_proceed_with_partial():
            raise KeyboardInterrupt
        rc.proceed_with_partial_requested[0] = True
        if rc.verbose:
            _rc_print(rc, "[yellow]Proceeding with partial screening results...[/]")

    return handler


async def run_workflow_resume(
    workflow_id: str | None = None,
    topic: str | None = None,
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    run_root: str = "runs",
    run_context: RunContext | None = None,
    from_phase: str | None = None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    """Resume a workflow from its last checkpoint."""
    if workflow_id is None and topic is None:
        raise ValueError("Either workflow_id or topic must be provided for resume")
    entry = None
    if workflow_id:
        entry = await find_by_workflow_id(run_root, workflow_id)
        if entry is None:
            entry = await find_by_workflow_id_fallback(run_root, workflow_id)
            if entry is not None:
                config_hash = _hash_config(review_path) if os.path.isfile(review_path) else ""
                await register_workflow(
                    run_root=run_root,
                    workflow_id=entry.workflow_id,
                    topic=entry.topic or "unknown",
                    config_hash=config_hash,
                    db_path=entry.db_path,
                    status=entry.status,
                )
    else:
        review, _ = load_configs(review_path, settings_path)
        config_hash = _hash_config(review_path)
        search_topic = topic if topic is not None else review.research_question
        matches = await find_by_topic(run_root, search_topic, config_hash)
        entry = matches[0] if matches else None
    if entry is None:
        raise FileNotFoundError("Workflow not found or db file missing. It may have been deleted.")
    state, next_phase = await load_resume_state(
        db_path=entry.db_path,
        workflow_id=entry.workflow_id,
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
        from_phase=from_phase,
    )
    state.run_context = run_context
    state.run_id = _now_utc()
    if run_context is not None and not getattr(run_context, "web_mode", False):
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, _make_sigint_handler(run_context))
        except NotImplementedError:
            pass
    start = ResumeStartNode()
    result = await RUN_GRAPH.run(start, state=state)
    return result.output


async def run_workflow(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    run_root: str = "runs",
    run_context: RunContext | None = None,
    fresh: bool = False,
    parent_db_path: str | None = None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    review, settings = load_configs(review_path, settings_path)
    config_hash = _hash_config(review_path)
    matches = await find_by_topic(run_root, review.research_question, config_hash)
    resumable = [m for m in matches if m.status != "completed"]
    if resumable and not fresh:
        entry = resumable[0]
        async with get_db(entry.db_path) as db:
            repo = WorkflowRepository(db)
            checkpoints = await repo.get_checkpoints(entry.workflow_id)
        phase_count = len(checkpoints)
        phase_label = f"phase {phase_count}/7" if phase_count < 7 else "finalize"
        _console = getattr(run_context, "console", None) if run_context else None
        if _console is not None:
            from rich.prompt import Confirm

            if Confirm.ask(
                f"Found existing run for this topic ({phase_label} complete). Resume?",
                default=True,
                console=_console,
            ):
                return await run_workflow_resume(
                    workflow_id=entry.workflow_id,
                    review_path=review_path,
                    settings_path=settings_path,
                    run_root=run_root,
                    run_context=run_context,
                )
        else:
            try:
                resp = (
                    input(f"Found existing run for this topic ({phase_label} complete). Resume? [Y/n]: ")
                    .strip()
                    .lower()
                )
                if resp in ("", "y", "yes"):
                    return await run_workflow_resume(
                        workflow_id=entry.workflow_id,
                        review_path=review_path,
                        settings_path=settings_path,
                        run_root=run_root,
                        run_context=run_context,
                    )
            except EOFError:
                pass

    if run_context is not None and not getattr(run_context, "web_mode", False):
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, _make_sigint_handler(run_context))
        except NotImplementedError:
            pass

    start = StartNode()
    initial = ReviewState(
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
        run_context=run_context,
        parent_db_path=parent_db_path,
    )
    result = await RUN_GRAPH.run(start, state=initial)
    return result.output


def run_workflow_sync(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    run_root: str = "runs",
    run_context: RunContext | None = None,
    fresh: bool = False,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    return asyncio.run(
        run_workflow(
            review_path=review_path,
            settings_path=settings_path,
            run_root=run_root,
            run_context=run_context,
            fresh=fresh,
        )
    )
