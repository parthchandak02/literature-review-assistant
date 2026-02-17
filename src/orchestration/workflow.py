"""Single-path workflow orchestration for `run`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.table import Table

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
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
from src.orchestration.context import RunContext
from src.utils.logging_paths import OutputRunPaths, create_output_paths, create_run_paths
from src.utils import structured_log
from src.visualization import render_rob_traffic_light


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


@dataclass
class ReviewState:
    review_path: str
    settings_path: str
    log_root: str
    output_root: str
    run_context: RunContext | None = None
    run_id: str = ""
    workflow_id: str = ""
    review: ReviewConfig | None = None
    settings: SettingsConfig | None = None
    db_path: str = ""
    log_dir: str = ""
    output_dir: str = ""
    connector_init_failures: dict[str, str] = field(default_factory=dict)
    search_counts: dict[str, int] = field(default_factory=dict)
    dedup_count: int = 0
    deduped_papers: list[CandidatePaper] = field(default_factory=list)
    included_papers: list[CandidatePaper] = field(default_factory=list)
    extraction_records: list[ExtractionRecord] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


def _rc(state: ReviewState) -> RunContext | None:
    return state.run_context


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
        state.artifacts["coverage_report"] = str(output_paths.run_dir / "fulltext_retrieval_coverage.md")
        state.artifacts["disagreements_report"] = str(output_paths.run_dir / "disagreements_report.md")
        state.artifacts["rob_traffic_light"] = str(output_paths.run_dir / "rob_traffic_light.png")
        state.artifacts["narrative_synthesis"] = str(output_paths.run_dir / "narrative_synthesis.json")
        if rc:
            rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
        return SearchNode()


class SearchNode(BaseNode[ReviewState]):
    async def run(self, ctx: GraphRunContext[ReviewState]) -> ScreeningNode:
        state = ctx.state
        rc = _rc(state)
        if rc:
            rc.emit_phase_start("phase_2_search", "Running connectors...")
        assert state.review is not None
        assert state.settings is not None

        connectors, connector_init_failures = _build_connectors(state.workflow_id, state.review.target_databases)
        state.connector_init_failures = connector_init_failures
        if rc:
            for name, err in connector_init_failures.items():
                rc.log_api_call(name, "failed", err, None, phase="phase_2_search")

        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            await repository.create_workflow(state.workflow_id, state.review.research_question, _hash_config(state.review_path))
            gate_runner = GateRunner(repository, state.settings)
            def _on_connector_done(s: str, st: str, d: str | None, r: int | None) -> None:
                if rc and rc.verbose:
                    rc.log_api_call(s, st, d, r, phase="phase_2_search")
                structured_log.log_connector_result(
                    connector=s, status=st, records=r, error=d if st != "success" else None
                )

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
            rc.emit_phase_start("phase_3_screening", f"Screening {len(state.deduped_papers)} papers...")
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
                on_llm_call = lambda s, st, d, r, **kw: rc.log_api_call(s, st, d, r, **kw)
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
            screener = DualReviewerScreener(
                repository=repository,
                provider=provider,
                review=state.review,
                settings=state.settings,
                llm_client=llm_client,
                on_llm_call=on_llm_call,
                on_progress=on_progress,
                on_prompt=on_prompt,
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
            await repository.save_checkpoint(state.workflow_id, "phase_3_screening", papers_processed=len(state.included_papers))
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
        if rc:
            rc.emit_phase_start("phase_4_extraction_quality", f"Extracting {len(state.included_papers)} papers...")
        assert state.review is not None
        assert state.settings is not None

        router = StudyRouter()
        rob2 = Rob2Assessor()
        robins_i = RobinsIAssessor()
        casp = CaspAssessor()
        grade = GradeAssessor()

        rob2_rows = []
        records: list[ExtractionRecord] = []
        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            gate_runner = GateRunner(repository, state.settings)
            provider = LLMProvider(state.settings, repository)
            classifier = StudyClassifier(provider=provider, repository=repository, review=state.review)
            extractor = ExtractionService(repository=repository)

            for paper in state.included_papers:
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

                tool = router.route_tool(record)
                if tool == "rob2":
                    assessment = rob2.assess(record)
                    rob2_rows.append(assessment)
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
            render_rob_traffic_light(rob2_rows, state.artifacts["rob_traffic_light"])
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
            rc.emit_phase_start("phase_5_synthesis", "Building narrative synthesis...")
        feasibility = assess_meta_analysis_feasibility(state.extraction_records)
        narrative = build_narrative_synthesis("primary_outcome", state.extraction_records)
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
        if rc:
            rc.emit_phase_done("finalize")
        return End(summary)


RUN_GRAPH = Graph(
    nodes=[StartNode, SearchNode, ScreeningNode, ExtractionQualityNode, SynthesisNode, FinalizeNode],
    state_type=ReviewState,
    run_end_type=dict,
)


async def run_workflow(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    log_root: str = "logs",
    output_root: str = "data/outputs",
    run_context: RunContext | None = None,
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
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
) -> dict[str, str | int | dict[str, int] | dict[str, str]]:
    return asyncio.run(
        run_workflow(
            review_path=review_path,
            settings_path=settings_path,
            log_root=log_root,
            output_root=output_root,
            run_context=run_context,
        )
    )
