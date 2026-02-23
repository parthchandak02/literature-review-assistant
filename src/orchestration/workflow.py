"""Single-path workflow orchestration for `run`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.table import Table

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.db.workflow_registry import (
    find_by_topic,
    find_by_workflow_id,
    find_by_workflow_id_fallback,
)
from src.db.workflow_registry import (
    register as register_workflow,
)
from src.db.workflow_registry import (
    update_status as update_registry_status,
)
from src.extraction import ExtractionService, StudyClassifier
from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import DecisionLogEntry, ExtractionRecord, SectionDraft, StudyDesign
from src.orchestration.context import RunContext
from src.orchestration.gates import GateRunner
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState
from src.prisma import build_prisma_counts, render_prisma_diagram
from src.protocol.generator import ProtocolGenerator
from src.quality import (
    CaspAssessor,
    GradeAssessor,
    Rob2Assessor,
    RobinsIAssessor,
    StudyRouter,
)
from src.screening.dual_screener import DualReviewerScreener
from src.screening.gemini_client import PydanticAIScreeningClient
from src.screening.keyword_filter import bm25_rank_and_cap, keyword_prefilter
from src.search.arxiv import ArxivConnector
from src.search.base import SearchConnector
from src.search.crossref import CrossrefConnector
from src.search.deduplication import deduplicate_papers
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.perplexity_search import PerplexitySearchConnector
from src.search.pubmed import PubMedConnector
from src.search.semantic_scholar import SemanticScholarConnector
from src.search.strategy import SearchStrategyCoordinator
from src.synthesis import assess_meta_analysis_feasibility, build_narrative_synthesis
from src.synthesis.meta_analysis import pool_effects
from src.utils import structured_log
from src.utils.logging_paths import create_run_paths
from src.visualization import (
    render_geographic,
    render_rob_traffic_light,
    render_timeline,
)
from src.visualization.forest_plot import render_forest_plot
from src.visualization.funnel_plot import render_funnel_plot
from src.export.markdown_refs import assemble_submission_manuscript
from src.writing.context_builder import build_writing_grounding
from src.writing.humanizer import humanize_async
from src.writing.orchestration import (
    prepare_writing_context,
    register_citations_from_papers,
    write_section_with_validation,
)
from src.writing.prompts.sections import (
    SECTIONS,
    get_section_context,
    get_section_word_limit,
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _hash_config(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


_PREFIX_TO_ENV: dict[str, str] = {
    "google-gla:": "GEMINI_API_KEY",
    "google-vertex:": "GEMINI_API_KEY",
    "anthropic:": "ANTHROPIC_API_KEY",
    "openai:": "OPENAI_API_KEY",
    "groq:": "GROQ_API_KEY",
    "mistral:": "MISTRAL_API_KEY",
    "cohere:": "CO_API_KEY",
}


def _llm_available(settings: "ReviewState | None" = None, settings_cfg: "SettingsConfig | None" = None) -> bool:
    """Return True if at least one LLM API key is set for the configured model prefixes.

    Accepts either a ReviewState (for workflow nodes that have state) or a
    SettingsConfig directly. Falls back to checking GEMINI_API_KEY for backward
    compatibility when no settings are provided.
    """
    from src.models import SettingsConfig as SC
    cfg: SC | None = None
    if settings_cfg is not None:
        cfg = settings_cfg
    elif settings is not None and hasattr(settings, "settings"):
        cfg = settings.settings  # type: ignore[union-attr]
    if cfg is None:
        return bool(os.getenv("GEMINI_API_KEY"))
    for agent_cfg in cfg.agents.values():
        for prefix, env_key in _PREFIX_TO_ENV.items():
            if agent_cfg.model.startswith(prefix) and os.getenv(env_key):
                return True
    return False


def _build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list[SearchConnector], dict[str, str]]:
    connectors: list[SearchConnector] = []
    failures: dict[str, str] = {}
    for name in target_databases:
        normalized = name.lower()
        try:
            if normalized == "openalex":
                connectors.append(OpenAlexConnector(workflow_id))
            elif normalized == "pubmed":
                connectors.append(PubMedConnector(workflow_id))
            elif normalized == "arxiv":
                connectors.append(ArxivConnector(workflow_id))
            elif normalized == "ieee_xplore":
                connectors.append(IEEEXploreConnector(workflow_id))
            elif normalized == "semantic_scholar":
                connectors.append(SemanticScholarConnector(workflow_id))
            elif normalized == "crossref":
                connectors.append(CrossrefConnector(workflow_id))
            elif normalized == "perplexity_search":
                connectors.append(PerplexitySearchConnector(workflow_id))
            else:
                failures[normalized] = "unsupported_connector"
        except Exception as exc:
            failures[normalized] = f"{type(exc).__name__}: {exc}"
    return connectors, failures


def _rc(state: ReviewState) -> RunContext | None:
    return state.run_context


class ResumeStartNode(BaseNode[ReviewState]):
    """Entry node for resume: loads state, configures logging, routes to next phase."""

    async def run(
        self,
        ctx: GraphRunContext[ReviewState],
    ) -> SearchNode | ScreeningNode | ExtractionQualityNode | SynthesisNode | FinalizeNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("resume", f"Resuming from {state.next_phase}...")
        structured_log.configure_run_logging(state.log_dir)
        structured_log.bind_run(state.workflow_id, state.run_id or "resume")
        phase = state.next_phase
        if phase == "phase_2_search":
            return SearchNode()
        if phase == "phase_3_screening":
            return ScreeningNode()
        if phase == "phase_4_extraction_quality":
            return ExtractionQualityNode()
        if phase == "phase_5_synthesis":
            return SynthesisNode()
        if phase == "phase_6_writing":
            return WritingNode()
        if phase == "finalize":
            return FinalizeNode()
        return SearchNode()


class StartNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> SearchNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("start", "Loading configs...")
        review, settings = load_configs(state.review_path, state.settings_path)
        state.review = review
        state.settings = settings
        state.run_id = _now_utc()
        state.workflow_id = f"wf-{uuid4().hex[:8]}"

        run_paths = create_run_paths(run_root=state.run_root, workflow_description=review.research_question)
        state.log_dir = str(run_paths.run_dir)
        state.output_dir = str(run_paths.run_dir)
        state.db_path = str(run_paths.runtime_db)
        structured_log.configure_run_logging(state.log_dir)
        structured_log.bind_run(state.workflow_id, state.run_id)
        state.artifacts["run_summary"] = str(run_paths.run_summary)
        state.artifacts["search_appendix"] = str(run_paths.search_appendix)
        state.artifacts["protocol"] = str(run_paths.protocol_markdown)
        state.artifacts["coverage_report"] = str(run_paths.run_dir / "doc_fulltext_retrieval_coverage.md")
        state.artifacts["disagreements_report"] = str(run_paths.run_dir / "doc_disagreements_report.md")
        state.artifacts["rob_traffic_light"] = str(run_paths.run_dir / "fig_rob_traffic_light.png")
        state.artifacts["rob2_traffic_light"] = str(run_paths.run_dir / "fig_rob2_traffic_light.png")
        state.artifacts["narrative_synthesis"] = str(run_paths.run_dir / "data_narrative_synthesis.json")
        state.artifacts["manuscript_md"] = str(run_paths.run_dir / "doc_manuscript.md")
        state.artifacts["prisma_diagram"] = str(run_paths.run_dir / "fig_prisma_flow.png")
        state.artifacts["timeline"] = str(run_paths.run_dir / "fig_publication_timeline.png")
        state.artifacts["geographic"] = str(run_paths.run_dir / "fig_geographic_distribution.png")
        state.artifacts["fig_forest_plot"] = str(run_paths.run_dir / "fig_forest_plot.png")
        state.artifacts["fig_funnel_plot"] = str(run_paths.run_dir / "fig_funnel_plot.png")
        if rc:
            rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
            if hasattr(rc, "set_db_path"):
                rc.set_db_path(state.db_path)
        return SearchNode()


class SearchNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> ScreeningNode:
        state = ctx.state
        rc = _rc(state)
        assert state.review is not None
        assert state.settings is not None

        connectors, connector_init_failures = _build_connectors(state.workflow_id, state.review.target_databases)
        state.connector_init_failures = connector_init_failures
        if rc:
            rc.emit_phase_start("phase_2_search", "Running connectors...", total=len(connectors))
            for name, err in connector_init_failures.items():
                rc.log_connector_result(
                    name=name,
                    status="failed",
                    records=0,
                    query="",
                    date_start=state.review.date_range_start,
                    date_end=state.review.date_range_end,
                    error=err,
                )

        connector_done_count: list[int] = [0]

        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            config_hash = _hash_config(state.review_path)
            await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)
            await register_workflow(
                run_root=state.run_root,
                workflow_id=state.workflow_id,
                topic=state.review.research_question,
                config_hash=config_hash,
                db_path=state.db_path,
            )
            if rc is not None and hasattr(rc, "notify_workflow_id"):
                rc.notify_workflow_id(state.workflow_id, state.run_root)
            gate_runner = GateRunner(repository, state.settings)
            def _on_connector_done(
                name: str,
                status: str,
                records: int,
                query: str,
                date_start: int | None,
                date_end: int | None,
                error: str | None,
            ) -> None:
                if rc and rc.verbose:
                    rc.log_connector_result(
                        name=name,
                        status=status,
                        records=records,
                        query=query,
                        date_start=date_start,
                        date_end=date_end,
                        error=error,
                    )
                structured_log.log_connector_result(
                    connector=name, status=status, records=records, error=error
                )
                connector_done_count[0] += 1
                if rc:
                    rc.advance_screening("phase_2_search", connector_done_count[0], len(connectors))

            on_connector_done = _on_connector_done
            coordinator = SearchStrategyCoordinator(
                workflow_id=state.workflow_id,
                config=state.review,
                connectors=connectors,
                repository=repository,
                gate_runner=gate_runner,
                output_dir=state.output_dir,
                on_connector_done=on_connector_done,
            )
            search_cfg = state.settings.search
            results, dedup_count = await coordinator.run(
                max_results=search_cfg.max_results_per_db,
                per_database_limits=search_cfg.per_database_limits or None,
            )
            all_papers = [paper for result in results for paper in result.papers]
            deduped, _ = deduplicate_papers(all_papers)
            state.deduped_papers = deduped
            state.dedup_count = dedup_count
            state.search_counts = await repository.get_search_counts(state.workflow_id)
            await repository.save_dedup_count(state.workflow_id, dedup_count)

            protocol_generator = ProtocolGenerator(output_dir=state.output_dir)
            protocol = protocol_generator.generate(state.workflow_id, state.review)
            protocol_markdown = protocol_generator.render_markdown(protocol, state.review)
            protocol_generator.write_markdown(state.workflow_id, protocol_markdown)
            await repository.save_checkpoint(state.workflow_id, "phase_2_search", papers_processed=len(deduped))
        if rc:
            total = sum(state.search_counts.values())
            rc.emit_phase_done(
                "phase_2_search",
                {"papers": len(deduped), "total_records": total, "dedup": state.dedup_count},
            )
            if rc.debug:
                rc.emit_debug_state(
                    "phase_2_search",
                    {
                        "search_counts": state.search_counts,
                        "dedup_count": state.dedup_count,
                        "connector_failures": len(state.connector_init_failures),
                    },
                )
        return ScreeningNode()


class ScreeningNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> ExtractionQualityNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start(
                "phase_3_screening",
                f"Screening {len(state.deduped_papers)} papers...",
                total=len(state.deduped_papers),
            )
            if rc.verbose:
                rc.console.print(
                    "[dim]Press Ctrl+C once to proceed with partial results, twice to abort.[/]"
                )
        assert state.review is not None
        assert state.settings is not None

        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            gate_runner = GateRunner(repository, state.settings)
            on_waiting = None
            if rc and rc.verbose:
                def _on_waiting(t: object, u: object, limit: object) -> None:
                    rc.log_rate_limit_wait(t, u, limit)  # type: ignore[union-attr]
                on_waiting = _on_waiting
            provider = LLMProvider(state.settings, repository, on_waiting=on_waiting)
            on_llm_call = None
            if rc and rc.verbose:
                def _on_llm_call(s: object, st: object, d: object, r: object, **kw: object) -> None:
                    rc.log_api_call(s, st, d, r, call_type="llm_screening", **kw)  # type: ignore[union-attr]
                on_llm_call = _on_llm_call
            use_real_client = (
                _llm_available(settings_cfg=state.settings)
                and (rc is None or not rc.offline)
            )
            llm_client = PydanticAIScreeningClient() if use_real_client else None
            on_progress = None
            if rc:
                def _on_progress(p: object, c: object, t: object) -> None:
                    rc.advance_screening(p, c, t)  # type: ignore[union-attr]
                on_progress = _on_progress
            on_prompt = None
            if rc and rc.debug:
                def _on_prompt(a: object, p: object, pid: object) -> None:
                    rc.log_prompt(a, p, pid)  # type: ignore[union-attr]
                on_prompt = _on_prompt
            should_proceed = (
                (lambda: rc.should_proceed_with_partial())
                if rc and hasattr(rc, "should_proceed_with_partial")
                else None
            )
            on_screening_decision = None
            if rc and hasattr(rc, "log_screening_decision"):
                def _on_screening_decision(pid: object, stg: object, dec: object) -> None:
                    rc.log_screening_decision(pid, stg, dec)  # type: ignore[union-attr]
                on_screening_decision = _on_screening_decision
            screener = DualReviewerScreener(
                repository=repository,
                provider=provider,
                review=state.review,
                settings=state.settings,
                llm_client=llm_client,
                on_llm_call=on_llm_call,
                on_progress=on_progress,
                on_prompt=on_prompt,
                should_proceed_with_partial=should_proceed,
                on_screening_decision=on_screening_decision,
            )

            # --- Pre-screening: BM25 ranking (when cap is set) or keyword filter ---
            cap = state.settings.screening.max_llm_screen
            paper_by_id = {p.paper_id: p for p in state.deduped_papers}

            if cap is not None:
                # BM25 ranks ALL deduped papers; top N go to LLM, tail is auto-excluded.
                # keyword_prefilter is NOT run as a hard gate - BM25 provides recall-safe ranking.
                papers_for_llm, pre_excluded = bm25_rank_and_cap(
                    state.deduped_papers, state.review, state.settings.screening
                )
                if pre_excluded:
                    pre_excluded_papers = [
                        paper_by_id[d.paper_id] for d in pre_excluded if d.paper_id in paper_by_id
                    ]
                    await repository.bulk_save_screening_decisions(
                        workflow_id=state.workflow_id,
                        stage="title_abstract",
                        papers=pre_excluded_papers,
                        decisions=pre_excluded,
                    )
                if rc and rc.verbose:
                    rc.console.print(
                        f"[dim]BM25 ranking: {len(state.deduped_papers)} papers scored, "
                        f"{len(papers_for_llm)} top-ranked forwarded to LLM, "
                        f"{len(pre_excluded)} auto-excluded (low relevance score).[/]"
                    )
            else:
                # Original path: keyword hard-gate -> all passers go to LLM.
                pre_excluded, papers_for_llm = keyword_prefilter(
                    state.deduped_papers, state.review, state.settings.screening
                )
                if pre_excluded:
                    pre_excluded_papers = [
                        paper_by_id[d.paper_id] for d in pre_excluded if d.paper_id in paper_by_id
                    ]
                    await repository.bulk_save_screening_decisions(
                        workflow_id=state.workflow_id,
                        stage="title_abstract",
                        papers=pre_excluded_papers,
                        decisions=pre_excluded,
                    )
                    if rc and rc.verbose:
                        rc.console.print(
                            f"[dim]Keyword pre-filter: {len(pre_excluded)} auto-excluded, "
                            f"{len(papers_for_llm)} forwarded to LLM screening.[/]"
                        )

            # --- Stage 1: title/abstract LLM dual-review ---
            stage1_llm = await screener.screen_batch(
                workflow_id=state.workflow_id,
                stage="title_abstract",
                papers=papers_for_llm,
            )
            # Merge pre-filter exclusions with LLM decisions for include_ids.
            # On resume, screen_batch skips already-processed papers and only returns
            # decisions made in this session.  We must also recover include/uncertain
            # decisions that were persisted during a previous (crashed) session so that
            # all survivors are forwarded to downstream phases.
            all_stage1 = list(pre_excluded) + list(stage1_llm)
            include_ids = {d.paper_id for d in all_stage1 if d.decision.value in ("include", "uncertain")}
            prior_ta_includes = await repository.get_title_abstract_include_ids(state.workflow_id)
            include_ids.update(prior_ta_includes)
            stage1_survivors = [p for p in state.deduped_papers if p.paper_id in include_ids]

            # --- Reset interrupt flag so stage 2 always runs to completion ---
            screener.reset_partial_flag()

            # --- Stage 2: full-text screening (skip if no real PDFs available) ---
            skip_fulltext = state.settings.screening.skip_fulltext_if_no_pdf
            if skip_fulltext and stage1_survivors:
                if rc and rc.verbose:
                    rc.console.print(
                        f"[dim]skip_fulltext_if_no_pdf=True: skipping full-text stage, "
                        f"treating {len(stage1_survivors)} stage-1 survivors as included.[/]"
                    )
                stage2: list = []
                state.included_papers = list(stage1_survivors)
            else:
                full_text_by_paper = {
                    paper.paper_id: (paper.abstract or paper.title or "").strip()
                    for paper in stage1_survivors
                }
                stage2 = await screener.screen_batch(
                    workflow_id=state.workflow_id,
                    stage="fulltext",
                    papers=stage1_survivors,
                    full_text_by_paper=full_text_by_paper,
                    coverage_report_path=state.artifacts["coverage_report"],
                )
                # Fallback guard: if stage 2 returned nothing for a non-empty input,
                # the interrupt flag was consumed -- fall back to stage-1 survivors.
                if stage1_survivors and not stage2:
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="screening_stage2_fallback",
                            decision="warning",
                            rationale=(
                                f"Stage 2 returned 0 decisions for {len(stage1_survivors)} "
                                f"stage-1 survivors; treating stage-1 include decisions as final."
                            ),
                            actor="workflow_run",
                            phase="phase_3_screening",
                        )
                    )
                    state.included_papers = list(stage1_survivors)
                else:
                    include_ids = {d.paper_id for d in stage2 if d.decision.value in ("include", "uncertain")}
                    state.included_papers = [p for p in stage1_survivors if p.paper_id in include_ids]

            await gate_runner.run_screening_safeguard_gate(
                workflow_id=state.workflow_id,
                phase="phase_3_screening",
                passed_screening=len(state.included_papers),
            )
            pre_filter_method = "bm25_rank_and_cap" if cap is not None else "keyword_prefilter"
            await repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_summary",
                    decision="completed",
                    rationale=(
                        f"pre_filter_method={pre_filter_method}, "
                        f"pre_filtered={len(pre_excluded)}, "
                        f"title_abstract_llm={len(stage1_llm)}, "
                        f"fulltext_total={len(stage2)}, "
                        f"included={len(state.included_papers)}"
                    ),
                    actor="workflow_run",
                    phase="phase_3_screening",
                )
            )
            checkpoint_status = (
                "partial"
                if (rc and rc.should_proceed_with_partial())
                else "completed"
            )
            await repository.save_checkpoint(
                state.workflow_id,
                "phase_3_screening",
                papers_processed=len(state.included_papers),
                status=checkpoint_status,
            )
            if rc and rc.verbose:
                summary_rows = await repository.get_screening_summary(state.workflow_id)
                if summary_rows:
                    table = Table(title="Screening Summary")
                    table.add_column("Paper ID", style="dim")
                    table.add_column("Stage", style="cyan")
                    table.add_column("Decision", style="bold")
                    table.add_column("Reason", style="white")
                    for paper_id, stage, decision, rationale in summary_rows:
                        table.add_row(paper_id[:16] + "...", stage, decision, rationale)
                    rc.console.print(table)
        if rc:
            rc.emit_phase_done(
                "phase_3_screening",
                {"included": len(state.included_papers), "screened": len(state.deduped_papers)},
            )
            if rc.debug:
                rc.emit_debug_state(
                    "phase_3_screening",
                    {"included_papers": len(state.included_papers), "screened": len(state.deduped_papers)},
                )
        return ExtractionQualityNode()


class ExtractionQualityNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> SynthesisNode:
        state = ctx.state
        rc = _rc(state)
        assert state.review is not None
        assert state.settings is not None

        router = StudyRouter()
        grade = GradeAssessor()

        rob2_rows: list = []
        records: list[ExtractionRecord] = list(state.extraction_records)
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            already_extracted = await repository.get_extraction_record_ids(state.workflow_id)
            to_process = [p for p in state.included_papers if p.paper_id not in already_extracted]
            if rc:
                rc.emit_phase_start(
                    "phase_4_extraction_quality",
                    f"Extracting {len(to_process)} papers...",
                    total=len(to_process),
                )
            gate_runner = GateRunner(repository, state.settings)
            provider = LLMProvider(state.settings, repository)
            on_classify = None
            if rc and rc.verbose:
                def _on_classify(**kw):
                    rc.log_api_call(**kw)
                on_classify = _on_classify
            classifier = StudyClassifier(
                provider=provider,
                repository=repository,
                review=state.review,
                on_llm_call=on_classify,
            )
            use_llm = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
            llm_gemini = PydanticAIClient() if use_llm else None
            extractor = ExtractionService(
                repository=repository,
                llm_client=llm_gemini,
                settings=state.settings,
                review=state.review,
                provider=provider if use_llm else None,
            )
            rob2 = Rob2Assessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            robins_i = RobinsIAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            casp = CaspAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            not_applicable_paper_ids: list[str] = []

            for i, paper in enumerate(to_process):
                if rc and rc.verbose:
                    rc.console.print(
                        f"  Extracting {paper.paper_id[:12]}... ({i + 1}/{len(to_process)})"
                    )
                full_text = (paper.abstract or paper.title or "").strip()
                try:
                    design = await classifier.classify(state.workflow_id, paper)
                except Exception as exc:
                    design = StudyDesign.NON_RANDOMIZED
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="study_design_classification",
                            paper_id=paper.paper_id,
                            decision=design.value,
                            rationale=f"Classifier error fallback: {type(exc).__name__}: {exc}",
                            actor="workflow_run",
                            phase="phase_4_extraction_quality",
                        )
                    )
                try:
                    record = await extractor.extract(
                        workflow_id=state.workflow_id,
                        paper=paper,
                        study_design=design,
                        full_text=full_text,
                    )
                    records.append(record)
                    if rc:
                        rc.advance_screening("phase_4_extraction_quality", i + 1, len(to_process))

                    tool = router.route_tool(record)
                    rob_judgment = "not_applicable"
                    if tool == "rob2":
                        assessment = await rob2.assess(record, full_text=full_text)
                        await repository.save_rob2_assessment(state.workflow_id, assessment)
                        rob_judgment = (
                            assessment.overall_judgment.value
                            if hasattr(assessment, "overall_judgment")
                            else "unknown"
                        )
                    elif tool == "robins_i":
                        assessment = await robins_i.assess(record, full_text=full_text)
                        await repository.save_robins_i_assessment(state.workflow_id, assessment)
                        rob_judgment = (
                            assessment.overall_judgment.value
                            if hasattr(assessment, "overall_judgment")
                            else "unknown"
                        )
                    elif tool == "casp":
                        assessment = await casp.assess(record, full_text=full_text)
                        rob_judgment = getattr(assessment, "overall_summary", "completed")[:80]
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="casp_assessment",
                                paper_id=record.paper_id,
                                decision="completed",
                                rationale=assessment.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    else:
                        # not_applicable: systematic reviews, technical reports, narrative papers.
                        # ROBINS-I and RoB2 do not apply; record for figure disclosure.
                        not_applicable_paper_ids.append(record.paper_id)
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="rob_not_applicable",
                                paper_id=record.paper_id,
                                decision="not_applicable",
                                rationale=(
                                    f"Study design '{record.study_design.value}' is not an "
                                    "interventional study; ROBINS-I/RoB2 assessment not applicable."
                                ),
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )

                    grade_assessment = grade.assess_outcome(
                        outcome_name="primary_outcome",
                        number_of_studies=1,
                        study_design=record.study_design,
                    )
                    await repository.save_grade_assessment(state.workflow_id, grade_assessment)

                    if rc and rc.verbose:
                        extraction_summary = (
                            record.results_summary.get("summary") or ""
                        )[:300]
                        rc.log_extraction_paper(
                            paper_id=paper.paper_id,
                            design=design.value,
                            extraction_summary=extraction_summary,
                            rob_judgment=rob_judgment,
                        )
                except Exception as exc:
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="extraction_error",
                            paper_id=paper.paper_id,
                            decision="error",
                            rationale=f"Extraction/quality error, paper skipped: {type(exc).__name__}: {exc}",
                            actor="workflow_run",
                            phase="phase_4_extraction_quality",
                        )
                    )
                    if rc:
                        rc.advance_screening("phase_4_extraction_quality", i + 1, len(to_process))

            rob2_rows, robins_i_rows = await repository.load_rob_assessments(state.workflow_id)
            completeness_ratio = 1.0 if not records else (
                sum(1 for record in records if (record.results_summary.get("summary") or "").strip() != "")
                / len(records)
            )
            await gate_runner.run_extraction_completeness_gate(
                workflow_id=state.workflow_id,
                phase="phase_4_extraction_quality",
                completeness_ratio=completeness_ratio,
            )
            await gate_runner.run_citation_lineage_gate(
                workflow_id=state.workflow_id,
                phase="phase_4_extraction_quality",
                unresolved_items=0,
            )
            _rob_paper_lookup = {p.paper_id: p for p in state.included_papers}
            render_rob_traffic_light(
                rob2_rows,
                robins_i_rows,
                state.artifacts["rob_traffic_light"],
                paper_lookup=_rob_paper_lookup,
                not_applicable_count=len(not_applicable_paper_ids),
                rob2_output_path=state.artifacts.get("rob2_traffic_light"),
            )
            await repository.save_checkpoint(
                state.workflow_id,
                "phase_4_extraction_quality",
                papers_processed=len(records),
            )
        state.extraction_records = records
        if rc:
            rc.emit_phase_done("phase_4_extraction_quality", {"records": len(records)})
            if rc.debug:
                rc.emit_debug_state(
                    "phase_4_extraction_quality",
                    {"extraction_records": len(records)},
                )
        return SynthesisNode()


def _try_meta_analysis(
    records: list,
    outcome_name: str,
    het_threshold: float,
    effect_measure: str,
    forest_path: str,
    funnel_path: str,
    funnel_min_studies: int = 10,
) -> tuple:
    """Attempt to pool effect sizes from ExtractionRecord.outcomes.

    Returns (MetaAnalysisResult | None, forest_path | None, funnel_path | None).
    Effect sizes are extracted from outcomes[*].effect_size and outcomes[*].se keys
    (populated by LLM extraction; absent in heuristic extraction).
    No LLM statistics -- all pooling done via statsmodels pool_effects().
    """
    import math
    effects: list[float] = []
    variances: list[float] = []
    labels: list[str] = []

    for record in records:
        for outcome in (record.outcomes or []):
            name = outcome.get("name", "").lower().replace(" ", "_")
            if outcome_name not in name:
                continue
            effect_str = outcome.get("effect_size") or outcome.get("effect")
            se_str = outcome.get("se") or outcome.get("standard_error")
            var_str = outcome.get("variance")
            try:
                # Attempt to parse the numeric part (e.g. "SMD=0.45" -> 0.45)
                if effect_str:
                    for tok in str(effect_str).replace("=", " ").split():
                        try:
                            effect_val = float(tok)
                            break
                        except ValueError:
                            continue
                    else:
                        effect_val = None
                else:
                    effect_val = None

                if var_str:
                    variance_val = float(str(var_str).split()[-1])
                elif se_str:
                    se_val = float(str(se_str).split()[-1])
                    variance_val = se_val ** 2
                else:
                    variance_val = None
            except (ValueError, TypeError):
                effect_val = None
                variance_val = None

            if effect_val is not None and variance_val is not None and variance_val > 0:
                effects.append(effect_val)
                variances.append(variance_val)
                labels.append(record.paper_id[:12])
                break

    if len(effects) < 2:
        return None, None, None

    try:
        meta_result = pool_effects(
            outcome_name=outcome_name,
            effect_measure=effect_measure,
            effects=effects,
            variances=variances,
            heterogeneity_threshold=het_threshold,
        )
    except Exception:
        return None, None, None

    rendered_forest: str | None = None
    rendered_funnel: str | None = None

    try:
        rendered_forest = render_forest_plot(
            effects=effects,
            variances=variances,
            labels=labels,
            output_path=forest_path,
            title=f"Forest plot: {outcome_name} ({effect_measure})",
        )
        meta_result = meta_result.model_copy(update={"forest_plot_path": rendered_forest})
    except Exception:
        pass

    if len(effects) >= funnel_min_studies:
        try:
            ses = [math.sqrt(v) for v in variances]
            rendered_funnel = render_funnel_plot(
                effect_sizes=effects,
                standard_errors=ses,
                pooled_effect=meta_result.pooled_effect,
                output_path=funnel_path,
                title=f"Funnel plot: {outcome_name}",
                minimum_studies=funnel_min_studies,
            )
            if rendered_funnel:
                meta_result = meta_result.model_copy(update={"funnel_plot_path": rendered_funnel})
        except Exception:
            pass

    return meta_result, rendered_forest, rendered_funnel


class SynthesisNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> FinalizeNode:
        state = ctx.state
        rc = _rc(state)
        assert state.settings is not None
        if rc:
            rc.emit_phase_start("phase_5_synthesis", "Building synthesis...", total=1)
        feasibility = assess_meta_analysis_feasibility(state.extraction_records)
        narrative = build_narrative_synthesis("primary_outcome", state.extraction_records)

        # Attempt quantitative meta-analysis for each feasible outcome group
        meta_result = None
        rendered_forest = None
        rendered_funnel = None
        if feasibility.feasible and state.settings.meta_analysis.enabled:
            het_threshold = float(state.settings.meta_analysis.heterogeneity_threshold)
            effect_measure = state.settings.meta_analysis.effect_measure_continuous
            funnel_min = state.settings.meta_analysis.funnel_plot_minimum_studies
            for group in feasibility.groupings:
                meta_result, rendered_forest, rendered_funnel = _try_meta_analysis(
                    records=state.extraction_records,
                    outcome_name=group,
                    het_threshold=het_threshold,
                    effect_measure=effect_measure,
                    forest_path=state.artifacts["fig_forest_plot"],
                    funnel_path=state.artifacts["fig_funnel_plot"],
                    funnel_min_studies=funnel_min,
                )
                if meta_result is not None:
                    break

        if rc and rc.verbose:
            rc.log_synthesis(
                feasible=feasibility.feasible,
                groups=feasibility.groupings,
                rationale=feasibility.rationale,
                n_studies=narrative.n_studies,
                direction=narrative.effect_direction_summary,
            )
            if meta_result is not None:
                rc.console.print(
                    f"  Meta-analysis: {meta_result.model}={meta_result.model}, "
                    f"I2={meta_result.i_squared:.1f}%, forest={rendered_forest is not None}, "
                    f"funnel={rendered_funnel is not None}"
                )
            else:
                rc.console.print(
                    "  Meta-analysis: insufficient numeric effect data; using narrative synthesis."
                )

        synthesis_payload: dict = {
            "feasibility": feasibility.model_dump(),
            "narrative": narrative.model_dump(),
        }
        if meta_result is not None:
            synthesis_payload["meta_analysis"] = meta_result.model_dump()

        Path(state.artifacts["narrative_synthesis"]).write_text(
            json.dumps(synthesis_payload, indent=2),
            encoding="utf-8",
        )
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            await repository.save_synthesis_result(state.workflow_id, feasibility, narrative)
            await repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="synthesis_summary",
                    decision="completed",
                    rationale=(
                        f"feasible={feasibility.feasible}, groups={len(feasibility.groupings)}, "
                        f"narrative_studies={narrative.n_studies}, "
                        f"meta_analysis={'yes' if meta_result else 'no'}, "
                        f"forest={'yes' if rendered_forest else 'no'}, "
                        f"funnel={'yes' if rendered_funnel else 'no'}"
                    ),
                    actor="workflow_run",
                    phase="phase_5_synthesis",
                )
            )
            await repository.save_checkpoint(
                state.workflow_id, "phase_5_synthesis",
                papers_processed=len(state.extraction_records),
            )
        if rc:
            rc.emit_phase_done(
                "phase_5_synthesis",
                {
                    "feasible": feasibility.feasible,
                    "n_studies": len(state.extraction_records),
                    "meta_analysis": meta_result is not None,
                    "forest_plot": rendered_forest is not None,
                    "funnel_plot": rendered_funnel is not None,
                },
            )
            if rc.debug:
                rc.emit_debug_state(
                    "phase_5_synthesis",
                    {"feasible": feasibility.feasible, "n_studies": len(state.extraction_records)},
                )
        return WritingNode()


class WritingNode(BaseNode[ReviewState]):
    """Write manuscript sections, validate citations, save drafts."""

    async def run(self, ctx: GraphRunContext[ReviewState]) -> FinalizeNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start(
                "phase_6_writing",
                f"Writing manuscript ({len(state.included_papers)} papers)...",
                total=len(SECTIONS),
            )
        assert state.review is not None
        assert state.settings is not None

        # Load narrative synthesis: DB is the canonical source; JSON file is the fallback
        # for runs that predate the synthesis_results table.
        narrative: dict | None = None
        async with get_db(state.db_path) as _nav_db:
            _synthesis = await WorkflowRepository(_nav_db).load_synthesis_result(state.workflow_id)
            if _synthesis is not None:
                _feas, _narr = _synthesis
                narrative = {"feasibility": _feas.model_dump(), "narrative": _narr.model_dump()}
        if narrative is None:
            narrative_path = Path(state.artifacts["narrative_synthesis"])
            if narrative_path.exists():
                try:
                    narrative = json.loads(narrative_path.read_text(encoding="utf-8"))
                except Exception:
                    narrative = None

        style_patterns, citation_catalog = prepare_writing_context(
            state.included_papers, narrative, state.settings
        )

        sections_written: list[str] = []
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)

            prisma_counts = await build_prisma_counts(
                repository,
                state.workflow_id,
                state.dedup_count,
                included_qualitative=0,
                included_quantitative=len(state.included_papers),
            )
            render_prisma_diagram(prisma_counts, state.artifacts["prisma_diagram"])
            render_timeline(state.included_papers, state.artifacts["timeline"])
            render_geographic(state.included_papers, state.artifacts["geographic"])
            if rc and rc.verbose:
                rc.console.print(
                    f"  PRISMA: {prisma_counts} -> {Path(state.artifacts['prisma_diagram']).name}"
                )
                rc.console.print(
                    f"  Timeline: {Path(state.artifacts['timeline']).name}"
                )
                rc.console.print(
                    f"  Geographic: {Path(state.artifacts['geographic']).name}"
                )
            citation_repo = CitationRepository(db)
            completed = await repository.get_completed_sections(state.workflow_id)
            provider = LLMProvider(state.settings, repository)

            await register_citations_from_papers(citation_repo, state.included_papers)

            # Build grounding data from real pipeline outputs so the writing LLM
            # cannot hallucinate counts, statistics, or citation keys.
            grounding = build_writing_grounding(
                prisma_counts=prisma_counts,
                extraction_records=state.extraction_records,
                included_papers=state.included_papers,
                narrative=narrative,
                citation_catalog=citation_catalog,
            )

            def _on_write(**kw):
                if rc:
                    rc.log_api_call(**kw)

            for i, section in enumerate(SECTIONS):
                if section in completed:
                    if rc and rc.verbose:
                        rc.console.print(f"  Skipping {section} (already done)")
                    cursor = await db.execute(
                        """
                        SELECT content FROM section_drafts
                        WHERE workflow_id = ? AND section = ?
                        ORDER BY version DESC LIMIT 1
                        """,
                        (state.workflow_id, section),
                    )
                    row = await cursor.fetchone()
                    if row:
                        sections_written.append(row[0])
                    if rc:
                        rc.advance_screening("phase_6_writing", i + 1, len(SECTIONS))
                    continue

                if rc and rc.verbose:
                    rc.console.print(f"  Writing section: {section}...")
                context = get_section_context(section)
                word_limit = get_section_word_limit(section)
                content = await write_section_with_validation(
                    section=section,
                    context=context,
                    workflow_id=state.workflow_id,
                    review=state.review,
                    settings=state.settings,
                    citation_repo=citation_repo,
                    citation_catalog=citation_catalog,
                    style_patterns=style_patterns,
                    word_limit=word_limit,
                    on_llm_call=_on_write if rc else None,
                    provider=provider,
                    grounding=grounding,
                )

                # Humanization pass: apply configured number of iterations
                writing_cfg = getattr(state.settings, "writing", None)
                do_humanize = getattr(writing_cfg, "humanization", False)
                humanize_iters = getattr(writing_cfg, "humanization_iterations", 1)
                use_llm_write = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
                if do_humanize and use_llm_write:
                    humanizer_agent = state.settings.agents.get("humanizer")
                    h_model = humanizer_agent.model if humanizer_agent else "google-gla:gemini-2.5-pro"
                    h_temp = humanizer_agent.temperature if humanizer_agent else 0.3
                    if rc and rc.verbose:
                        rc.console.print(
                            f"    Humanizing {section} ({humanize_iters} pass(es))..."
                        )
                    for _ in range(humanize_iters):
                        content = await humanize_async(
                            content, model=h_model, temperature=h_temp, max_chars=4000,
                            provider=provider if use_llm_write else None,
                        )

                word_count = len(content.split())
                draft = SectionDraft(
                    workflow_id=state.workflow_id,
                    section=section,
                    version=1,
                    content=content,
                    claims_used=[],
                    citations_used=[],
                    word_count=word_count,
                )
                await repository.save_section_draft(draft)
                sections_written.append(content)
                if rc:
                    rc.advance_screening("phase_6_writing", i + 1, len(SECTIONS))

            await repository.save_checkpoint(
                state.workflow_id, "phase_6_writing", papers_processed=len(SECTIONS)
            )
            citation_rows = await CitationRepository(db).get_all_citations_for_export()

        manuscript_path = Path(state.artifacts["manuscript_md"])
        body = "\n\n".join(sections_written)
        full_manuscript = assemble_submission_manuscript(
            body=body,
            manuscript_path=manuscript_path,
            artifacts=state.artifacts,
            citation_rows=citation_rows,
        )
        manuscript_path.write_text(full_manuscript, encoding="utf-8")

        if rc:
            rc.emit_phase_done("phase_6_writing", {"sections": len(sections_written)})
        return FinalizeNode()


class FinalizeNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> End[dict[str, str | int | dict[str, int] | dict[str, str]]]:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("finalize", "Writing run summary...")
        # Filter artifact paths: only include entries that either are the run_summary
        # itself (written below) or point to a file that actually exists on disk.
        # This prevents broken image links in the UI when optional figures (e.g.
        # forest/funnel plot) were not generated because meta-analysis was infeasible.
        run_summary_key = "run_summary"
        filtered_artifacts = {
            k: v
            for k, v in state.artifacts.items()
            if k == run_summary_key or os.path.isfile(v)
        }
        summary: dict[str, str | int | dict[str, int] | dict[str, str]] = {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "log_dir": state.log_dir,
            "output_dir": state.output_dir,
            "search_counts": state.search_counts,
            "dedup_count": state.dedup_count,
            "connector_init_failures": state.connector_init_failures,
            "included_papers": len(state.included_papers),
            "extraction_records": len(state.extraction_records),
            "artifacts": filtered_artifacts,
        }
        Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        await update_registry_status(state.run_root, state.workflow_id, "completed")
        async with get_db(state.db_path) as db:
            await WorkflowRepository(db).update_workflow_status(state.workflow_id, "completed")
        if rc and rc.verbose:
            rc.console.print(f"  Run summary: {state.artifacts['run_summary']}")
            rc.console.print(f"  Output dir: {state.output_dir}")
        if rc:
            rc.emit_phase_done("finalize")
        return End(summary)


RUN_GRAPH = Graph(
    nodes=[
        StartNode,
        ResumeStartNode,
        SearchNode,
        ScreeningNode,
        ExtractionQualityNode,
        SynthesisNode,
        WritingNode,
        FinalizeNode,
    ],
    state_type=ReviewState,
    run_end_type=dict,
)


def _make_sigint_handler(rc: RunContext):
    """Return a SIGINT handler that sets proceed_with_partial on first Ctrl+C, aborts on second."""

    def handler() -> None:
        if rc.should_proceed_with_partial():
            raise KeyboardInterrupt
        rc.proceed_with_partial_requested[0] = True
        if rc.verbose:
            rc.console.print("[yellow]Proceeding with partial screening results...[/]")

    return handler


async def run_workflow_resume(
    workflow_id: str | None = None,
    topic: str | None = None,
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    run_root: str = "runs",
    run_context: RunContext | None = None,
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
        raise FileNotFoundError(
            "Workflow not found or db file missing. It may have been deleted."
        )
    state, next_phase = await load_resume_state(
        db_path=entry.db_path,
        workflow_id=entry.workflow_id,
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
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
        phase_label = f"phase {phase_count}/6" if phase_count < 6 else "finalize"
        if run_context and run_context.console:
            from rich.prompt import Confirm
            if Confirm.ask(
                f"Found existing run for this topic ({phase_label} complete). Resume?",
                default=True,
                console=run_context.console,
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
                resp = input(f"Found existing run for this topic ({phase_label} complete). Resume? [Y/n]: ").strip().lower()
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
            pass  # Windows: add_signal_handler not available

    start = StartNode()
    initial = ReviewState(
        review_path=review_path,
        settings_path=settings_path,
        run_root=run_root,
        run_context=run_context,
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
