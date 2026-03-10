"""Search strategy coordinator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

from src.db.repositories import WorkflowRepository
from src.models import DecisionLogEntry, ReviewConfig, SearchResult
from src.orchestration.gates import GateRunner
from src.search.base import SearchConnector
from src.search.deduplication import deduplicate_papers

_logger = logging.getLogger(__name__)
_slog = structlog.get_logger()


def build_boolean_query(config: ReviewConfig) -> str:
    # Use only keywords, NOT full PICO description strings.
    # PICO descriptions (intervention/outcome) are multi-sentence text that never
    # appears verbatim in papers and produces zero-result queries on ClinicalTrials.gov
    # and nonsensical queries on all other databases. Keywords are the correct input.
    keyword_terms = list(config.keywords)
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
    if config.search_overrides:
        if name in config.search_overrides:
            _slog.info(
                "search_override_status",
                database=name,
                status="applied",
                detail=f"verbatim override ({len(config.search_overrides[name])} chars)",
            )
            return config.search_overrides[name]
        _slog.info(
            "search_override_status",
            database=name,
            status="miss",
            detail=f"search_overrides present but no key for '{name}' -- keys: {list(config.search_overrides.keys())}",
        )
    else:
        _slog.info(
            "search_override_status",
            database=name,
            status="absent",
            detail="config.search_overrides is None -- using fallback query",
        )
    base = build_boolean_query(config)
    # short_query: first 8 keywords space-separated for relevance-ranked APIs (S2, OpenAlex).
    # Use natural keyword terms, NOT full PICO description strings which never appear
    # verbatim in papers and produce near-zero recall on semantic search APIs.
    kws = config.keywords or []
    short_query = " ".join(kws[:8]) if kws else (config.pico.intervention[:80])
    if name == "pubmed":
        return f"({base}) AND ({config.pico.population}[Title/Abstract] OR {config.pico.intervention}[Title/Abstract])"
    if name == "arxiv":
        return f'all:("{config.research_question}") OR all:("{config.pico.intervention}")'
    if name == "ieee_xplore":
        kws = config.keywords or []
        kw_part1 = " OR ".join(f'"{k}"' for k in kws[:8]) if kws else f'"{config.pico.intervention[:60]}"'
        kw_part2 = " OR ".join(f'"{k}"' for k in kws[8:16]) if len(kws) > 8 else kw_part1
        return f"({kw_part1}) AND ({kw_part2})"
    if name == "semantic_scholar":
        return short_query
    if name == "openalex":
        # OpenAlex uses relevance-ranked full-text search via the search= param.
        # A short, focused phrase (5-10 keywords) gives far better precision than
        # the broad boolean OR fallback. Mirror the Semantic Scholar approach.
        return short_query
    if name in {"clinicaltrials_gov", "clinicaltrials"}:
        # ClinicalTrials.gov plain-text search: OR-joined quoted keywords work best.
        # PICO descriptions never appear verbatim in trial records and always return 0.
        # Use up to 12 keywords; quote each one so the registry treats them as phrases.
        ct_kws = config.keywords or []
        return " OR ".join(f'"{k}"' for k in ct_kws[:12]) if ct_kws else short_query
    if name == "crossref":
        return f'"{config.research_question}" OR ({base})'
    if name == "perplexity_search":
        return short_query
    if name in {"web_of_science", "wos"}:
        # WoS Starter API: each term needs own TS= prefix inside parenthesized OR groups.
        # WRONG: TS=("term1" OR "term2") -- causes 512 server error
        # CORRECT: (TS="term1" OR TS="term2") AND (TS="term3" OR TS="term4")
        kws = config.keywords or []
        wos_part1 = " OR ".join(f'TS="{k}"' for k in kws[:8]) if kws else f'TS="{config.pico.intervention[:60]}"'
        wos_part2 = " OR ".join(f'TS="{k}"' for k in kws[8:16]) if len(kws) > 8 else wos_part1
        date_s = config.date_range_start or 2010
        date_e = config.date_range_end or 2026
        return f"({wos_part1}) AND ({wos_part2}) AND PY={date_s}-{date_e}"
    if name == "scopus":
        # Use Scopus field-code syntax: TITLE-ABS-KEY covers title, abstract, and author keywords.
        # Split keywords into two groups to build two AND-joined TITLE-ABS-KEY clauses.
        # Using full PICO strings as phrases produces 0 results because Scopus phrase
        # matching is strict and long PICO sentences never appear verbatim in papers.
        kws = config.keywords or []
        kw_part1 = " OR ".join(f'"{k}"' for k in kws[:8]) if kws else f'"{config.pico.intervention[:60]}"'
        # Second clause: use keywords[8:16] for broader coverage; fall back to first group.
        kw_part2 = " OR ".join(f'"{k}"' for k in kws[8:16]) if len(kws) > 8 else kw_part1
        date_s = config.date_range_start or 2009
        date_e = config.date_range_end or 2027
        return (
            f"TITLE-ABS-KEY({kw_part1}) AND "
            f"TITLE-ABS-KEY({kw_part2}) "
            f"AND PUBYEAR > {date_s - 1} AND PUBYEAR < {date_e + 1}"
        )
    return base


class SearchStrategyCoordinator:
    def __init__(
        self,
        workflow_id: str,
        config: ReviewConfig,
        connectors: list[SearchConnector],
        repository: WorkflowRepository,
        gate_runner: GateRunner,
        output_dir: str = "runs",
        on_connector_done: Callable[[str, str, int, str, int | None, int | None, str | None], None] | None = None,
        low_recall_threshold: int = 10,
    ):
        self.workflow_id = workflow_id
        self.config = config
        self.connectors = connectors
        self.repository = repository
        self.gate_runner = gate_runner
        self.output_dir = Path(output_dir)
        self.on_connector_done = on_connector_done
        self.low_recall_threshold = low_recall_threshold
        # Populated after run() completes; maps connector name -> query string used.
        self.query_map: dict[str, str] = {}

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
                        workflow_id=self.workflow_id,
                        decision_type="search_connector_error",
                        decision="failed",
                        rationale=f"{connector.name}: {type(outcome).__name__}: {outcome}",
                        actor="search_strategy",
                        phase="phase_2_search",
                    )
                )
                continue
            result_list: list[SearchResult] = outcome if isinstance(outcome, list) else [outcome]
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

            async def _save_one(r: SearchResult) -> None:
                try:
                    await self.repository.save_search_result(r)
                except Exception:
                    _logger.exception(
                        "save_search_result failed: workflow_id=%s, papers=%d, first_paper=%s",
                        self.workflow_id,
                        len(r.papers),
                        r.papers[0].paper_id if r.papers else None,
                    )
                    raise

            await asyncio.gather(*[_save_one(r) for r in result_list])
            results.extend(result_list)

        # Low-recall diagnostic: warn when a connector returned very few records.
        # This surfaces over-restricted queries early so the user can fix before screening.
        if self.low_recall_threshold > 0:
            for db_name, result_list in connector_results.items():
                total = sum(r.records_retrieved for r in result_list)
                if total < self.low_recall_threshold:
                    _logger.warning(
                        "LOW RECALL: %s returned only %d records (threshold: %d). "
                        "Consider broadening search_overrides.%s in config/review.yaml. "
                        "Check doc_search_strategies_appendix.md for the exact query used.",
                        db_name,
                        total,
                        self.low_recall_threshold,
                        db_name,
                    )

        all_papers = [paper for result in results for paper in result.papers]
        _, dedup_count = deduplicate_papers(all_papers)
        query_map = {connector.name: query for connector, query, _ in tasks}
        self.query_map = query_map
        await self._write_search_appendix(query_map, connector_results, errors, dedup_count)
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
