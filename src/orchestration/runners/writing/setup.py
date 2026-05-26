"""Writing phase setup: load synthesis, configure limits, register citations, build grounding."""

from __future__ import annotations

import json
import logging
import pathlib
from pathlib import Path
from typing import Any

from src.db.repositories import CitationRepository, WorkflowRepository
from src.llm.provider import LLMProvider
from src.models import SectionDraft
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.writing_manuscript import build_minimal_sections_for_zero_papers
from src.orchestration.state import ReviewState
from src.prisma import build_prisma_counts, render_prisma_diagram
from src.visualization import render_geographic, render_timeline
from src.writing.context_builder import build_writing_grounding
from src.writing.orchestration import (
    prepare_writing_context,
    register_background_sr_citations,
    register_citations_from_papers,
    register_methodology_citations,
)
from src.writing.prompts.sections import SECTIONS

logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


def _rc_print(rc, message):
    from src.orchestration.helpers.runtime import rc_print as helper_rc_print

    helper_rc_print(rc, message)


async def load_narrative(state: ReviewState) -> dict | None:
    """Load synthesis narrative from DB or JSON artifact file."""
    from src.db.database import get_db

    narrative: dict | None = None
    async with get_db(state.db_path) as _nav_db:
        _synthesis = await WorkflowRepository(_nav_db).load_synthesis_result(state.workflow_id)
        if _synthesis is not None:
            _feas, _narr = _synthesis
            narrative = {"feasibility": _feas.model_dump(), "narrative": _narr.model_dump()}
        if narrative is not None and "narrative_synthesis" in state.artifacts:
            _narr_path = Path(state.artifacts["narrative_synthesis"])
            if _narr_path.exists():
                try:
                    _json_data = json.loads(_narr_path.read_text(encoding="utf-8"))
                    if "meta_analysis" in _json_data:
                        narrative["meta_analysis"] = _json_data["meta_analysis"]
                except Exception:
                    pass
    if narrative is None:
        narrative_path = Path(state.artifacts["narrative_synthesis"])
        if narrative_path.exists():
            try:
                narrative = json.loads(narrative_path.read_text(encoding="utf-8"))
            except Exception:
                narrative = None
    return narrative


