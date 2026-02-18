"""Single-path workflow orchestration for `run`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.table import Table

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import (
    find_by_topic,
    find_by_workflow_id,
    find_by_workflow_id_fallback,
    register as register_workflow,
    update_status as update_registry_status,
)
from src.extraction import ExtractionService, StudyClassifier
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, DecisionLogEntry, ExtractionRecord, ReviewConfig, SettingsConfig, StudyDesign
from src.orchestration.gates import GateRunner
from src.protocol.generator import ProtocolGenerator
from src.quality import CaspAssessor, GradeAssessor, Rob2Assessor, RobinsIAssessor, StudyRouter
from src.screening.dual_screener import DualReviewerScreener
from src.screening.gemini_client import GeminiScreeningClient
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
from src.db.repositories import CitationRepository
from src.models import SectionDraft
from src.orchestration.context import RunContext
from src.orchestration.resume import load_resume_state
from src.orchestration.state import ReviewState
from src.utils.logging_paths import OutputRunPaths, create_output_paths, create_run_paths
from src.utils import structured_log
from src.prisma import build_prisma_counts, render_prisma_diagram
from src.visualization import render_geographic, render_rob_traffic_light, render_timeline


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _hash_config(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


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

        log_paths = create_run_paths(log_root=state.log_root, workflow_description=review.research_question)
        output_paths: OutputRunPaths = create_output_paths(
            output_root=state.output_root,
            workflow_description=review.research_question,
            run_dir_name=log_paths.run_dir.name,
            date_folder=log_paths.run_dir.parent.parent.name,
        )
        state.log_dir = str(log_paths.run_dir)
        state.output_dir = str(output_paths.run_dir)
        state.db_path = str(log_paths.runtime_db)
        structured_log.configure_run_logging(state.log_dir)
        structured_log.bind_run(state.workflow_id, state.run_id)
        state.artifacts["run_summary"] = str(log_paths.run_summary)
        state.artifacts["search_appendix"] = str(output_paths.search_appendix)
        state.artifacts["protocol"] = str(output_paths.protocol_markdown)
        state.artifacts["coverage_report"] = str(output_paths.run_dir / "doc_fulltext_retrieval_coverage.md")
        state.artifacts["disagreements_report"] = str(output_paths.run_dir / "doc_disagreements_report.md")
        state.artifacts["rob_traffic_light"] = str(output_paths.run_dir / "fig_rob_traffic_light.png")
        state.artifacts["narrative_synthesis"] = str(output_paths.run_dir / "data_narrative_synthesis.json")
        state.artifacts["manuscript_md"] = str(output_paths.run_dir / "doc_manuscript.md")
        state.artifacts["prisma_diagram"] = str(output_paths.run_dir / "fig_prisma_flow.png")
        state.artifacts["timeline"] = str(output_paths.run_dir / "fig_publication_timeline.png")
        state.artifacts["geographic"] = str(output_paths.run_dir / "fig_geographic_distribution.png")
        if rc:
            rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
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
                log_root=state.log_root,
                workflow_id=state.workflow_id,
                topic=state.review.research_question,
                config_hash=config_hash,
                db_path=state.db_path,
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
            results, dedup_count = await coordinator.run(max_results=100)
            all_papers = [paper for result in results for paper in result.papers]
            deduped, _ = deduplicate_papers(all_papers)
            state.deduped_papers = deduped
            state.dedup_count = dedup_count
            state.search_counts = await repository.get_search_counts(state.workflow_id)

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
                on_waiting = lambda t, u, l: rc.log_rate_limit_wait(t, u, l)
            provider = LLMProvider(state.settings, repository, on_waiting=on_waiting)
            on_llm_call = None
            if rc and rc.verbose:
                on_llm_call = lambda s, st, d, r, **kw: rc.log_api_call(
                    s, st, d, r, call_type="llm_screening", **kw
                )
            use_real_client = (
                os.getenv("GEMINI_API_KEY")
                and (rc is None or not rc.offline)
            )
            llm_client = GeminiScreeningClient() if use_real_client else None
            on_progress = None
            if rc:
                on_progress = lambda p, c, t: rc.advance_screening(p, c, t)
            on_prompt = None
            if rc and rc.debug:
                on_prompt = lambda a, p, pid: rc.log_prompt(a, p, pid)
            should_proceed = (
                (lambda: rc.should_proceed_with_partial())
                if rc and hasattr(rc, "should_proceed_with_partial")
                else None
            )
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
            )
            stage1 = await screener.screen_batch(
                workflow_id=state.workflow_id,
                stage="title_abstract",
                papers=state.deduped_papers,
            )
            include_ids = {decision.paper_id for decision in stage1 if decision.decision.value == "include"}
            stage1_survivors = [paper for paper in state.deduped_papers if paper.paper_id in include_ids]
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
            include_ids = {decision.paper_id for decision in stage2 if decision.decision.value == "include"}
            state.included_papers = [paper for paper in stage1_survivors if paper.paper_id in include_ids]
            await gate_runner.run_screening_safeguard_gate(
                workflow_id=state.workflow_id,
                phase="phase_3_screening",
                passed_screening=len(state.included_papers),
            )
            await repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="screening_summary",
                    decision="completed",
                    rationale=(
                        f"title_abstract_total={len(stage1)}, fulltext_total={len(stage2)}, "
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
        rob2 = Rob2Assessor()
        robins_i = RobinsIAssessor()
        casp = CaspAssessor()
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
                    rc.log_api_call(call_type="llm_classification", **kw)
                on_classify = _on_classify
            classifier = StudyClassifier(
                provider=provider,
                repository=repository,
                review=state.review,
                on_llm_call=on_classify,
            )
            extractor = ExtractionService(repository=repository)

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
                if tool == "rob2":
                    assessment = rob2.assess(record)
                    await repository.save_rob2_assessment(state.workflow_id, assessment)
                elif tool == "robins_i":
                    assessment = robins_i.assess(record)
                    await repository.save_robins_i_assessment(state.workflow_id, assessment)
                else:
                    assessment = casp.assess(record)
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

                grade_assessment = grade.assess_outcome(
                    outcome_name="primary_outcome",
                    number_of_studies=1,
                    study_design=record.study_design,
                )
                await repository.save_grade_assessment(state.workflow_id, grade_assessment)

                if rc and rc.verbose:
                    rob_judgment = (
                        assessment.overall_judgment.value
                        if hasattr(assessment, "overall_judgment")
                        else getattr(assessment, "overall_summary", "unknown")
                    )
                    extraction_summary = (
                        record.results_summary.get("summary") or ""
                    )[:300]
                    rc.log_extraction_paper(
                        paper_id=paper.paper_id,
                        design=design.value,
                        extraction_summary=extraction_summary,
                        rob_judgment=rob_judgment,
                    )

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
            render_rob_traffic_light(rob2_rows, robins_i_rows, state.artifacts["rob_traffic_light"])
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


class SynthesisNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> FinalizeNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("phase_5_synthesis", "Building narrative synthesis...", total=1)
        feasibility = assess_meta_analysis_feasibility(state.extraction_records)
        narrative = build_narrative_synthesis("primary_outcome", state.extraction_records)
        if rc and rc.verbose:
            rc.log_synthesis(
                feasible=feasibility.feasible,
                groups=feasibility.groupings,
                rationale=feasibility.rationale,
                n_studies=narrative.n_studies,
                direction=narrative.effect_direction_summary,
            )
        Path(state.artifacts["narrative_synthesis"]).write_text(
            json.dumps(
                {
                    "feasibility": feasibility.model_dump(),
                    "narrative": narrative.model_dump(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            await repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="synthesis_summary",
                    decision="completed",
                    rationale=(
                        f"feasible={feasibility.feasible}, groups={len(feasibility.groupings)}, "
                        f"narrative_studies={narrative.n_studies}"
                    ),
                    actor="workflow_run",
                    phase="phase_5_synthesis",
                )
            )
            await repository.save_checkpoint(state.workflow_id, "phase_5_synthesis", papers_processed=len(state.extraction_records))
        if rc:
            rc.emit_phase_done("phase_5_synthesis", {"feasible": feasibility.feasible, "n_studies": len(state.extraction_records)})
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

        narrative_path = Path(state.artifacts["narrative_synthesis"])
        narrative: dict | None = None
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

            def _on_write(**kw):
                if rc:
                    rc.log_api_call(call_type="llm_writing", **kw)

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
                    on_llm_call=_on_write if rc and rc.verbose else None,
                    provider=provider if rc and rc.verbose else None,
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

        manuscript_path = Path(state.artifacts["manuscript_md"])
        manuscript_path.write_text(
            "\n\n".join(sections_written),
            encoding="utf-8",
        )

        if rc:
            rc.emit_phase_done("phase_6_writing", {"sections": len(sections_written)})
        return FinalizeNode()


class FinalizeNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> End[dict[str, str | int | dict[str, int] | dict[str, str]]]:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("finalize", "Writing run summary...")
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
            "artifacts": state.artifacts,
        }
        Path(state.artifacts["run_summary"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        await update_registry_status(state.log_root, state.workflow_id, "completed")
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
    log_root: str = "logs",
    output_root: str = "data/outputs",
    run_context: RunContext | None = None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    """Resume a workflow from its last checkpoint."""
    if workflow_id is None and topic is None:
        raise ValueError("Either workflow_id or topic must be provided for resume")
    entry = None
    if workflow_id:
        entry = await find_by_workflow_id(log_root, workflow_id)
        if entry is None:
            entry = await find_by_workflow_id_fallback(log_root, workflow_id)
            if entry is not None:
                config_hash = _hash_config(review_path) if os.path.isfile(review_path) else ""
                await register_workflow(
                    log_root=log_root,
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
        matches = await find_by_topic(log_root, search_topic, config_hash)
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
        log_root=log_root,
        output_root=output_root,
    )
    state.run_context = run_context
    state.run_id = _now_utc()
    if run_context is not None:
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
    log_root: str = "logs",
    output_root: str = "data/outputs",
    run_context: RunContext | None = None,
    fresh: bool = False,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    review, settings = load_configs(review_path, settings_path)
    config_hash = _hash_config(review_path)
    matches = await find_by_topic(log_root, review.research_question, config_hash)
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
                    log_root=log_root,
                    output_root=output_root,
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
                        log_root=log_root,
                        output_root=output_root,
                        run_context=run_context,
                    )
            except EOFError:
                pass

    if run_context is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, _make_sigint_handler(run_context))
        except NotImplementedError:
            pass  # Windows: add_signal_handler not available

    start = StartNode()
    initial = ReviewState(
        review_path=review_path,
        settings_path=settings_path,
        log_root=log_root,
        output_root=output_root,
        run_context=run_context,
    )
    result = await RUN_GRAPH.run(start, state=initial)
    return result.output


def run_workflow_sync(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    log_root: str = "logs",
    output_root: str = "data/outputs",
    run_context: RunContext | None = None,
    fresh: bool = False,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    return asyncio.run(
        run_workflow(
            review_path=review_path,
            settings_path=settings_path,
            log_root=log_root,
            output_root=output_root,
            run_context=run_context,
            fresh=fresh,
        )
    )
