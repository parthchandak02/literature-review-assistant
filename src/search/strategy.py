"""Search strategy coordinator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.db.repositories import WorkflowRepository
from src.models import DecisionLogEntry, ReviewConfig, SearchResult
from src.orchestration.gates import GateRunner
from src.search.base import SearchConnector
from src.search.deduplication import deduplicate_papers


def build_boolean_query(config: ReviewConfig) -> str:
    keyword_terms = [*config.keywords, config.pico.intervention, config.pico.outcome]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped_terms: list[str] = []
    for term in keyword_terms:
        normalized = term.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped_terms.append(term.strip())
    keyword_part = " OR ".join(f'"{k}"' for k in deduped_terms)
    return f"({keyword_part})"

def build_database_query(config: ReviewConfig, database_name: str) -> str:
    name = database_name.lower()
    if config.search_overrides and name in config.search_overrides:
        return config.search_overrides[name]
    base = build_boolean_query(config)
    short_query = (
        f"{config.pico.intervention} {config.pico.population} {config.pico.outcome}"
    )
    if name == "pubmed":
        return (
            f"({base})"
            f" AND ({config.pico.population}[Title/Abstract] OR {config.pico.intervention}[Title/Abstract])"
        )
    if name == "arxiv":
        return f'all:("{config.research_question}") OR all:("{config.pico.intervention}")'
    if name == "ieee_xplore":
        return f'("{config.pico.intervention}") AND ("{config.pico.outcome}")'
    if name == "semantic_scholar":
        return short_query
    if name == "crossref":
        return f'"{config.research_question}" OR ({base})'
    if name == "perplexity_search":
        return short_query
    return base


class SearchStrategyCoordinator:
    def __init__(
        self,
        workflow_id: str,
        config: ReviewConfig,
        connectors: list[SearchConnector],
        repository: WorkflowRepository,
        gate_runner: GateRunner,
        output_dir: str = "data/outputs",
        on_connector_done: Callable[
            [str, str, int, str, int | None, int | None, str | None], None
        ] | None = None,
    ):
        self.workflow_id = workflow_id
        self.config = config
        self.connectors = connectors
        self.repository = repository
        self.gate_runner = gate_runner
        self.output_dir = Path(output_dir)
        self.on_connector_done = on_connector_done

    async def run(
        self,
        max_results: int = 500,
        per_database_limits: dict[str, int] | None = None,
    ) -> tuple[list[SearchResult], int]:
        tasks: list[tuple[SearchConnector, str, Any]] = []
        for connector in self.connectors:
            query = build_database_query(self.config, connector.name)
            limit = (per_database_limits or {}).get(connector.name, max_results)
            task = connector.search(
                query=query,
                max_results=limit,
                date_start=self.config.date_range_start,
                date_end=self.config.date_range_end,
            )
            tasks.append((connector, query, task))

        gathered = await asyncio.gather(*(t[2] for t in tasks), return_exceptions=True)
        results: list[SearchResult] = []
        connector_results: dict[str, list[SearchResult]] = {}
        errors: dict[str, str] = {}
        for (connector, query, _), outcome in zip(tasks, gathered):
            if isinstance(outcome, Exception):
                err_msg = f"{type(outcome).__name__}: {outcome}"
                errors[connector.name] = err_msg
                connector_results[connector.name] = []
                if self.on_connector_done:
                    self.on_connector_done(
                        connector.name,
                        "failed",
                        0,
                        query,
                        self.config.date_range_start,
                        self.config.date_range_end,
                        err_msg,
                    )
                await self.repository.append_decision_log(
                    DecisionLogEntry(
                        decision_type="search_connector_error",
                        decision="failed",
                        rationale=f"{connector.name}: {type(outcome).__name__}: {outcome}",
                        actor="search_strategy",
                        phase="phase_2_search",
                    )
                )
                continue
            result_list: list[SearchResult] = (
                outcome if isinstance(outcome, list) else [outcome]
            )
            connector_results[connector.name] = result_list
            if self.on_connector_done:
                total = sum(r.records_retrieved for r in result_list)
                self.on_connector_done(
                    connector.name,
                    "success",
                    total,
                    query,
                    self.config.date_range_start,
                    self.config.date_range_end,
                    None,
                )
            for r in result_list:
                await self.repository.save_search_result(r)
                results.append(r)

        all_papers = [paper for result in results for paper in result.papers]
        _, dedup_count = deduplicate_papers(all_papers)
        query_map = {connector.name: query for connector, query, _ in tasks}
        await self._write_search_appendix(
            query_map, connector_results, errors, dedup_count
        )
        await self.gate_runner.run_search_volume_gate(
            workflow_id=self.workflow_id,
            phase="phase_2_search",
            total_records=sum(r.records_retrieved for r in results),
        )
        return results, dedup_count

    async def _write_search_appendix(
        self,
        query_map: dict[str, str],
        connector_results: dict[str, list[SearchResult]],
        errors: dict[str, str],
        dedup_count: int,
    ) -> Path:
        output_dir = self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "doc_search_strategies_appendix.md"
        lines = ["# Search Strategies Appendix", ""]
        for connector_name, query in query_map.items():
            lines.append(f"## {connector_name}")
            lines.append(f"- Query: `{query}`")
            result_list = connector_results.get(connector_name, [])
            if connector_name in errors:
                lines.append("- Retrieved: 0")
                lines.append("- Status: failed")
                lines.append(f"- Error: {errors.get(connector_name, 'unknown_error')}")
            elif result_list:
                if len(result_list) == 1:
                    r = result_list[0]
                    lines.append(f"- Search date: {r.search_date}")
                    lines.append(f"- Retrieved: {r.records_retrieved}")
                else:
                    # Perplexity attribution: multiple sources
                    lines.append(f"- Search date: {result_list[0].search_date}")
                    parts = [f"{r.database_name}: {r.records_retrieved}" for r in result_list]
                    lines.append(f"- Retrieved (via attribution): {', '.join(parts)}")
                lines.append("- Status: success")
            else:
                lines.append("- Retrieved: 0")
                lines.append("- Status: success")
            lines.append("")
        lines.append(f"Deduplicated records removed: {dedup_count}")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