async def run_writing_setup(
    state: ReviewState,
    *,
    repository: WorkflowRepository,
    db: Any,
    citation_repo: CitationRepository,
    narrative: dict | None,
    rc: Any | None,
    save_writing_checkpoint: Any,
    save_subphase_checkpoint: Any,
) -> dict:
    """Execute writing setup: PRISMA, citation registration, grounding, zero-papers handling.

    Returns a dict with keys needed by subsequent phases:
      - prisma_counts, provider, grounding, citation_catalog, completed,
        bg_citekeys, rewound_before_writing, sections_written (if zero papers),
        screening_decisions, actual_search_date, failed_dbs,
        rob2_rows, robins_i_rows, casp_rows, mmat_rows, grade_rows,
        fig_map, fulltext_ids_for_grounding
    """
    await save_writing_checkpoint(papers_processed=0, status="partial")

    _removed_stale_grade = await repository.delete_placeholder_grade_assessments(state.workflow_id)
    if _removed_stale_grade > 0:
        logger.info(
            "WritingNode: removed %d stale placeholder GRADE row(s) before writing",
            _removed_stale_grade,
        )

    _canonical_included_ids_for_prisma = await repository.get_synthesis_included_paper_ids(state.workflow_id)
    if not _canonical_included_ids_for_prisma:
        _canonical_included_ids_for_prisma = {str(p.paper_id) for p in state.included_papers if p.paper_id}
    prisma_counts = await build_prisma_counts(
        repository,
        state.workflow_id,
        state.dedup_count,
        included_qualitative=0,
        included_quantitative=len(_canonical_included_ids_for_prisma),
    )
    render_prisma_diagram(prisma_counts, state.artifacts["prisma_diagram"])
    render_timeline(state.included_papers, state.artifacts["timeline"])
    render_geographic(state.included_papers, state.artifacts["geographic"])
    if rc and rc.verbose:
        _rc_print(rc, f"  PRISMA: {prisma_counts} -> {Path(state.artifacts['prisma_diagram']).name}")
        _rc_print(rc, f"  Timeline: {Path(state.artifacts['timeline']).name}")
        _rc_print(rc, f"  Geographic: {Path(state.artifacts['geographic']).name}")

    await citation_repo.ensure_schema()
    _rewound_before_writing = state.next_phase in {
        "phase_2_search",
        "phase_3_screening",
        "phase_4_extraction_quality",
        "phase_4b_embedding",
        "phase_5_synthesis",
        "phase_5b_knowledge_graph",
        "phase_5c_pre_writing_gate",
    }
    completed = await repository.get_completed_sections(state.workflow_id)
    if _rewound_before_writing and completed:
        logger.info(
            "WritingNode: ignoring %d persisted completed sections after rewind from %s",
            len(completed),
            state.next_phase,
        )
        completed = set()

    wr_on_waiting = None
    wr_on_resolved = None
    if rc:

        def _wr_on_waiting(t: object, u: object, limit: object, waited: object = 0.0) -> None:
            rc.log_rate_limit_wait(t, u, limit, waited)

        def _wr_on_resolved(t: object, waited: object) -> None:
            rc.log_rate_limit_resolved(t, waited)

        wr_on_waiting = _wr_on_waiting
        wr_on_resolved = _wr_on_resolved
    provider = LLMProvider(state.settings, repository, on_waiting=wr_on_waiting, on_resolved=wr_on_resolved)

    await register_citations_from_papers(citation_repo, state.included_papers)
    await register_methodology_citations(citation_repo)
    _bg_kws = list(state.review.keywords)[:6] if state.review else []
    _bg_rq = state.review.research_question if state.review else ""
    _writing_cfg = getattr(state.settings, "writing", None)
    _bg_citekeys = await register_background_sr_citations(
        citation_repo,
        _bg_rq,
        _bg_kws,
        max_results=int(getattr(_writing_cfg, "background_sr_max_results", 8)),
        query_keyword_limit=int(getattr(_writing_cfg, "background_sr_query_keyword_limit", 6)),
        topic_token_keyword_limit=int(getattr(_writing_cfg, "background_sr_topic_token_keyword_limit", 10)),
        request_timeout_seconds=int(getattr(_writing_cfg, "background_sr_request_timeout_seconds", 20)),
    )
    if _bg_citekeys:
        logger.info(
            "WritingNode: registered %d background SR citekeys: %s",
            len(_bg_citekeys),
            ", ".join(_bg_citekeys),
        )
    _bg_rows_raw: list[tuple] = []
    async with db.execute(
        """
        SELECT citekey, title, year
        FROM citations
        WHERE source_type = 'background_sr'
        ORDER BY year DESC, citekey ASC
        """
    ) as _bg_cur:
        _bg_rows_raw = await _bg_cur.fetchall()
    _bg_rows: list[tuple[str, str, int | None]] = [
        (
            str(r[0]),
            str(r[1] or ""),
            int(r[2]) if r[2] is not None else None,
        )
        for r in _bg_rows_raw
    ]
    citation_catalog = prepare_writing_context(state.included_papers, state.settings, _bg_rows)

    # --- Zero-papers fast path ---
    sections_written_zero: list[str] | None = None
    if len(state.included_papers) == 0:
        total_id = prisma_counts.total_identified_databases + prisma_counts.total_identified_other
        dbs = list(prisma_counts.databases_records.keys()) or ["searched databases"]
        db_str = ", ".join(dbs) if dbs else "the specified databases"
        minimal_para = (
            f"The search identified {total_id} records from {db_str}. "
            "After screening, 0 studies met the eligibility criteria. "
            "No synthesis or findings are reported."
        )
        rq = state.review.research_question or "the research question"
        _minimal_contents = build_minimal_sections_for_zero_papers(rq, minimal_para, SECTIONS)
        sections_written_zero = []
        for i, content in enumerate(_minimal_contents):
            draft = SectionDraft(
                workflow_id=state.workflow_id,
                section=SECTIONS[i],
                version=1,
                content=content,
                claims_used=[],
                citations_used=[],
                word_count=len(content.split()),
            )
            await repository.save_section_artifacts_from_draft(draft, section_order=i)
            sections_written_zero.append(content)
            if rc:
                rc.advance_screening("phase_6_writing", i + 1, len(SECTIONS))
        logger.info("WritingNode: 0 included papers; produced minimal manuscript without LLM calls")

    # --- Load auxiliary data for grounding ---
    _screening_decisions: list[object] = []
    _actual_search_date: str | None = None
    _failed_dbs: list[str] = []
    _rob2_rows_w: list = []
    _robins_i_rows_w: list = []
    _casp_rows_w: list = []
    _mmat_rows_w: list = []
    _grade_rows_w: list = []

    if len(state.included_papers) > 0:
        try:
            async with db.execute("SELECT actor, phase FROM decision_log WHERE phase = 'phase_3_screening'") as _sdcur:
                _sd_rows = await _sdcur.fetchall()

            class _SDStub:
                __slots__ = ("actor", "phase")

                def __init__(self, _actor: str, _phase: str) -> None:
                    self.actor = _actor
                    self.phase = _phase

            _screening_decisions = [_SDStub(r[0], r[1]) for r in _sd_rows]
        except Exception as _sd_err:
            logger.debug("WritingNode: could not fetch screening decisions: %s", _sd_err)

        try:
            async with db.execute(
                "SELECT MAX(search_date) FROM search_results WHERE workflow_id = ?",
                (state.workflow_id,),
            ) as _date_cur:
                _date_row = await _date_cur.fetchone()
            if _date_row and _date_row[0]:
                _actual_search_date = str(_date_row[0])
        except Exception as _date_err:
            logger.debug("WritingNode: could not fetch search_date: %s", _date_err)

        try:
            _failed_dbs = await repository.get_failed_search_connectors(state.workflow_id)
        except Exception as _fdb_err:
            logger.debug("WritingNode: could not fetch failed search connectors: %s", _fdb_err)

        try:
            _rob2_rows_w, _robins_i_rows_w = await repository.load_rob_assessments(state.workflow_id)
            _casp_rows_w = await repository.load_casp_assessments(state.workflow_id)
            _mmat_rows_w = await repository.load_mmat_assessments(state.workflow_id)
            _grade_rows_w = await repository.load_grade_assessments(state.workflow_id)
        except Exception as _rob_err:
            logger.debug("WritingNode: could not load RoB/GRADE assessments: %s", _rob_err)

    # --- Figure map ---
    from src.export.markdown_refs import FIGURE_DEFS as _FIGURE_DEFS

    _fig_map: dict[str, int] = {}
    _fig_seq = 1
    for _fkey, _ in _FIGURE_DEFS:
        _fpath_str = state.artifacts.get(_fkey, "")
        if _fpath_str and pathlib.Path(_fpath_str).exists():
            _fig_map[_fkey] = _fig_seq
            _fig_seq += 1

    _fulltext_ids_for_grounding: set[str] = set()
    _papers_dir = pathlib.Path(state.artifacts.get("papers_dir", ""))
    if _papers_dir.exists():
        for _pf in _papers_dir.iterdir():
            if _pf.suffix.lower() in {".pdf", ".txt"} and _pf.stat().st_size > 0:
                _fulltext_ids_for_grounding.add(_pf.stem)

    # --- Build grounding ---
    grounding = build_writing_grounding(
        prisma_counts=prisma_counts,
        extraction_records=state.extraction_records,
        included_papers=state.included_papers,
        narrative=narrative,
        citation_catalog=citation_catalog,
        cohens_kappa=state.cohens_kappa,
        kappa_stage=state.kappa_stage,
        kappa_n=state.kappa_n,
        sensitivity_results=state.sensitivity_results,
        search_limitation=getattr(state.review, "search_limitation", None) if state.review else None,
        review_config=state.review,
        heuristic_assessment_count=state.heuristic_assessment_count,
        screening_decisions=_screening_decisions or None,
        background_sr_citekeys=_bg_citekeys,
        search_date=_actual_search_date,
        failed_databases=_failed_dbs,
        batch_screen_forwarded=state.batch_screen_forwarded,
        batch_screen_excluded=state.batch_screen_excluded,
        batch_screener_model=state.batch_screener_model,
        batch_screen_threshold=state.batch_screen_threshold,
        batch_screen_validation_n=state.batch_screen_validation_n,
        batch_screen_validation_npv=state.batch_screen_validation_npv,
        batch_screen_validation_min_n=int(
            getattr(
                getattr(state.settings, "screening", None),
                "batch_screen_validation_min_sample",
                20,
            )
        ),
        fulltext_sought=state.fulltext_sought,
        fulltext_not_retrieved=state.fulltext_not_retrieved,
        sparse_evidence_mode=state.sparse_evidence_mode,
        rob2_assessments=_rob2_rows_w or None,
        robins_i_assessments=_robins_i_rows_w or None,
        casp_assessments=_casp_rows_w or None,
        mmat_assessments=_mmat_rows_w or None,
        grade_assessments=_grade_rows_w or None,
        figure_map=_fig_map or None,
        fulltext_paper_ids=_fulltext_ids_for_grounding or None,
        fulltext_nonretrieval_caution_threshold=float(
            getattr(
                getattr(state.settings, "writing", None),
                "fulltext_nonretrieval_caution_threshold",
                0.40,
            )
        ),
        abstract_only_caution_threshold=float(
            getattr(
                getattr(state.settings, "writing", None),
                "abstract_only_caution_threshold",
                0.40,
            )
        ),
        excluded_non_primary_count=state.excluded_non_primary_count,
    )

    return {
        "prisma_counts": prisma_counts,
        "provider": provider,
        "grounding": grounding,
        "citation_catalog": citation_catalog,
        "completed": completed,
        "bg_citekeys": _bg_citekeys,
        "rewound_before_writing": _rewound_before_writing,
        "sections_written_zero": sections_written_zero,
    }
