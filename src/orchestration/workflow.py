"""Single-path workflow orchestration for `run`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import signal

_log = logging.getLogger(__name__)
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.table import Table

from src.citation.ledger import CitationLedger
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
from src.export.markdown_refs import assemble_submission_manuscript, is_extraction_failed
from src.extraction import ExtractionService, StudyClassifier
from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import DecisionLogEntry, ExtractionRecord, GateStatus, SectionDraft, StudyDesign
from src.models.diagrams import (
    FlowchartDiagramInput,
    FlowchartPhase,
    FrameworkDiagramInput,
    TaxonomyCategory,
    TaxonomyDiagramInput,
)
from src.orchestration.context import RunContext
from src.orchestration.embedding_node import EmbeddingNode
from src.orchestration.gates import GateRunner
from src.orchestration.knowledge_graph_node import KnowledgeGraphNode
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState
from src.prisma import build_prisma_counts, render_prisma_diagram
from src.protocol.generator import ProtocolGenerator
from src.quality import (
    CaspAssessor,
    GradeAssessor,
    MmatAssessor,
    Rob2Assessor,
    RobinsIAssessor,
    StudyRouter,
)
from src.rag.embedder import embed_query as rag_embed_query
from src.rag.hyde import generate_hyde_document
from src.rag.reranker import rerank_chunks
from src.rag.retriever import RAGRetriever
from src.screening.dual_screener import DualReviewerScreener
from src.screening.gemini_client import PydanticAIScreeningClient
from src.screening.keyword_filter import bm25_rank_and_cap, keyword_prefilter, metadata_prefilter
from src.screening.reliability import compute_cohens_kappa, log_reliability_to_decision_log
from src.search.arxiv import ArxivConnector
from src.search.base import SearchConnector
from src.search.citation_chasing import CitationChaser
from src.search.clinicaltrials import ClinicalTrialsConnector
from src.search.crossref import CrossrefConnector
from src.search.csv_import import parse_masterlist_csv, parse_supplementary_csvs
from src.search.embase import EmbaseConnector
from src.search.deduplication import deduplicate_papers
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.pdf_retrieval import PDFRetriever
from src.search.perplexity_search import PerplexitySearchConnector
from src.search.pubmed import PubMedConnector
from src.search.scopus import ScopusConnector
from src.search.semantic_scholar import SemanticScholarConnector
from src.search.strategy import SearchStrategyCoordinator
from src.search.web_of_science import WebOfScienceConnector
from src.synthesis import assess_meta_analysis_feasibility, build_narrative_synthesis
from src.synthesis.contradiction_detector import detect_contradictions
from src.synthesis.meta_analysis import pool_effects
from src.synthesis.sensitivity import run_sensitivity_analysis
from src.utils import structured_log
from src.utils.logging_paths import create_run_paths
from src.visualization import (
    render_geographic,
    render_rob_traffic_light,
    render_timeline,
)
from src.visualization.concept_diagrams import render_concept_diagrams
from src.visualization.forest_plot import render_forest_plot
from src.visualization.funnel_plot import render_funnel_plot
from src.writing.citation_grounding import repair_hallucinated_citekeys, verify_citation_grounding
from src.writing.context_builder import build_writing_grounding
from src.writing.contradiction_resolver import (
    build_conflicting_evidence_section,
    generate_contradiction_paragraph,
)
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
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


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


def _llm_available(settings: ReviewState | None = None, settings_cfg: SettingsConfig | None = None) -> bool:  # noqa: F821
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
            elif normalized == "scopus":
                connectors.append(ScopusConnector(workflow_id))
            elif normalized in {"web_of_science", "wos"}:
                connectors.append(WebOfScienceConnector(workflow_id))
            elif normalized in {"clinicaltrials", "clinicaltrials_gov"}:
                connectors.append(ClinicalTrialsConnector(workflow_id))
            elif normalized == "embase":
                connectors.append(EmbaseConnector(workflow_id))
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
    ) -> (
        SearchNode
        | ScreeningNode
        | HumanReviewCheckpointNode
        | ExtractionQualityNode
        | EmbeddingNode
        | SynthesisNode
        | KnowledgeGraphNode
        | WritingNode
        | FinalizeNode
    ):
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
        if phase == "phase_4b_embedding":
            return EmbeddingNode()
        if phase == "phase_5_synthesis":
            return SynthesisNode()
        if phase == "phase_5b_knowledge_graph":
            return KnowledgeGraphNode()
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
        state.artifacts["concept_taxonomy"] = str(run_paths.run_dir / "fig_concept_taxonomy.svg")
        state.artifacts["conceptual_framework"] = str(run_paths.run_dir / "fig_conceptual_framework.svg")
        state.artifacts["methodology_flow"] = str(run_paths.run_dir / "fig_methodology_flow.svg")
        state.artifacts["evidence_network"] = str(run_paths.run_dir / "fig_evidence_network.png")

        # Snapshot the review config at run start so re-extraction and post-hoc
        # scripts always use the config that produced this run, not a later config.
        import shutil as _shutil

        _config_src = Path("config/review.yaml")
        if _config_src.exists():
            _shutil.copy(_config_src, run_paths.run_dir / "config_snapshot.yaml")

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

        # --- CSV master list bypass ---
        # When masterlist_csv_path is set the user has pre-assembled papers
        # externally. We skip all connectors but keep every other side-effect
        # (DB writes, SSE events, checkpointing, PRISMA rows, protocol) identical
        # to the normal search branch so that no downstream node breaks.
        if state.review.masterlist_csv_path:
            if rc:
                rc.emit_phase_start("phase_2_search", "Loading master list...", total=1)
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

                csv_result = parse_masterlist_csv(state.review.masterlist_csv_path, state.workflow_id)
                await repository.save_search_result(csv_result)

                if rc:
                    rc.log_connector_result(
                        name="CSV Import",
                        status="success",
                        records=csv_result.records_retrieved,
                        query=csv_result.search_query,
                        date_start=None,
                        date_end=None,
                        error=None,
                    )
                    rc.advance_screening("phase_2_search", 1, 1)
                structured_log.log_connector_result(
                    connector="CSV Import",
                    status="success",
                    records=csv_result.records_retrieved,
                    error=None,
                )

                await gate_runner.run_search_volume_gate(
                    state.workflow_id, "phase_2_search", csv_result.records_retrieved
                )
                if state.settings.gates.profile == "strict":
                    gr = await repository.get_latest_gate_result(state.workflow_id, "phase_2_search", "search_volume")
                    if gr and gr.status == GateStatus.FAILED:
                        err_msg = (
                            f"Search volume gate failed: {gr.actual_value or 0} records "
                            f"(minimum {gr.threshold or '?'}). Cannot proceed."
                        )
                        summary = {
                            "workflow_id": state.workflow_id,
                            "status": "failed",
                            "error": err_msg,
                            "gate": "search_volume",
                            "phase": "phase_2_search",
                        }
                        Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
                        await repository.update_workflow_status(state.workflow_id, "failed")
                        await update_registry_status(state.run_root, state.workflow_id, "failed")
                        if rc:
                            rc.emit_phase_done("phase_2_search", {"error": err_msg})
                        return End(summary)

                deduped, dedup_count = deduplicate_papers(csv_result.papers)
                state.deduped_papers = deduped
                state.dedup_count = dedup_count
                state.connector_init_failures = {}
                state.search_counts = await repository.get_search_counts(state.workflow_id)
                await repository.save_dedup_count(state.workflow_id, dedup_count)

                protocol_generator = ProtocolGenerator(output_dir=state.output_dir)
                protocol = protocol_generator.generate(state.workflow_id, state.review)
                protocol_markdown = protocol_generator.render_markdown(protocol, state.review)
                protocol_generator.write_markdown(state.workflow_id, protocol_markdown)
                if not await repository.has_checkpoint_integrity(state.workflow_id):
                    await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)
                await repository.save_checkpoint(state.workflow_id, "phase_2_search", papers_processed=len(deduped))
            if rc:
                total = sum(state.search_counts.values())
                rc.emit_phase_done(
                    "phase_2_search",
                    {"papers": len(deduped), "total_records": total, "dedup": dedup_count},
                )
                if rc.debug:
                    rc.emit_debug_state(
                        "phase_2_search",
                        {
                            "search_counts": state.search_counts,
                            "dedup_count": state.dedup_count,
                            "connector_failures": 0,
                        },
                    )
            return ScreeningNode()
        # --- end CSV branch ---

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

            # Living review delta: merge previously included papers from the parent
            # run DB before searching, so they are present when the dedup and
            # living-review DOI-skip logic runs. This avoids re-screening papers
            # that were already adjudicated in the prior run.
            if state.parent_db_path:
                try:
                    from src.db.repositories import merge_papers_from_parent

                    n_merged = await merge_papers_from_parent(state.parent_db_path, db)
                    logger.info(
                        "Living refresh: merged %d papers from parent DB %s",
                        n_merged,
                        state.parent_db_path,
                    )
                    if rc:
                        rc._emit(
                            {
                                "type": "living_refresh_merge",
                                "merged_papers": n_merged,
                                "parent_db": state.parent_db_path,
                            }
                        )
                except Exception as _merge_err:
                    logger.warning(
                        "Living refresh: parent DB merge failed (%s) -- proceeding as fresh run",
                        _merge_err,
                    )

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
                structured_log.log_connector_result(connector=name, status=status, records=records, error=error)
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
            state.search_queries = coordinator.query_map
            if state.settings.gates.profile == "strict":
                gr = await repository.get_latest_gate_result(state.workflow_id, "phase_2_search", "search_volume")
                if gr and gr.status == GateStatus.FAILED:
                    err_msg = (
                        f"Search volume gate failed: {gr.actual_value or 0} records "
                        f"(minimum {gr.threshold or '?'}). Cannot proceed."
                    )
                    summary = {
                        "workflow_id": state.workflow_id,
                        "status": "failed",
                        "error": err_msg,
                        "gate": "search_volume",
                        "phase": "phase_2_search",
                    }
                    Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
                    await repository.update_workflow_status(state.workflow_id, "failed")
                    await update_registry_status(state.run_root, state.workflow_id, "failed")
                    if rc:
                        rc.emit_phase_done("phase_2_search", {"error": err_msg})
                    return End(summary)

            all_papers = [paper for result in results for paper in result.papers]

            # Supplementary CSV import: merge Embase/CINAHL/etc. exports with connector results.
            # Each file produces its own SearchResult (for PRISMA accuracy) and its papers
            # are appended to all_papers before deduplication.
            supp_paths = state.review.supplementary_csv_paths if state.review else []
            if supp_paths:
                try:
                    supp_results = parse_supplementary_csvs(supp_paths, state.workflow_id)
                    for sr in supp_results:
                        await repository.save_search_result(sr)
                        all_papers.extend(sr.papers)
                        if rc:
                            rc.log_connector_result(
                                name=sr.database_name,
                                status="success",
                                records=sr.records_retrieved,
                                query=sr.search_query,
                                date_start=None,
                                date_end=None,
                                error=None,
                            )
                        _log.info(
                            "Supplementary CSV '%s': loaded %d papers",
                            sr.database_name,
                            sr.records_retrieved,
                        )
                except Exception as _supp_err:
                    _log.warning("Supplementary CSV import failed: %s", _supp_err)

            # Living review: skip papers whose DOIs were already screened in a prior run.
            if state.review.living_review:
                known_dois: set[str] = set()
                async with db.execute(
                    "SELECT DISTINCT p.doi FROM papers p "
                    "JOIN screening_decisions sd ON p.paper_id = sd.paper_id "
                    "WHERE p.doi IS NOT NULL"
                ) as _cur:
                    async for _row in _cur:
                        if _row[0]:
                            known_dois.add(_row[0].lower().strip())
                before_count = len(all_papers)
                all_papers = [p for p in all_papers if not (p.doi and p.doi.lower().strip() in known_dois)]
                _log.info(
                    "Living review: skipped %d already-screened papers; %d new candidates",
                    before_count - len(all_papers),
                    len(all_papers),
                )

            deduped, _ = deduplicate_papers(all_papers)

            # Backfill abstracts for Scopus papers (Search API never returns dc:description)
            scopus_no_abstract = sum(1 for p in deduped if p.source_database == "scopus" and not p.abstract and p.doi)
            if scopus_no_abstract > 0:
                try:
                    from src.search.scopus import enrich_scopus_abstracts

                    enriched_count = await enrich_scopus_abstracts(deduped)
                    logger.info(
                        "SearchNode: enriched %d/%d Scopus abstracts via Abstract API",
                        enriched_count,
                        scopus_no_abstract,
                    )
                except Exception as _enrich_err:
                    logger.warning(
                        "SearchNode: Scopus abstract enrichment failed (%s) -- proceeding",
                        _enrich_err,
                    )

            state.deduped_papers = deduped
            state.dedup_count = dedup_count
            state.search_counts = await repository.get_search_counts(state.workflow_id)
            await repository.save_dedup_count(state.workflow_id, dedup_count)

            protocol_generator = ProtocolGenerator(output_dir=state.output_dir)
            protocol = protocol_generator.generate(state.workflow_id, state.review)
            protocol_markdown = protocol_generator.render_markdown(protocol, state.review)
            protocol_generator.write_markdown(state.workflow_id, protocol_markdown)
            if not await repository.has_checkpoint_integrity(state.workflow_id):
                await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)
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
    async def run(self, ctx: GraphRunContext[ReviewState]) -> HumanReviewCheckpointNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start(
                "phase_3_screening",
                f"Screening {len(state.deduped_papers)} papers...",
                total=len(state.deduped_papers),
            )
            if rc.verbose:
                rc.console.print("[dim]Press Ctrl+C once to proceed with partial results, twice to abort.[/]")
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
            use_real_client = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
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

                def _on_screening_decision(
                    pid: object,
                    stg: object,
                    dec: object,
                    reason: object = None,
                    conf: float | None = None,
                ) -> None:
                    rc.log_screening_decision(pid, stg, dec, str(reason) if reason is not None else None, conf)  # type: ignore[union-attr]

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

            # --- Gate 0: Metadata pre-filter (no LLM cost) ---
            # Reject papers with no title, no content (abstract+doi+url), or no year
            # before any keyword scoring or LLM call. These cannot be meaningfully
            # screened or extracted from and would produce garbage table rows.
            meta_acceptable, meta_rejected = metadata_prefilter(state.deduped_papers)
            if meta_rejected:
                meta_rejected_papers = [
                    p for p in state.deduped_papers if any(d.paper_id == p.paper_id for d in meta_rejected)
                ]
                await repository.bulk_save_screening_decisions(
                    workflow_id=state.workflow_id,
                    stage="title_abstract",
                    papers=meta_rejected_papers,
                    decisions=meta_rejected,
                )
                if rc and rc.verbose:
                    rc.console.print(
                        f"[dim]Metadata pre-filter: {len(meta_rejected)} papers rejected "
                        f"(missing title/abstract/year), {len(meta_acceptable)} forwarded.[/]"
                    )

            # --- Pre-screening: BM25 ranking (when cap is set) or keyword filter ---
            cap = state.settings.screening.max_llm_screen
            paper_by_id = {p.paper_id: p for p in meta_acceptable}

            if cap is not None:
                # BM25 ranks metadata-acceptable papers; top N go to LLM, tail is auto-excluded.
                # keyword_prefilter is NOT run as a hard gate - BM25 provides recall-safe ranking.
                papers_for_llm, pre_excluded = bm25_rank_and_cap(
                    meta_acceptable, state.review, state.settings.screening
                )
                if pre_excluded:
                    pre_excluded_papers = [paper_by_id[d.paper_id] for d in pre_excluded if d.paper_id in paper_by_id]
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
                    meta_acceptable, state.review, state.settings.screening
                )
                if pre_excluded:
                    pre_excluded_papers = [paper_by_id[d.paper_id] for d in pre_excluded if d.paper_id in paper_by_id]
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

            # --- Adaptive threshold calibration (optional) ---
            screening_cfg = state.settings.screening
            if (
                getattr(screening_cfg, "calibrate_threshold", True)
                and papers_for_llm
                and use_real_client
                and not state.parent_db_path  # skip for living-refresh delta runs
            ):
                from src.screening.reliability import calibrate_threshold as _calibrate_threshold

                _calib_sample_size = getattr(screening_cfg, "calibration_sample_size", 30)
                _calib_max_iter = getattr(screening_cfg, "calibration_max_iterations", 3)
                _calib_total = min(_calib_sample_size, len(papers_for_llm)) * _calib_max_iter

                # Emit start event so the UI shows calibration is running (not frozen).
                if rc:
                    rc.emit_phase_start(
                        "screening_calibration",
                        description=(
                            f"Calibrating screening thresholds ({_calib_sample_size} papers, "
                            f"up to {_calib_max_iter} iterations)..."
                        ),
                        total=_calib_total,
                    )

                _calib_completed: list[int] = [0]

                def _calib_on_progress(phase: object, current: object, total: object) -> None:
                    _calib_completed[0] += 1
                    if rc:
                        rc.advance_screening("screening_calibration", _calib_completed[0], _calib_total)

                async def _calibration_screener(
                    sample_papers: list[CandidatePaper],  # noqa: F821
                    threshold: float,
                ) -> list[DualScreeningResult]:  # noqa: F821
                    # Use screen_batch_for_calibration so both reviewers always run.
                    # This returns DualScreeningResult objects with reviewer_a and
                    # reviewer_b populated, which compute_cohens_kappa requires.
                    # Temporarily override threshold to reflect the bisection attempt.
                    original_include = getattr(screener.settings.screening, "stage1_include_threshold", 0.85)
                    try:
                        screener.settings.screening.stage1_include_threshold = threshold
                        screener.settings.screening.stage1_exclude_threshold = max(0.0, threshold - 0.05)
                        results = await screener.screen_batch_for_calibration(
                            workflow_id=f"{state.workflow_id}_calib",
                            papers=sample_papers,
                            on_progress=_calib_on_progress,
                        )
                        return list(results)
                    finally:
                        screener.settings.screening.stage1_include_threshold = original_include
                        screener.settings.screening.stage1_exclude_threshold = max(0.0, original_include - 0.05)

                try:
                    calibrated = await _calibrate_threshold(
                        papers=papers_for_llm,
                        screener_fn=_calibration_screener,
                        target_kappa=getattr(screening_cfg, "calibration_target_kappa", 0.7),
                        max_iterations=_calib_max_iter,
                        sample_size=_calib_sample_size,
                        initial_include_threshold=screening_cfg.stage1_include_threshold,
                    )
                    screening_cfg.stage1_include_threshold = calibrated.include_threshold
                    screening_cfg.stage1_exclude_threshold = calibrated.exclude_threshold
                    logger.info(
                        "Screening calibration: threshold adjusted to %.3f (kappa=%.4f, %d iter)",
                        calibrated.include_threshold,
                        calibrated.achieved_kappa,
                        calibrated.iterations,
                    )
                    if rc:
                        rc.emit_phase_done(
                            "screening_calibration",
                            summary={
                                "include_threshold": calibrated.include_threshold,
                                "exclude_threshold": calibrated.exclude_threshold,
                                "kappa": calibrated.achieved_kappa,
                                "iterations": calibrated.iterations,
                                "sample_size": calibrated.sample_size,
                            },
                        )
                        # Also emit legacy event for any consumers watching for it.
                        rc._emit(
                            {
                                "type": "screening_calibration",
                                "include_threshold": calibrated.include_threshold,
                                "exclude_threshold": calibrated.exclude_threshold,
                                "kappa": calibrated.achieved_kappa,
                                "iterations": calibrated.iterations,
                                "sample_size": calibrated.sample_size,
                            }
                        )
                except Exception as _cal_err:
                    logger.warning("Screening calibration failed (%s) -- using default thresholds", _cal_err)
                    if rc:
                        rc.emit_phase_done(
                            "screening_calibration",
                            summary={"error": str(_cal_err), "using_defaults": True},
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
            stage1_survivors = [p for p in meta_acceptable if p.paper_id in include_ids]

            # --- Reset interrupt flag so stage 2 always runs to completion ---
            screener.reset_partial_flag()

            # --- Stage 2: full-text screening (unified resolver: Unpaywall, S2, CORE, Europe PMC, ScienceDirect, PMC) ---
            stage2 = await screener.screen_batch(
                workflow_id=state.workflow_id,
                stage="fulltext",
                papers=stage1_survivors,
                full_text_by_paper=None,
                retriever=PDFRetriever(),
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
            if state.settings.gates.profile == "strict":
                gr = await repository.get_latest_gate_result(
                    state.workflow_id, "phase_3_screening", "screening_safeguard"
                )
                if gr and gr.status == GateStatus.FAILED:
                    err_msg = (
                        f"Screening safeguard gate failed: {gr.actual_value or 0} studies "
                        f"included (minimum {gr.threshold or '?'}). Cannot proceed."
                    )
                    summary = {
                        "workflow_id": state.workflow_id,
                        "status": "failed",
                        "error": err_msg,
                        "gate": "screening_safeguard",
                        "phase": "phase_3_screening",
                    }
                    Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
                    await repository.update_workflow_status(state.workflow_id, "failed")
                    await update_registry_status(state.run_root, state.workflow_id, "failed")
                    if rc:
                        rc.emit_phase_done("phase_3_screening", {"error": err_msg})
                    return End(summary)

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
            # -- Compute Cohen's kappa from dual-review pairs (where both reviewers ran) --
            if screener._dual_results:
                reliability = compute_cohens_kappa(screener._dual_results, stage="title_abstract")
                state.cohens_kappa = reliability.cohens_kappa
                state.kappa_stage = reliability.stage
                state.kappa_n = len(screener._dual_results)
                await log_reliability_to_decision_log(repository, reliability)

            # -- Forward citation chasing (PRISMA 2020 snowball supplement) --
            # Runs after inclusion decisions; found papers re-enter as screening candidates.
            _citation_chasing = state.settings.search.citation_chasing_enabled if state.settings else False
            if state.included_papers and _citation_chasing:
                try:
                    known_dois = {p.doi for p in state.deduped_papers if p.doi}
                    chaser = CitationChaser(workflow_id=state.workflow_id)
                    chased_results = await chaser.chase_citations_to_search_results(state.included_papers, known_dois)
                    if chased_results:
                        for sr in chased_results:
                            await repository.save_search_result(sr)
                        new_papers = [p for sr in chased_results for p in sr.papers]
                        if rc:
                            rc.emit_phase_start(
                                "citation_chasing",
                                f"Citation chasing: {len(new_papers)} candidates found.",
                                total=0,
                            )
                        state.deduped_papers = state.deduped_papers + new_papers
                except Exception as _cc_exc:
                    logger.warning("Citation chasing failed: %s", _cc_exc)

            checkpoint_status = "partial" if (rc and rc.should_proceed_with_partial()) else "completed"
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
        return HumanReviewCheckpointNode()


class HumanReviewCheckpointNode(BaseNode[ReviewState]):
    """Optional pause between screening and extraction for human review.

    When settings.human_in_the_loop.enabled is True, this node sets run
    status to 'awaiting_review', emits a SSE event, and polls until the
    /api/run/{run_id}/approve-screening endpoint is called.

    When disabled (default), this node is a no-op.
    """

    async def run(self, ctx: GraphRunContext[ReviewState]) -> ExtractionQualityNode:
        state = ctx.state
        rc = _rc(state)
        assert state.settings is not None

        hitl = state.settings.human_in_the_loop
        if not hitl.enabled:
            return ExtractionQualityNode()

        if rc:
            rc.emit_phase_start(
                "human_review_checkpoint",
                f"Awaiting human review of {len(state.included_papers)} screened papers. "
                "Approve via POST /api/run/{{run_id}}/approve-screening to continue.",
                total=0,
            )

        await update_registry_status(state.run_root, state.workflow_id, "awaiting_review")

        import asyncio as _asyncio

        poll_interval = 5
        max_wait = 7200
        waited = 0
        while waited < max_wait:
            await _asyncio.sleep(poll_interval)
            waited += poll_interval
            entry = await find_by_workflow_id(state.run_root, state.workflow_id)
            if entry and str(getattr(entry, "status", "awaiting_review")) == "running":
                break

        await update_registry_status(state.run_root, state.workflow_id, "running")
        if rc:
            rc.emit_phase_done("human_review_checkpoint", {"approved": True})

        return ExtractionQualityNode()


class ExtractionQualityNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> EmbeddingNode:
        state = ctx.state
        rc = _rc(state)
        assert state.review is not None
        assert state.settings is not None

        router = StudyRouter()
        grade = GradeAssessor()

        rob2_rows: list = []
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            # Always load from DB so records is complete even when resuming mid-phase
            # (state.extraction_records is empty if the phase checkpoint was never saved).
            records: list[ExtractionRecord] = await repository.load_extraction_records(state.workflow_id)
            already_extracted = {r.paper_id for r in records}
            already_assessed = await repository.get_rob_assessment_ids(state.workflow_id)
            to_process = [p for p in state.included_papers if p.paper_id not in already_extracted]
            # Papers that were extracted before a mid-phase crash but whose RoB
            # assessment was never saved.  Re-run quality assessment only (skip extraction).
            quality_only = [r for r in records if r.paper_id not in already_assessed]
            if rc:
                rc.emit_phase_start(
                    "phase_4_extraction_quality",
                    f"Extracting {len(to_process)} papers...",
                    total=len(to_process) + len(quality_only),
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
            _llm_timeout = float(getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 120))
            llm_gemini = PydanticAIClient(timeout_seconds=_llm_timeout) if use_llm else None
            extractor = ExtractionService(
                repository=repository,
                llm_client=llm_gemini,
                settings=state.settings,
                review=state.review,
                provider=provider if use_llm else None,
            )
            rob2 = Rob2Assessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            robins_i = RobinsIAssessor(
                llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None
            )
            casp = CaspAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            mmat = MmatAssessor(llm_client=llm_gemini, settings=state.settings, provider=provider if use_llm else None)
            not_applicable_paper_ids: list[str] = []

            # Quality-only pass: papers extracted before a crash but missing RoB.
            _paper_lookup = {p.paper_id: p for p in state.included_papers}
            for qr in quality_only:
                _src_paper = _paper_lookup.get(qr.paper_id)
                full_text = (_src_paper.abstract or _src_paper.title or "").strip() if _src_paper else ""
                try:
                    tool = router.route_tool(qr)
                    if tool == "rob2":
                        assessment = await rob2.assess(qr, full_text=full_text)
                        await repository.save_rob2_assessment(state.workflow_id, assessment)
                    elif tool == "robins_i":
                        assessment = await robins_i.assess(qr, full_text=full_text)
                        await repository.save_robins_i_assessment(state.workflow_id, assessment)
                    elif tool == "casp":
                        assessment = await casp.assess(qr, full_text=full_text)
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="casp_assessment",
                                paper_id=qr.paper_id,
                                decision="completed",
                                rationale=assessment.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    elif tool == "mmat":
                        mmat_result = await mmat.assess(qr, full_text=full_text)
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="mmat_assessment",
                                paper_id=qr.paper_id,
                                decision="completed",
                                rationale=mmat_result.overall_summary,
                                actor="quality_assessment",
                                phase="phase_4_extraction_quality",
                            )
                        )
                    else:
                        not_applicable_paper_ids.append(qr.paper_id)
                    _qr_outcomes = [
                        o.name.strip()
                        for o in qr.outcomes
                        if o.name.strip()
                        and o.name.strip().lower()
                        not in {
                            "primary_outcome",
                            "secondary_outcome",
                            "not_reported",
                            "",
                        }
                    ]
                    _qr_outcome_name = _qr_outcomes[0] if _qr_outcomes else "primary_outcome"
                    grade_assessment = grade.assess_outcome(
                        outcome_name=_qr_outcome_name,
                        number_of_studies=1,
                        study_design=qr.study_design,
                    )
                    await repository.save_grade_assessment(
                        state.workflow_id, grade_assessment
                    )  # quality-only retry; no fresh rob_assessment available
                except Exception as exc:
                    await repository.append_decision_log(
                        DecisionLogEntry(
                            decision_type="quality_retry_error",
                            paper_id=qr.paper_id,
                            decision="error",
                            rationale=f"Quality-only retry error: {type(exc).__name__}: {exc}",
                            actor="workflow_run",
                            phase="phase_4_extraction_quality",
                        )
                    )

            # Load extraction config for full-text retrieval and PDF vision
            extraction_cfg = getattr(state.settings, "extraction", None)

            for i, paper in enumerate(to_process):
                if rc and rc.verbose:
                    rc.console.print(f"  Extracting {paper.paper_id[:12]}... ({i + 1}/{len(to_process)})")

                # --- 3-tier full-text retrieval (replaces abstract-only) ---
                ft_result = None
                if use_llm and extraction_cfg is not None:
                    try:
                        from src.extraction.table_extraction import fetch_full_text

                        ft_result = await fetch_full_text(
                            doi=paper.doi,
                            url=paper.url,
                            pmid=getattr(paper, "pmid", None),
                            use_sciencedirect=getattr(extraction_cfg, "sciencedirect_full_text", True),
                            use_unpaywall=getattr(extraction_cfg, "unpaywall_full_text", True),
                            use_pmc=getattr(extraction_cfg, "pmc_full_text", True),
                            use_core=getattr(extraction_cfg, "core_full_text", True),
                            use_europepmc=getattr(extraction_cfg, "europepmc_full_text", True),
                            use_semanticscholar=getattr(extraction_cfg, "semanticscholar_full_text", True),
                            use_arxiv_pdf=getattr(extraction_cfg, "arxiv_full_text", True),
                            use_biorxiv_medrxiv=getattr(extraction_cfg, "biorxiv_medrxiv_full_text", True),
                            use_openalex_content=getattr(extraction_cfg, "openalex_content_full_text", False),
                            use_crossref_links=getattr(extraction_cfg, "crossref_links_full_text", True),
                        )
                    except Exception as _ft_err:
                        logger.warning(
                            "ExtractionNode: full-text fetch failed for %s (%s) -- using abstract",
                            paper.paper_id,
                            _ft_err,
                        )

                # Use fetched full text if substantial; fall back to abstract
                min_chars = getattr(extraction_cfg, "full_text_min_chars", 500)
                if ft_result and ft_result.text and len(ft_result.text) >= min_chars:
                    full_text = ft_result.text
                    if rc and rc.verbose:
                        rc.console.print(f"    [dim]full-text via {ft_result.source} ({len(full_text)} chars)[/]")
                elif ft_result and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                    # PDF-only (e.g. sciencedirect_pdf): parse to text for LLM extraction
                    try:
                        from src.search.pdf_retrieval import _parse_pdf_bytes

                        full_text = _parse_pdf_bytes(ft_result.pdf_bytes)
                        if rc and rc.verbose:
                            rc.console.print(
                                f"    [dim]full-text via {ft_result.source} PDF ({len(full_text)} chars)[/]"
                            )
                    except Exception:
                        full_text = (paper.abstract or paper.title or "").strip()
                else:
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

                    # --- PDF vision table extraction ---
                    # Guard: require at least 1 KB of PDF bytes to avoid "document has no pages"
                    # errors from the vision model when the retriever returns empty/corrupt bytes.
                    _pdf_bytes_ok = (
                        ft_result is not None and ft_result.pdf_bytes is not None and len(ft_result.pdf_bytes) >= 1024
                    )
                    use_vision = (
                        use_llm
                        and extraction_cfg is not None
                        and getattr(extraction_cfg, "use_pdf_vision", True)
                        and _pdf_bytes_ok
                    )
                    # Set extraction_source from the full-text retrieval tier
                    if ft_result and ft_result.source != "abstract":
                        try:
                            record.extraction_source = ft_result.source  # type: ignore[assignment]
                        except Exception:
                            pass  # model validation will reject unknown literals gracefully

                    if use_vision:
                        try:
                            from src.extraction.table_extraction import (
                                extract_tables_from_pdf,
                                merge_outcomes,
                            )

                            vision_model = getattr(
                                extraction_cfg, "pdf_vision_model", "gemini-3.1-flash-lite-preview"
                            ).replace("google-gla:", "")
                            vision_outcomes = await extract_tables_from_pdf(
                                ft_result.pdf_bytes,
                                model_name=vision_model,
                            )
                            if vision_outcomes:
                                merged, _merge_source = merge_outcomes(list(record.outcomes), vision_outcomes)
                                record.outcomes = merged
                                try:
                                    record.extraction_source = _merge_source  # type: ignore[assignment]
                                except Exception:
                                    pass
                                logger.info(
                                    "ExtractionNode: vision extracted %d table rows for paper %s (source=%s)",
                                    len(vision_outcomes),
                                    paper.paper_id,
                                    _merge_source,
                                )
                        except Exception as _vis_err:
                            logger.warning(
                                "ExtractionNode: PDF vision failed for %s: %s",
                                paper.paper_id,
                                _vis_err,
                            )

                    records.append(record)
                    if rc:
                        rc.advance_screening("phase_4_extraction_quality", i + 1, len(to_process))

                    tool = router.route_tool(record)
                    rob_judgment = "not_applicable"
                    rob_assessment_obj = None
                    if tool == "rob2":
                        assessment = await rob2.assess(record, full_text=full_text)
                        await repository.save_rob2_assessment(state.workflow_id, assessment)
                        rob_assessment_obj = assessment
                        rob_judgment = (
                            assessment.overall_judgment.value if hasattr(assessment, "overall_judgment") else "unknown"
                        )
                    elif tool == "robins_i":
                        assessment = await robins_i.assess(record, full_text=full_text)
                        await repository.save_robins_i_assessment(state.workflow_id, assessment)
                        rob_assessment_obj = assessment
                        rob_judgment = (
                            assessment.overall_judgment.value if hasattr(assessment, "overall_judgment") else "unknown"
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
                    elif tool == "mmat":
                        mmat_result = await mmat.assess(record, full_text=full_text)
                        rob_judgment = f"MMAT score {mmat_result.overall_score}/5"
                        await repository.append_decision_log(
                            DecisionLogEntry(
                                decision_type="mmat_assessment",
                                paper_id=record.paper_id,
                                decision="completed",
                                rationale=mmat_result.overall_summary,
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

                    # Use first named outcome from extraction record if available
                    _grade_outcomes = [
                        o.name.strip()
                        for o in record.outcomes
                        if o.name.strip()
                        and o.name.strip().lower()
                        not in {
                            "primary_outcome",
                            "secondary_outcome",
                            "not_reported",
                            "",
                        }
                    ]
                    _grade_outcome_name = _grade_outcomes[0] if _grade_outcomes else "primary_outcome"

                    if rob_assessment_obj is not None:
                        grade_assessment = grade.assess_from_rob(
                            outcome_name=_grade_outcome_name,
                            study_design=record.study_design,
                            rob_assessments=[rob_assessment_obj],
                            extraction_records=[record],
                        )
                    else:
                        grade_assessment = grade.assess_outcome(
                            outcome_name=_grade_outcome_name,
                            number_of_studies=1,
                            study_design=record.study_design,
                        )
                    await repository.save_grade_assessment(state.workflow_id, grade_assessment)

                    if rc and rc.verbose:
                        extraction_summary = (record.results_summary.get("summary") or "")[:300]
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
            # Count heuristic-derived assessments for Methods section transparency.
            _heuristic_count = sum(
                1 for r in (rob2_rows + robins_i_rows)
                if getattr(r, "assessment_source", "llm") == "heuristic"
            )
            state.heuristic_assessment_count = _heuristic_count
            if _heuristic_count > 0:
                logger.warning(
                    "ExtractionQualityNode: %d quality assessment(s) used heuristic fallback",
                    _heuristic_count,
                )
            completeness_ratio = (
                1.0
                if not records
                else (
                    sum(1 for record in records if (record.results_summary.get("summary") or "").strip() != "")
                    / len(records)
                )
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
        return EmbeddingNode()


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
        for outcome in record.outcomes or []:
            name = outcome.name.lower().replace(" ", "_")
            if outcome_name not in name:
                continue
            effect_str = outcome.effect_size or ""
            se_str = outcome.se or ""
            var_str = outcome.variance or ""
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
                    variance_val = se_val**2
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
    async def run(self, ctx: GraphRunContext[ReviewState]) -> KnowledgeGraphNode:
        state = ctx.state
        rc = _rc(state)
        assert state.settings is not None
        if rc:
            rc.emit_phase_start("phase_5_synthesis", "Building synthesis...", total=1)
        feasibility = assess_meta_analysis_feasibility(state.extraction_records)
        _use_llm = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
        _synth_timeout = float(getattr(getattr(state.settings, "llm", None), "request_timeout_seconds", 120))
        _synth_llm = PydanticAIClient(timeout_seconds=_synth_timeout) if _use_llm else None
        narrative = await build_narrative_synthesis(
            "primary_outcome",
            state.extraction_records,
            llm_client=_synth_llm,
            settings=state.settings,
        )

        # Attempt quantitative meta-analysis for each feasible outcome group
        meta_result = None
        rendered_forest = None
        rendered_funnel = None
        sensitivity_texts: list[str] = []
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
                    # Run sensitivity analysis for this pooled outcome
                    sens = run_sensitivity_analysis(
                        records=state.extraction_records,
                        outcome_name=group,
                        effect_measure=effect_measure,
                        subgroup_cols=["study_design"],
                        heterogeneity_threshold=het_threshold,
                    )
                    if sens is not None:
                        sensitivity_texts.append(sens.to_grounding_text())
                    break

        state.sensitivity_results = sensitivity_texts

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
                rc.console.print("  Meta-analysis: insufficient numeric effect data; using narrative synthesis.")

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
                state.workflow_id,
                "phase_5_synthesis",
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
        return KnowledgeGraphNode()


def _reconcile_manuscript_consistency(body: str, state: ReviewState) -> str:  # type: ignore[name-defined]
    """Detect and repair cross-section contradictions in the assembled manuscript body.

    Sections are written independently by the LLM, which can produce factual
    inconsistencies such as:
    - Claiming meta-analysis was performed (in abstract/methods) when the
      feasibility check declared it infeasible (narrated in discussion/limitations)
    - Claiming the protocol was prospectively registered when it was not

    This function applies targeted string corrections that preserve all other text
    while making the inter-section claims consistent with the grounding data.
    It is intentionally conservative: only replace well-known contradiction patterns.
    """
    import json
    import re

    # Determine ground-truth flags from the narrative synthesis JSON artifact on disk
    meta_feasible: bool = False
    meta_ran: bool = False  # True only when pooling produced a usable result
    narrative_path = state.artifacts.get("narrative_synthesis", "")
    if narrative_path:
        try:
            with open(narrative_path, encoding="utf-8") as _nf:
                _narrative_data = json.load(_nf)
            feasibility = _narrative_data.get("feasibility", {})
            raw_feasible = bool(feasibility.get("feasible", False))
            groupings = feasibility.get("groupings", [])
            _generic = frozenset({"primary_outcome", "secondary_outcome"})
            generic_only = not groupings or all(g in _generic for g in groupings)
            meta_feasible = raw_feasible and not generic_only
            # meta_analysis key only present when pooling actually produced results
            meta_ran = bool(_narrative_data.get("meta_analysis"))
        except Exception:
            pass

    # Apply meta-analysis contradiction fixes when:
    # (a) feasibility check failed, OR
    # (b) feasibility check passed but actual float-parsing/pooling failed (meta_ran=False)
    # In both cases the manuscript MUST describe narrative synthesis only.
    should_fix_meta = not meta_feasible or (meta_feasible and not meta_ran)

    # -----------------------------------------------------------------------
    # Fix 1: meta-analysis contradictions
    # When pooling was not performed, replace phrases that claim it was.
    # -----------------------------------------------------------------------
    if should_fix_meta:
        # Patterns that assert a meta-analysis was conducted
        _META_ASSERTIONS = [
            (
                r"determined that a meta-analysis was feasible",
                "conducted a narrative synthesis; a meta-analysis was not feasible",
            ),
            (
                r"the data were deemed suitable for meta-analysis",
                "a meta-analysis was not feasible due to heterogeneity in outcomes; a narrative synthesis was conducted",
            ),
            (
                r"we conducted a meta-analysis\b",
                "we conducted a narrative synthesis (meta-analysis was not feasible)",
            ),
            (
                r"We conducted a meta-analysis\b",
                "We conducted a narrative synthesis (meta-analysis was not feasible)",
            ),
            (
                r"A meta-analysis was initially considered but was precluded",
                "A meta-analysis was not feasible",
            ),
        ]
        for pattern, replacement in _META_ASSERTIONS:
            body = re.sub(pattern, replacement, body)

    # -----------------------------------------------------------------------
    # Fix 2: protocol registration contradictions
    # Always use "not prospectively registered" unless we have an ID (not yet
    # implemented -- protocol_registered is always False in grounding data).
    # -----------------------------------------------------------------------
    _PROTO_REGISTERED_RE = re.compile(
        r"The\s+(?:review\s+)?protocol\s+was\s+(?:prospectively\s+)?registered\s+prospectively",
        re.IGNORECASE,
    )
    body = _PROTO_REGISTERED_RE.sub(
        "The protocol was not prospectively registered",
        body,
    )

    return body


def _build_minimal_sections_for_zero_papers(
    research_question: str,
    minimal_paragraph: str,
    sections: list[str],
) -> list[str]:
    """Build minimal section content when no studies were included.

    Avoids LLM calls; produces factual, non-hallucinated manuscript.
    """
    rq = research_question or "the research question"
    result: list[str] = []
    for s in sections:
        if s == "abstract":
            content = (
                f"**Objectives:** This systematic review addressed {rq}. "
                "**Methods:** Bibliographic databases were searched per protocol. "
                "**Results:** The search identified records as reported; 0 studies "
                "met the eligibility criteria. **Conclusion:** No synthesis was "
                "performed. **Keywords:** systematic review, empty result."
            )
        elif s == "introduction":
            content = (
                f"This systematic review aimed to address {rq}. "
                "No studies met the eligibility criteria after screening."
            )
        elif s == "methods":
            content = (
                "Searches were conducted in bibliographic databases per the "
                "registered protocol. Eligibility criteria were applied by "
                "independent reviewers. No studies were included."
            )
        elif s == "results":
            content = minimal_paragraph
        elif s == "discussion":
            content = (
                "With no studies meeting eligibility criteria, no synthesis or "
                "findings can be reported. This may reflect a narrow search scope, "
                "restrictive eligibility criteria, or a genuine evidence gap."
            )
        elif s == "conclusion":
            content = "No conclusions can be drawn from this review. No studies met the eligibility criteria."
        else:
            content = minimal_paragraph
        result.append(content)
    return result


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

        style_patterns, citation_catalog = prepare_writing_context(state.included_papers, narrative, state.settings)

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
                rc.console.print(f"  PRISMA: {prisma_counts} -> {Path(state.artifacts['prisma_diagram']).name}")
                rc.console.print(f"  Timeline: {Path(state.artifacts['timeline']).name}")
                rc.console.print(f"  Geographic: {Path(state.artifacts['geographic']).name}")

            citation_repo = CitationRepository(db)
            completed = await repository.get_completed_sections(state.workflow_id)
            provider = LLMProvider(state.settings, repository)

            await register_citations_from_papers(citation_repo, state.included_papers)

            if len(state.included_papers) == 0:
                # Zero-papers guard: produce minimal manuscript without LLM calls
                total_id = prisma_counts.total_identified_databases + prisma_counts.total_identified_other
                dbs = list(prisma_counts.databases_records.keys()) or ["searched databases"]
                db_str = ", ".join(dbs) if dbs else "the specified databases"
                minimal_para = (
                    f"The search identified {total_id} records from {db_str}. "
                    "After screening, 0 studies met the eligibility criteria. "
                    "No synthesis or findings are reported."
                )
                rq = state.review.research_question or "the research question"
                _minimal_contents = _build_minimal_sections_for_zero_papers(rq, minimal_para, SECTIONS)
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
                    await repository.save_section_draft(draft)
                    sections_written.append(content)
                    if rc:
                        rc.advance_screening("phase_6_writing", i + 1, len(SECTIONS))
                await repository.save_checkpoint(state.workflow_id, "phase_6_writing", papers_processed=len(SECTIONS))
                logger.info("WritingNode: 0 included papers; produced minimal manuscript without LLM calls")
            else:
                # Build grounding data from real pipeline outputs so the writing LLM
                # cannot hallucinate counts, statistics, or citation keys.
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
                )

                def _on_write(**kw):
                    if rc:
                        rc.log_api_call(**kw)

                # Pre-generate HyDE hypothetical documents for all sections in
                # parallel before the writing loop. Abstract always returns "".
                rag_cfg = getattr(state.settings, "rag", None)
                use_hyde = getattr(rag_cfg, "use_hyde", True)
                hyde_model = getattr(rag_cfg, "hyde_model", "google-gla:gemini-3.1-flash-lite-preview")
                embed_model = getattr(rag_cfg, "embed_model", "google-gla:gemini-embedding-001")
                embed_dim = getattr(rag_cfg, "embed_dim", 768)

                _pico_cfg = getattr(state.review, "pico", None) if state.review else None

                hyde_docs: dict[str, str] = {}
                if use_hyde and state.review:
                    try:
                        import asyncio as _asyncio

                        _hyde_results = await _asyncio.gather(
                            *[
                                generate_hyde_document(
                                    section=s,
                                    research_question=state.review.research_question,
                                    model=hyde_model,
                                    pico=_pico_cfg,
                                    repository=repository,
                                )
                                for s in SECTIONS
                            ],
                            return_exceptions=True,
                        )
                        for s, res in zip(SECTIONS, _hyde_results):
                            if isinstance(res, str) and res:
                                hyde_docs[s] = res
                        logger.info(
                            "HyDE pre-generated %d/%d section docs (PICO=%s)",
                            len(hyde_docs),
                            len(SECTIONS),
                            _pico_cfg is not None,
                        )
                    except Exception as _hyde_err:
                        logger.warning("HyDE batch failed: %s -- falling back to bare embed_query", _hyde_err)

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

                    # Retrieve semantically relevant evidence chunks for this section
                    # using hybrid BM25 + dense retrieval with Reciprocal Rank Fusion,
                    # followed by optional cross-encoder reranking.
                    rag_context = ""
                    try:
                        retriever = RAGRetriever(db, state.workflow_id)
                        chunk_count = await retriever.chunk_count()
                        if chunk_count > 0:
                            # HyDE: embed the hypothetical doc if available, else
                            # fall back to bare section name. BM25 always uses the
                            # factual query (not hypothetical) to avoid hallucinated
                            # corpus-drift.
                            hyde_text = hyde_docs.get(section, "")
                            query_vec = await rag_embed_query(
                                hyde_text if hyde_text else section,
                                model=embed_model,
                                dim=embed_dim,
                            )
                            if hyde_text:
                                logger.debug("RAG: HyDE embedding used for section '%s'", section)
                            # PICO enrichment: appending PICO terms gives BM25
                            # domain-specific keywords beyond the bare section name.
                            _pico_terms = (
                                " ".join(
                                    filter(
                                        None,
                                        [
                                            getattr(_pico_cfg, "population", "") or "",
                                            getattr(_pico_cfg, "intervention", "") or "",
                                            getattr(_pico_cfg, "comparison", "") or "",
                                            getattr(_pico_cfg, "outcome", "") or "",
                                        ],
                                    )
                                ).strip()
                                if _pico_cfg
                                else ""
                            )
                            bm25_query = " ".join(
                                filter(
                                    None,
                                    [
                                        state.review.research_question,
                                        _pico_terms,
                                        section,
                                    ],
                                )
                            )

                            # Retrieve wider candidate set (top_k=20) for reranker;
                            # fall back to top_k=8 when reranking is disabled.
                            use_rerank = getattr(rag_cfg, "rerank", True)
                            candidate_k = 20 if use_rerank else 8
                            chunks = await retriever.search(query_vec, top_k=candidate_k, query_text=bm25_query)

                            # Listwise reranking: single Gemini Flash call orders
                            # all candidates by relevance, keeping the best 8.
                            if use_rerank and chunks:
                                reranker_model = getattr(
                                    rag_cfg,
                                    "reranker_model",
                                    "google-gla:gemini-3.1-flash-lite-preview",
                                )
                                rerank_query = hyde_text if hyde_text else bm25_query
                                chunks = await rerank_chunks(
                                    rerank_query,
                                    chunks,
                                    top_k=8,
                                    model=reranker_model,
                                    repository=repository,
                                )

                            if chunks:
                                rag_context = "\n\n".join(
                                    f"[Paper {c.paper_id} | score {c.score:.4f}]\n{c.content}" for c in chunks
                                )
                    except Exception as _rag_exc:
                        logger.warning("RAG retrieval failed for section '%s': %s", section, _rag_exc)

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
                        rag_context=rag_context,
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
                            rc.console.print(f"    Humanizing {section} ({humanize_iters} pass(es))...")
                        for _ in range(humanize_iters):
                            content = await humanize_async(
                                content,
                                model=h_model,
                                temperature=h_temp,
                                max_chars=12000,
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

                await repository.save_checkpoint(state.workflow_id, "phase_6_writing", papers_processed=len(SECTIONS))

            citation_rows = await CitationRepository(db).get_all_citations_for_export()
            # Load papers + extraction records for the study characteristics table.
            # Derive included_ids from extraction_records first (not from fulltext
            # screening decisions which may not exist when title_abstract screening
            # is the only stage used).  This mirrors finalize_manuscript.py exactly.
            all_extraction_records = await repository.load_extraction_records(state.workflow_id)
            # Apply post-extraction quality gate: only pass records with real extracted data.
            extraction_records_for_table = [r for r in all_extraction_records if not is_extraction_failed(r)]
            _failed_extraction_count = len(all_extraction_records) - len(extraction_records_for_table)
            included_ids = {r.paper_id for r in extraction_records_for_table}
            if not included_ids:
                included_ids = await repository.get_included_paper_ids(state.workflow_id)
            included_papers_for_table = await repository.load_papers_by_ids(included_ids)

        # Prefix each section with its standard IMRaD heading.
        # The abstract is kept as-is (it already contains the title + structured fields).
        _SECTION_HEADINGS: dict[str, str] = {
            "abstract": "",
            "introduction": "## Introduction",
            "methods": "## Methods",
            "results": "## Results",
            "discussion": "## Discussion",
            "conclusion": "## Conclusion",
        }
        # Patterns that match LLM-generated section-level heading variants we
        # must strip before prepending the canonical ## heading.
        # Covers: "## Results", "### Results", "### **Results**", etc.
        _section_heading_strip_re = re.compile(
            r"^#{2,3}\s+\*{0,2}(Introduction|Methods|Results|Discussion|Conclusion)\*{0,2}\s*\n+",
            re.IGNORECASE,
        )

        titled_sections = []
        for section, content in zip(SECTIONS, sections_written):
            heading = _SECTION_HEADINGS.get(section, "")
            if heading:
                # Strip any duplicate or variant section heading the LLM may have
                # written at the top (e.g. "## Discussion", "### **Results**").
                stripped = content.lstrip()
                # Exact match strip (fast path)
                if stripped.startswith(heading):
                    content = stripped[len(heading) :].lstrip("\n")
                else:
                    # Broad strip: remove any ## or ### section-level heading variant
                    content = _section_heading_strip_re.sub("", stripped)
            titled_sections.append(f"{heading}\n\n{content}" if heading else content)

        manuscript_path = Path(state.artifacts["manuscript_md"])
        body = "\n\n".join(titled_sections)

        # --- Contradiction detection pass (Idea 3) ---
        # Detect directional disagreements between included studies and inject
        # a disagreement paragraph into the Discussion section.
        if state.extraction_records and len(state.extraction_records) >= 2:
            try:
                # Load mean chunk embeddings for cosine similarity (if available)
                _chunk_embeddings: dict[str, list[float]] = {}
                import json as _json

                async with get_db(state.db_path) as _emb_db:
                    async with _emb_db.execute(
                        "SELECT paper_id, embedding FROM paper_chunks_meta "
                        "WHERE workflow_id = ? AND embedding IS NOT NULL",
                        (state.workflow_id,),
                    ) as _emb_cursor:
                        _paper_vecs: dict[str, list[list[float]]] = {}
                        async for _emb_row in _emb_cursor:
                            try:
                                _vec = _json.loads(_emb_row[1])
                                _paper_vecs.setdefault(_emb_row[0], []).append(_vec)
                            except Exception:
                                continue
                    for _pid, _vecs in _paper_vecs.items():
                        if _vecs:
                            _dim = len(_vecs[0])
                            _chunk_embeddings[_pid] = [sum(v[i] for v in _vecs) / len(_vecs) for i in range(_dim)]

                flags = detect_contradictions(
                    state.extraction_records,
                    chunk_embeddings=_chunk_embeddings if _chunk_embeddings else None,
                )
                state.contradiction_flags = flags

                if flags:
                    _use_llm_contra = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
                    api_key = os.getenv("GEMINI_API_KEY", "")
                    _contra_model = (
                        state.settings.agents["writing"].model
                        if state.settings and "writing" in state.settings.agents
                        else "google-gla:gemini-2.5-pro"
                    )
                    contra_paragraph = await generate_contradiction_paragraph(
                        flags,
                        model_name=_contra_model,
                        api_key=api_key if _use_llm_contra else None,
                    )
                    if contra_paragraph and "## Discussion" in body:
                        # Inject after the first paragraph of the Discussion section
                        _disc_marker = "## Discussion"
                        _disc_idx = body.index(_disc_marker) + len(_disc_marker)
                        _after_disc = body[_disc_idx:]
                        _first_para_end = _after_disc.find("\n\n")
                        if _first_para_end > 0:
                            _inject_point = _disc_idx + _first_para_end
                            body = body[:_inject_point] + "\n\n" + contra_paragraph + body[_inject_point:]

                    # Append structured "### Conflicting Evidence" subsection before
                    # the Conclusion so reviewers can see the flag pairs explicitly.
                    _conflict_section = build_conflicting_evidence_section(flags)
                    if _conflict_section:
                        # Insert before ## Conclusion (or append to body if absent)
                        if "## Conclusion" in body:
                            body = body.replace(
                                "## Conclusion",
                                _conflict_section + "\n\n## Conclusion",
                                1,
                            )
                        else:
                            body = body.rstrip() + "\n\n" + _conflict_section + "\n"
            except Exception as _contra_exc:
                logger.warning("Contradiction detection failed (non-fatal): %s", _contra_exc)

        # --- Citation grounding verification (Idea 1) ---
        # Verify all citekeys in the assembled manuscript are legitimate.
        if citation_catalog:
            _valid_citekeys = [
                line.strip()[1 : line.strip().index("]")]
                for line in citation_catalog.splitlines()
                if line.strip().startswith("[") and "]" in line.strip()
            ]
            if _valid_citekeys:
                _verified, _hallucinated = verify_citation_grounding(body, _valid_citekeys, "full_manuscript")
                if _hallucinated:
                    body = repair_hallucinated_citekeys(body, _hallucinated, _valid_citekeys)
                    logger.warning(
                        "Citation grounding: repaired %d hallucinated citekeys: %s",
                        len(_hallucinated),
                        _hallucinated[:5],
                    )

        # Cross-section consistency pass: detect and repair contradictions that arise
        # when sections are written independently by the LLM.
        body = _reconcile_manuscript_consistency(body, state)
        async with get_db(state.db_path) as _grade_db:
            _grade_repo = WorkflowRepository(_grade_db)
            _grade_assessments = await _grade_repo.load_grade_assessments(state.workflow_id)
            _rob2_rows, _robins_i_rows = await _grade_repo.load_rob_assessments(state.workflow_id)

        _search_appendix_path = (
            Path(state.artifacts["search_appendix"]) if "search_appendix" in state.artifacts else None
        )
        full_manuscript = assemble_submission_manuscript(
            body=body,
            manuscript_path=manuscript_path,
            artifacts=state.artifacts,
            citation_rows=citation_rows,
            papers=included_papers_for_table,
            extraction_records=extraction_records_for_table,
            grade_assessments=_grade_assessments if _grade_assessments else None,
            robins_i_assessments=_robins_i_rows if _robins_i_rows else None,
            review_config=state.review,
            failed_count=_failed_extraction_count,
            search_appendix_path=_search_appendix_path,
            research_question=state.review.research_question if state.review else "",
            title=None,
        )
        manuscript_path.write_text(full_manuscript, encoding="utf-8")

        # Emit phase done and advance to FinalizeNode NOW, before concept diagrams.
        # Concept diagrams are bonus artifacts -- a CancelledError, timeout, or any
        # other failure must never prevent FinalizeNode from running.
        if rc:
            rc.emit_phase_done("phase_6_writing", {"sections": len(sections_written)})

        # --- Concept diagrams (LLM -> Graphviz/Kroki -> SVG) ---
        # Best-effort: runs after the phase is marked done so failures here are
        # non-fatal.  The entire block -- including spec construction and the
        # async render call -- is inside one try/except so that KeyErrors on
        # missing artifact keys, Pydantic ValidationErrors on None PICO fields,
        # LLM 503s, timeouts, and CancelledErrors all fall through gracefully to
        # FinalizeNode without failing the run.
        try:
            _out_dir = Path(state.artifacts["concept_taxonomy"]).parent
            _review = state.review
            _pico = _review.pico if _review else None
            _n_included = len(state.included_papers)
            _topic = _review.research_question if _review else "Systematic Review"

            _taxonomy_spec: TaxonomyDiagramInput | None = None
            if state.extraction_records and _pico:
                from collections import Counter as _Counter

                _design_counter = _Counter(
                    r.study_design.value if r.study_design else "Other" for r in state.extraction_records
                )
                if len(_design_counter) >= 2:
                    _categories = [
                        TaxonomyCategory(label=design, items=[f"n={count} studies"])
                        for design, count in _design_counter.most_common()
                    ]
                    _taxonomy_spec = TaxonomyDiagramInput(
                        title=f"Study Design Taxonomy ({_n_included} studies)",
                        root_label="Included Studies",
                        categories=_categories,
                        review_topic=_topic,
                    )

            _framework_spec: FrameworkDiagramInput | None = None
            if _pico and _n_included >= 1:
                _narr_themes: list[str] = []
                if narrative and "narrative" in narrative:
                    _narr_data = narrative["narrative"]
                    if isinstance(_narr_data, dict):
                        _narr_themes = _narr_data.get("key_themes", [])
                    elif isinstance(_narr_data, list):
                        for _n in _narr_data:
                            if isinstance(_n, dict):
                                _narr_themes.extend(_n.get("key_themes", []))
                _framework_spec = FrameworkDiagramInput(
                    title="Conceptual Framework",
                    population=_pico.population,
                    interventions=[_pico.intervention],
                    outcomes=[_pico.outcome],
                    comparator=_pico.comparison if _pico.comparison else None,
                    key_themes=list(dict.fromkeys(_narr_themes))[:6],
                    study_count=_n_included,
                    review_topic=_topic,
                )

            _flowchart_spec: FlowchartDiagramInput | None = None
            if prisma_counts:
                _phases = [
                    FlowchartPhase(
                        label="Database Search",
                        count=prisma_counts.total_identified_databases,
                    ),
                    FlowchartPhase(
                        label="After Deduplication",
                        count=prisma_counts.records_screened + prisma_counts.records_excluded_screening,
                    ),
                    FlowchartPhase(
                        label="Title/Abstract Screening",
                        count=prisma_counts.records_screened,
                        sublabel=f"{prisma_counts.records_excluded_screening} excluded",
                    ),
                    FlowchartPhase(
                        label="Eligible for Inclusion",
                        count=prisma_counts.reports_sought,
                    ),
                    FlowchartPhase(
                        label="Included in Review",
                        count=prisma_counts.studies_included_qualitative + prisma_counts.studies_included_quantitative,
                    ),
                ]
                _flowchart_spec = FlowchartDiagramInput(
                    title="Systematic Review Methodology",
                    phases=_phases,
                    review_topic=_topic,
                )

            _concept_model = (
                state.settings.agents.get("abstract_generation", state.settings.agents.get("writing")).model
                if state.settings and state.settings.agents
                else "google-gla:gemini-2.5-flash"
            )
            _concept_results = await asyncio.wait_for(
                render_concept_diagrams(
                    taxonomy_spec=_taxonomy_spec,
                    framework_spec=_framework_spec,
                    flowchart_spec=_flowchart_spec,
                    out_dir=_out_dir,
                    model=_concept_model,
                ),
                timeout=180.0,
            )
            if rc and rc.verbose:
                for _key, _path in _concept_results.items():
                    if _path:
                        rc.console.print(f"  Concept diagram ({_key}): {_path.name}")
        except TimeoutError:
            logger.warning("Concept diagram generation timed out after 180s -- skipping")
        except asyncio.CancelledError:
            logger.warning("Concept diagram generation cancelled -- skipping")
        except Exception as _cd_exc:  # noqa: BLE001
            logger.warning("Concept diagram generation failed: %s", _cd_exc)

        return FinalizeNode()


class FinalizeNode(BaseNode[ReviewState]):
    async def run(
        self, ctx: GraphRunContext[ReviewState]
    ) -> End[dict[str, str | int | dict[str, int] | dict[str, str]]]:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("finalize", "Writing run summary...")
        # Filter artifact paths: only include entries that either are the run_summary
        # itself (written below) or point to a file that actually exists on disk.
        # This prevents broken image links in the UI when optional figures (e.g.
        # forest/funnel plot) were not generated because meta-analysis was infeasible.
        run_summary_key = "run_summary"
        filtered_artifacts = {k: v for k, v in state.artifacts.items() if k == run_summary_key or os.path.isfile(v)}
        summary: dict[str, str | int | dict[str, int] | dict[str, str]] = {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "log_dir": state.log_dir,
            "output_dir": state.output_dir,
            "search_counts": state.search_counts,
            "search_queries": state.search_queries,
            "dedup_count": state.dedup_count,
            "connector_init_failures": state.connector_init_failures,
            "included_papers": len(state.included_papers),
            "extraction_records": len(state.extraction_records),
            "artifacts": filtered_artifacts,
        }
        # --- Citation lineage validation gate ---
        # Check the final manuscript for unresolved citekeys. Respects the
        # citation_lineage.block_export_on_unresolved setting: when True, a warning
        # is logged and the summary records the issue so the export endpoint can
        # surface it. The run itself always completes -- the gate is advisory here.
        _manuscript_path = state.artifacts.get("manuscript_md", "")
        if _manuscript_path and os.path.isfile(_manuscript_path):
            try:
                _manuscript_text = Path(_manuscript_path).read_text(encoding="utf-8")
                async with get_db(state.db_path) as _cit_db:
                    _ledger = CitationLedger(CitationRepository(_cit_db))
                    _block_on_unresolved = (
                        state.settings.citation_lineage.block_export_on_unresolved if state.settings else True
                    )
                    _should_block = await _ledger.block_export_if_invalid(
                        _manuscript_text,
                        block_on_unresolved=_block_on_unresolved,
                    )
                    if _should_block:
                        _log.warning(
                            "Citation lineage gate: unresolved citations or claims detected "
                            "in final manuscript. Export may be blocked. "
                            "Check citation_lineage.block_export_on_unresolved in settings.yaml "
                            "to suppress this warning."
                        )
                        summary["citation_lineage_valid"] = False
                    else:
                        summary["citation_lineage_valid"] = True
            except Exception as _cit_err:
                _log.warning("Citation lineage check skipped: %s", _cit_err)

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
        HumanReviewCheckpointNode,
        ExtractionQualityNode,
        EmbeddingNode,
        SynthesisNode,
        KnowledgeGraphNode,
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
            pass  # Windows: add_signal_handler not available

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
