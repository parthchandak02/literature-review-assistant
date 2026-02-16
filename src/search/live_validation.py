"""Live Phase 2 validation runner with log artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.orchestration.gates import GateRunner
from src.protocol.generator import ProtocolGenerator
from src.search.arxiv import ArxivConnector
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.pubmed import PubMedConnector
from src.search.semantic_scholar import SemanticScholarConnector
from src.search.crossref import CrossrefConnector
from src.search.perplexity_search import PerplexitySearchConnector
from src.search.strategy import SearchStrategyCoordinator
from src.utils.logging_paths import LogRunPaths, OutputRunPaths, create_output_paths, create_run_paths


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _hash_config(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _build_connectors(workflow_id: str, target_databases: list[str]) -> tuple[list[Any], dict[str, str]]:
    connectors: list[Any] = []
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
        except Exception as exc:  # best-effort mode
            failures[normalized] = f"{type(exc).__name__}: {exc}"
    return connectors, failures


async def run_live_phase2(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    log_root: str = "logs",
) -> dict[str, Any]:
    review, settings = load_configs(review_path, settings_path)
    workflow_id = f"wf-{uuid4().hex[:8]}"
    run_id = _now_utc()
    log_paths: LogRunPaths = create_run_paths(log_root=log_root, workflow_description=review.research_question)
    log_dir = log_paths.run_dir
    output_paths: OutputRunPaths = create_output_paths(
        output_root="data/outputs",
        workflow_description=review.research_question,
        run_dir_name=log_dir.name,
        date_folder=log_dir.parent.parent.name,
    )

    connectors, connector_init_failures = _build_connectors(workflow_id, review.target_databases)

    db_path = str(log_paths.runtime_db)
    async with get_db(db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(workflow_id, review.research_question, _hash_config(review_path))
        gate_runner = GateRunner(repository, settings)
        coordinator = SearchStrategyCoordinator(
            workflow_id=workflow_id,
            config=review,
            connectors=connectors,
            repository=repository,
            gate_runner=gate_runner,
            output_dir=str(output_paths.run_dir),
        )
        results, dedup_count = await coordinator.run(max_results=100)
        search_counts = await repository.get_search_counts(workflow_id)

        protocol_generator = ProtocolGenerator(output_dir=str(output_paths.run_dir))
        protocol = protocol_generator.generate(workflow_id, review)
        protocol_markdown = protocol_generator.render_markdown(protocol, review)
        protocol_path = protocol_generator.write_markdown(workflow_id, protocol_markdown)

        appendix_path = output_paths.search_appendix
        gate_cursor = await db.execute(
            """
            SELECT status, details, threshold, actual_value
            FROM gate_results
            WHERE workflow_id = ? AND gate_name = 'search_volume'
            ORDER BY id DESC LIMIT 1
            """,
            (workflow_id,),
        )
        gate_row = await gate_cursor.fetchone()
        gate_summary = {
            "status": str(gate_row[0]) if gate_row else "missing",
            "details": str(gate_row[1]) if gate_row else "missing",
            "threshold": str(gate_row[2]) if gate_row else "missing",
            "actual_value": str(gate_row[3]) if gate_row else "missing",
        }

    summary = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "topic": review.research_question,
        "target_databases": review.target_databases,
        "connector_init_failures": connector_init_failures,
        "successful_connectors": [r.database_name for r in results],
        "search_counts": search_counts,
        "dedup_count": dedup_count,
        "appendix_path": str(appendix_path),
        "protocol_path": str(protocol_path),
        "search_volume_gate": gate_summary,
        "log_dir": str(log_dir),
        "output_dir": str(output_paths.run_dir),
    }
    log_paths.run_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # Backward compatibility for older scripts reading legacy filename.
    (log_dir / "live_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log_paths.acceptance_checklist.write_text(
        "\n".join(
            [
                "# Acceptance Checklist",
                "",
                f"- Phase: phase_2_search",
                f"- Search volume gate status: {gate_summary['status']}",
                f"- Total retrieved: {sum(search_counts.values())}",
                f"- Successful connectors: {', '.join(summary['successful_connectors']) or 'none'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    log_paths.phase_readiness.write_text(
        "\n".join(
            [
                "# Phase Readiness",
                "",
                "Phase 2 run completed with unified logging.",
                "Phase 3 should reuse the same logging utility in src/utils/logging_paths.py.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    log_paths.revalidation_log.write_text(
        "Revalidation is run by explicit test commands; see terminal outputs for latest execution.\n",
        encoding="utf-8",
    )
    return summary


def run_live_phase2_sync(
    review_path: str = "config/review.yaml",
    settings_path: str = "config/settings.yaml",
    log_root: str = "logs",
) -> dict[str, Any]:
    return asyncio.run(run_live_phase2(review_path=review_path, settings_path=settings_path, log_root=log_root))
