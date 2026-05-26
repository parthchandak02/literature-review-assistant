"""Runner for WritingNode — orchestrates sub-phases in sequence."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import FailureCategory, FallbackEventRecord, StepStatus, WorkflowStepRecord, WritingManifestRecord
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.step_journal import journal_step_complete, journal_step_start
from src.orchestration.runners.writing.post_assembly import run_post_assembly
from src.orchestration.runners.writing.section_loop import SectionLoopResult, run_section_writing_loop
from src.orchestration.runners.writing.setup import load_narrative, run_writing_setup
from src.orchestration.state import ReviewState
from src.writing.prompts.sections import SECTIONS

logger = logging.getLogger(__name__)
_log = logging.getLogger(__name__)


def _rc(state):
    return helper_rc(state)


def _rc_print(rc, message):
    from src.orchestration.helpers.runtime import rc_print as helper_rc_print

    helper_rc_print(rc, message)


async def run_writing_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> None:
    """Write manuscript sections, validate citations, save drafts.

    This is the main writing phase implementation extracted from WritingNode.run().
    It orchestrates: setup → section loop → post-assembly → journal/manifests.
    """
    rc = _rc(state)
    if rc:
        rc.emit_phase_start(
            "phase_6_writing",
            f"Writing manuscript ({len(state.included_papers)} papers)...",
            total=len(SECTIONS),
        )
    assert state.review is not None
    assert state.settings is not None

    # --- Journal step start ---
    _writing_step: WorkflowStepRecord | None = None
    try:
        async with get_db(state.db_path) as _jdb:
            _jrepo = WorkflowRepository(_jdb)
            _writing_step = await journal_step_start(
                _jrepo,
                state.workflow_id,
                "phase_6_writing",
                "writing_phase",
                max_attempts=2,
            )
    except Exception:
        pass

    from src.writing.prompts.sections import set_abstract_word_limit

    set_abstract_word_limit(getattr(state.settings.ieee_export, "max_abstract_words", 250))

    # --- Load narrative ---
    narrative = await load_narrative(state)

    # --- Checkpoint helpers (closures over state) ---
    sections_written: list[str] = []
    _failed_sections: list[str] = []
    _section_results_by_key: dict[str, object] = {}

    async def _save_writing_checkpoint(
        *,
        papers_processed: int,
        status: str = "partial",
    ) -> None:
        """Persist phase_6 progress aggressively for low-loss resume."""
        async with get_db(state.db_path) as _wdb:
            await WorkflowRepository(_wdb).save_checkpoint(
                state.workflow_id,
                "phase_6_writing",
                papers_processed=papers_processed,
                status=status,
            )

    async def _save_subphase_checkpoint(name: str, papers_processed: int = 0) -> None:
        """Best-effort sub-phase markers for deeper resume observability."""
        async with get_db(state.db_path) as _sdb:
            await WorkflowRepository(_sdb).save_checkpoint(
                state.workflow_id,
                name,
                papers_processed=papers_processed,
                status="completed",
            )

    # --- Main DB session: setup + section loop ---
    citation_catalog = ""
    rewound_before_writing = False
    prisma_counts: Any = None

    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        citation_repo = CitationRepository(db)

        # Phase 1: Setup
        setup_result = await run_writing_setup(
            state,
            repository=repository,
            db=db,
            citation_repo=citation_repo,
            narrative=narrative,
            rc=rc,
            save_writing_checkpoint=_save_writing_checkpoint,
            save_subphase_checkpoint=_save_subphase_checkpoint,
        )
        prisma_counts = setup_result["prisma_counts"]
        citation_catalog = setup_result["citation_catalog"]
        rewound_before_writing = setup_result["rewound_before_writing"]

        # Zero-papers fast path
        if setup_result["sections_written_zero"] is not None:
            sections_written = setup_result["sections_written_zero"]
        else:
            # Phase 2: Section writing loop
            loop_result: SectionLoopResult = await run_section_writing_loop(
                state,
                repository=repository,
                db=db,
                citation_repo=citation_repo,
                provider=setup_result["provider"],
                grounding=setup_result["grounding"],
                citation_catalog=citation_catalog,
                completed=setup_result["completed"],
                prisma_counts=prisma_counts,
                rc=rc,
                save_writing_checkpoint=_save_writing_checkpoint,
                save_subphase_checkpoint=_save_subphase_checkpoint,
            )
            sections_written = loop_result.sections_written
            _failed_sections = loop_result.failed_sections
            _section_results_by_key = loop_result.section_results_by_key

    # --- Phase 3: Post-assembly (citation coverage, contradictions, manuscript, diagrams) ---
    await run_post_assembly(
        state,
        sections_written=sections_written,
        failed_sections=_failed_sections,
        citation_catalog=citation_catalog,
        narrative=narrative,
        prisma_counts=prisma_counts,
        rewound_before_writing=rewound_before_writing,
        rc=rc,
        save_subphase_checkpoint=_save_subphase_checkpoint,
    )

    # --- Final checkpoint validation ---
    async with get_db(state.db_path) as _ckpt_db:
        _ckpt_repo = WorkflowRepository(_ckpt_db)
        _persisted_sections = await _ckpt_repo.get_completed_sections(state.workflow_id)
        from src.orchestration.helpers.writing_manuscript import validate_writing_persistence_invariant

        _has_invariant_violation, _missing_sections = validate_writing_persistence_invariant(
            required_sections=list(SECTIONS),
            persisted_sections=_persisted_sections,
            failed_sections=_failed_sections,
        )
        if _has_invariant_violation:
            await _ckpt_repo.save_checkpoint(
                state.workflow_id,
                "phase_6_writing",
                status="partial",
                papers_processed=len(_persisted_sections),
            )
            if rc and hasattr(rc, "_emit"):
                rc._emit(
                    {
                        "type": "writing_error",
                        "workflow_id": state.workflow_id,
                        "required_sections": list(SECTIONS),
                        "failed_sections": _failed_sections,
                        "missing_sections": _missing_sections,
                        "persisted_sections": sorted(_persisted_sections),
                        "message": (
                            "Writing phase ended with incomplete durable section state; "
                            "checkpoint saved as partial for safe resume."
                        ),
                        "resume_hint": (
                            f"uv run python -m src.main resume --workflow-id {state.workflow_id} "
                            "--from-phase phase_6_writing --verbose"
                        ),
                    }
                )
            raise RuntimeError(
                "Writing section persistence invariant failed: "
                f"workflow_id={state.workflow_id}, failed={_failed_sections}, "
                f"missing={_missing_sections}, persisted={sorted(_persisted_sections)}"
            )
        await _ckpt_repo.save_checkpoint(
            state.workflow_id,
            "phase_6_writing",
            papers_processed=len(SECTIONS),
        )
        await _ckpt_db.commit()

    if rc:
        rc.emit_phase_done("phase_6_writing", {"sections": len(sections_written)})

    # --- Journal step complete ---
    if _writing_step:
        try:
            async with get_db(state.db_path) as _jdb:
                _jrepo = WorkflowRepository(_jdb)
                _w_status = StepStatus.SUCCEEDED if not _failed_sections else StepStatus.FAILED
                _w_err = f"failed sections: {', '.join(_failed_sections)}" if _failed_sections else None
                _w_fc = FailureCategory.REPAIRABLE if _failed_sections else None
                await journal_step_complete(
                    _jrepo,
                    _writing_step,
                    status=_w_status,
                    error_message=_w_err,
                    failure_category=_w_fc,
                )
        except Exception:
            _log.warning("WritingNode: step journal write failed", exc_info=True)

    # --- Writing manifests ---
    try:
        async with get_db(state.db_path) as _mdb:
            _mrepo = WorkflowRepository(_mdb)
            _grounding_hash = (
                hashlib.sha256(citation_catalog.encode("utf-8")).hexdigest()[:16] if citation_catalog else None
            )
            _citation_catalog_hash = (
                hashlib.sha256(citation_catalog.encode("utf-8")).hexdigest()[:16] if citation_catalog else None
            )
            for _mi, _msec in enumerate(SECTIONS):
                _mcontent = sections_written[_mi] if _mi < len(sections_written) else ""
                _mresult = _section_results_by_key.get(_msec)
                _missues = list(getattr(_mresult, "validation_issues", []) or [])
                _mfallback = bool(getattr(_mresult, "fallback_used", False)) or _msec in (_failed_sections or [])
                manifest = WritingManifestRecord(
                    workflow_id=state.workflow_id,
                    section_key=_msec,
                    attempt_number=1,
                    grounding_hash=_grounding_hash,
                    citation_catalog_hash=_citation_catalog_hash,
                    contract_status="failed" if _mfallback else ("warning" if _missues else "passed"),
                    contract_issues=json.dumps(_missues),
                    fallback_used=_mfallback,
                    retry_count=int(getattr(_mresult, "validation_retries", 0) or 0),
                    word_count=len(_mcontent.split()) if _mcontent else 0,
                    meta_json=str(getattr(_mresult, "ratchet_meta_json", "{}") or "{}"),
                )
                await _mrepo.save_writing_manifest(manifest)
                if _mfallback:
                    await _mrepo.save_fallback_event(
                        FallbackEventRecord(
                            workflow_id=state.workflow_id,
                            phase="phase_6_writing",
                            module="writing.section_writer",
                            fallback_type="deterministic_section_fallback",
                            reason=(
                                f"section={_msec}; validation_retries="
                                f"{int(getattr(_mresult, 'validation_retries', 0) or 0)}"
                            ),
                            details_json=json.dumps({"validation_issues": _missues}),
                        )
                    )
    except Exception:
        _log.debug("writing manifest persistence failed (non-fatal)", exc_info=True)
