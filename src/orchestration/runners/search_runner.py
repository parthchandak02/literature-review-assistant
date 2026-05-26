"""Runner for SearchNode – extracted from workflow.py lines 410-780."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from pydantic_graph import End, GraphRunContext

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import (
    register as register_workflow,
)
from src.db.workflow_registry import (
    update_status as update_registry_status,
)
from src.models import GateStatus, WorkflowStepRecord
from src.orchestration.gates import GateRunner
from src.orchestration.helpers.runtime import hash_config as helper_hash_config
from src.orchestration.helpers.runtime import rc as helper_rc
from src.orchestration.helpers.search_connectors import build_connectors as helper_build_connectors
from src.orchestration.helpers.step_journal import journal_step_complete as helper_journal_step_complete
from src.orchestration.helpers.step_journal import journal_step_start as helper_journal_step_start
from src.orchestration.state import ReviewState
from src.protocol.generator import ProtocolGenerator
from src.search.base import SearchConnector
from src.search.csv_import import parse_masterlist_csv, parse_supplementary_csvs
from src.search.deduplication import deduplicate_papers
from src.search.source_quality import quality_priority_score
from src.search.strategy import SearchStrategyCoordinator
from src.utils import structured_log

_log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


def _rc(state: ReviewState):
    return helper_rc(state)


def _hash_config(path: str) -> str:
    return helper_hash_config(path)


def _build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list[SearchConnector], dict[str, str]]:
    return helper_build_connectors(workflow_id, target_databases)


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
    return await helper_journal_step_start(
        repo,
        workflow_id,
        phase,
        step_name,
        paper_id=paper_id,
        parent_step_id=parent_step_id,
        max_attempts=max_attempts,
    )


async def _journal_step_complete(repo: WorkflowRepository, record: WorkflowStepRecord, **kwargs) -> None:
    await helper_journal_step_complete(repo, record, **kwargs)


async def run_search_node(state: ReviewState, ctx: GraphRunContext[ReviewState]) -> End[dict] | None:
    rc = _rc(state)
    assert state.review is not None
    assert state.settings is not None

    _phase_step: WorkflowStepRecord | None = None
    if state.db_path:
        try:
            async with get_db(state.db_path) as _jdb:
                _jrepo = WorkflowRepository(_jdb)
                _phase_step = await _journal_step_start(
                    _jrepo,
                    state.workflow_id,
                    "phase_2_search",
                    "search_phase",
                )
        except Exception:
            pass

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

            await gate_runner.run_search_volume_gate(state.workflow_id, "phase_2_search", csv_result.records_retrieved)
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
            protocol = protocol_generator.generate(state.workflow_id, state.review, state.settings)
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
        return None
    # --- end CSV branch ---

    connectors, connector_init_failures = _build_connectors(
        state.workflow_id,
        state.review.resolved_target_databases(),
    )
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
            if rc:
                rc.log_connector_result(
                    name=name,
                    status=status,
                    records=records,
                    query=query,
                    date_start=date_start,
                    date_end=date_end,
                    error=error,
                )
            else:
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
            low_recall_threshold=state.settings.search.low_recall_warning_threshold,
        )
        search_cfg = state.settings.search
        if rc and hasattr(rc, "log_status"):
            _names = ", ".join(c.name for c in connectors)
            rc.log_status(
                f"Search: {len(connectors)} connector(s) queued ({_names}). "
                "Each database line appears when that search finishes (order varies)."
            )
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
        supp_paths = state.review.supplementary_csv_paths if state.review else []
        if supp_paths:
            try:
                supp_results = parse_supplementary_csvs(supp_paths, state.workflow_id)
                await asyncio.gather(*[repository.save_search_result(sr) for sr in supp_results])
                for sr in supp_results:
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
        tier_weights = state.settings.search.quality_tier_weights or {}
        deduped = sorted(
            deduped,
            key=lambda paper: quality_priority_score(
                paper.source_database,
                tier_weights=tier_weights,
                open_index_bonus=state.settings.search.open_index_bonus,
                peer_review_bonus=state.settings.search.peer_review_bonus,
            ),
            reverse=True,
        )

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
        protocol = protocol_generator.generate(state.workflow_id, state.review, state.settings)
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

    if _phase_step and state.db_path:
        try:
            async with get_db(state.db_path) as _jdb:
                _jrepo = WorkflowRepository(_jdb)
                await _journal_step_complete(_jrepo, _phase_step)
        except Exception:
            _log.warning("SearchNode: step journal write failed", exc_info=True)

    return None
