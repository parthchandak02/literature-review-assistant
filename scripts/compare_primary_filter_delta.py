#!/usr/bin/env python3
"""One-time live delta test for primary-study query filtering.

Runs each connector twice for the same topic:
- baseline query (without primary-study exclusion clause)
- filtered query (with exclusion clause where supported)

Prints a Rich summary table and writes JSON output for auditing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.config.loader import load_configs
from src.models import CandidatePaper, ReviewConfig
from src.search.arxiv import ArxivConnector
from src.search.clinicaltrials import ClinicalTrialsConnector
from src.search.crossref import CrossrefConnector
from src.search.embase import EmbaseConnector
from src.search.ieee_xplore import IEEEXploreConnector
from src.search.openalex import OpenAlexConnector
from src.search.pubmed import PubMedConnector
from src.search.scopus import ScopusConnector
from src.search.semantic_scholar import SemanticScholarConnector
from src.search.web_of_science import WebOfScienceConnector

console = Console()

CONNECTOR_ORDER = [
    "pubmed",
    "scopus",
    "web_of_science",
    "embase",
    "openalex",
    "crossref",
    "semantic_scholar",
    "ieee_xplore",
    "arxiv",
    "clinicaltrials_gov",
]

CONNECTOR_CTORS: dict[str, Any] = {
    "pubmed": PubMedConnector,
    "scopus": ScopusConnector,
    "web_of_science": WebOfScienceConnector,
    "embase": EmbaseConnector,
    "openalex": OpenAlexConnector,
    "crossref": CrossrefConnector,
    "semantic_scholar": SemanticScholarConnector,
    "ieee_xplore": IEEEXploreConnector,
    "arxiv": ArxivConnector,
    "clinicaltrials_gov": ClinicalTrialsConnector,
}

_PUBMED_PRIMARY_ONLY_EXCLUSION = (
    "NOT ("
    '"systematic review"[Publication Type] OR '
    '"meta-analysis"[Publication Type] OR '
    '"review"[Publication Type] OR '
    '"systematic review"[Title] OR '
    '"scoping review"[Title] OR '
    '"narrative review"[Title] OR '
    '"umbrella review"[Title] OR '
    '"meta-analysis"[Title] OR '
    '"meta analysis"[Title]'
    ")"
)


def _dedupe_keywords(config: ReviewConfig) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in list(config.keywords):
        cleaned = term.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped


def _base_boolean_query(config: ReviewConfig) -> str:
    terms = _dedupe_keywords(config)
    return "(" + " OR ".join(f'"{t}"' for t in terms) + ")"


def _build_filtered_query(config: ReviewConfig, db_name: str) -> str:
    base = _base_boolean_query(config)
    kws = _dedupe_keywords(config)
    short_query = " ".join(kws[:8]) if kws else (config.pico.intervention[:80])
    name = db_name.lower()

    if name == "pubmed":
        return (
            f"({base}) "
            f"AND ({config.pico.population}[Title/Abstract] OR {config.pico.intervention}[Title/Abstract]) "
            f"AND {_PUBMED_PRIMARY_ONLY_EXCLUSION}"
        )
    if name == "arxiv":
        return f'all:("{config.research_question}") OR all:("{config.pico.intervention}")'
    if name == "ieee_xplore":
        kw_part1 = " OR ".join(f'"{k}"' for k in kws[:8]) if kws else f'"{config.pico.intervention[:60]}"'
        kw_part2 = " OR ".join(f'"{k}"' for k in kws[8:16]) if len(kws) > 8 else kw_part1
        return f"({kw_part1}) AND ({kw_part2})"
    if name == "semantic_scholar":
        return short_query
    if name == "openalex":
        return short_query
    if name in {"clinicaltrials", "clinicaltrials_gov"}:
        return " OR ".join(f'"{k}"' for k in kws[:12]) if kws else short_query
    if name == "crossref":
        return f'"{config.research_question}" OR ({base})'
    if name in {"web_of_science", "wos"}:
        wos_part1 = " OR ".join(f'TS="{k}"' for k in kws[:8]) if kws else f'TS="{config.pico.intervention[:60]}"'
        wos_part2 = " OR ".join(f'TS="{k}"' for k in kws[8:16]) if len(kws) > 8 else wos_part1
        date_s = config.date_range_start or 2010
        date_e = config.date_range_end or 2026
        return f"({wos_part1}) AND ({wos_part2}) AND PY={date_s}-{date_e} AND NOT DT=Review"
    if name in {"scopus", "embase"}:
        kw_part1 = " OR ".join(f'"{k}"' for k in kws[:8]) if kws else f'"{config.pico.intervention[:60]}"'
        kw_part2 = " OR ".join(f'"{k}"' for k in kws[8:16]) if len(kws) > 8 else kw_part1
        date_s = config.date_range_start or 2009
        date_e = config.date_range_end or 2027
        return (
            f"TITLE-ABS-KEY({kw_part1}) AND "
            f"TITLE-ABS-KEY({kw_part2}) "
            f"AND PUBYEAR > {date_s - 1} AND PUBYEAR < {date_e + 1} "
            "AND NOT DOCTYPE(re)"
        )
    return base


def _build_baseline_query(db_name: str, filtered_query: str) -> str:
    name = db_name.lower()
    if name == "pubmed":
        return re.sub(r"\s+AND\s+NOT\s*\(.*\)\s*$", "", filtered_query, flags=re.IGNORECASE).strip()
    if name in {"scopus", "embase"}:
        return filtered_query.replace(" AND NOT DOCTYPE(re)", "").strip()
    if name in {"web_of_science", "wos"}:
        return filtered_query.replace(" AND NOT DT=Review", "").strip()
    return filtered_query


def _paper_sig(p: CandidatePaper) -> str:
    doi = (p.doi or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return f"title:{(p.title or '').strip().lower()}"


def _mode_for_connector(connector: str) -> str:
    if connector in {"pubmed", "scopus", "web_of_science", "embase"}:
        return "query_exclusion"
    return "screening_only"


@dataclass
class ConnectorDelta:
    connector: str
    expected_mode: str
    baseline_count: int | None
    filtered_count: int | None
    delta: int | None
    overlap_top_n: int | None
    baseline_ok: bool
    filtered_ok: bool
    baseline_error: str | None
    filtered_error: str | None
    baseline_query: str
    filtered_query: str
    filtered_limits_applied: list[str] | None


async def _run_search_once(
    connector_obj: Any,
    query: str,
    max_results: int,
    date_start: int | None,
    date_end: int | None,
) -> tuple[int, list[CandidatePaper], list[str | None]]:
    result = await connector_obj.search(
        query=query,
        max_results=max_results,
        date_start=date_start,
        date_end=date_end,
    )
    if isinstance(result, list):
        results = result
    else:
        results = [result]
    total = sum(r.records_retrieved for r in results)
    papers: list[CandidatePaper] = []
    limits: list[str | None] = []
    for r in results:
        papers.extend(r.papers)
        limits.append(r.limits_applied)
    return total, papers, limits


def _load_review_config(review_path: str, settings_path: str) -> ReviewConfig:
    if pathlib.Path(review_path).exists():
        with pathlib.Path(review_path).open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        return ReviewConfig.model_validate(raw)
    review, _settings = load_configs(review_path, settings_path)
    return review


async def run_delta_test(
    max_results: int,
    overlap_top_n: int,
    review_path: str,
    settings_path: str,
    label: str,
) -> tuple[list[ConnectorDelta], pathlib.Path]:
    review = _load_review_config(review_path, settings_path)
    date_start = review.date_range_start
    date_end = review.date_range_end

    rows: list[ConnectorDelta] = []
    for connector in CONNECTOR_ORDER:
        filtered_query = _build_filtered_query(review, connector)
        baseline_query = _build_baseline_query(connector, filtered_query)
        ctor = CONNECTOR_CTORS[connector]

        try:
            connector_obj = ctor("wf-one-off-filter-delta")
        except Exception as exc:
            err = f"init_failed: {type(exc).__name__}: {exc}"
            rows.append(
                ConnectorDelta(
                    connector=connector,
                    expected_mode=_mode_for_connector(connector),
                    baseline_count=None,
                    filtered_count=None,
                    delta=None,
                    overlap_top_n=None,
                    baseline_ok=False,
                    filtered_ok=False,
                    baseline_error=err,
                    filtered_error=err,
                    baseline_query=baseline_query,
                    filtered_query=filtered_query,
                    filtered_limits_applied=None,
                )
            )
            continue

        baseline_ok = True
        filtered_ok = True
        baseline_err: str | None = None
        filtered_err: str | None = None
        baseline_count: int | None = None
        filtered_count: int | None = None
        overlap_count: int | None = None
        filtered_limits: list[str] | None = None

        try:
            baseline_count, baseline_papers, _ = await _run_search_once(
                connector_obj, baseline_query, max_results, date_start, date_end
            )
        except Exception as exc:
            baseline_ok = False
            baseline_err = f"{type(exc).__name__}: {exc}"
            baseline_papers = []

        try:
            filtered_count, filtered_papers, limits = await _run_search_once(
                connector_obj, filtered_query, max_results, date_start, date_end
            )
            filtered_limits = [x for x in limits if x]
        except Exception as exc:
            filtered_ok = False
            filtered_err = f"{type(exc).__name__}: {exc}"
            filtered_papers = []

        if baseline_ok and filtered_ok:
            b_set = {_paper_sig(p) for p in baseline_papers[:overlap_top_n]}
            f_set = {_paper_sig(p) for p in filtered_papers[:overlap_top_n]}
            overlap_count = len(b_set.intersection(f_set))

        delta = None
        if baseline_count is not None and filtered_count is not None:
            delta = filtered_count - baseline_count

        rows.append(
            ConnectorDelta(
                connector=connector,
                expected_mode=_mode_for_connector(connector),
                baseline_count=baseline_count,
                filtered_count=filtered_count,
                delta=delta,
                overlap_top_n=overlap_count,
                baseline_ok=baseline_ok,
                filtered_ok=filtered_ok,
                baseline_error=baseline_err,
                filtered_error=filtered_err,
                baseline_query=baseline_query,
                filtered_query=filtered_query,
                filtered_limits_applied=filtered_limits,
            )
        )

    output_dir = pathlib.Path("runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "run"
    out_path = output_dir / f"primary_filter_delta_{safe_label}_{timestamp}.json"
    out_path.write_text(json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8")
    return rows, out_path


def _print_summary(rows: list[ConnectorDelta], output_path: pathlib.Path, overlap_top_n: int) -> None:
    table = Table(title="Primary Filter Delta (One-Time Live Test)")
    table.add_column("Connector")
    table.add_column("Mode")
    table.add_column("Baseline", justify="right")
    table.add_column("Filtered", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column(f"OverlapTop{overlap_top_n}", justify="right")
    table.add_column("Status")

    for row in rows:
        status = "OK" if row.baseline_ok and row.filtered_ok else "ERROR"
        b = "--" if row.baseline_count is None else str(row.baseline_count)
        f = "--" if row.filtered_count is None else str(row.filtered_count)
        d = "--" if row.delta is None else str(row.delta)
        o = "--" if row.overlap_top_n is None else str(row.overlap_top_n)
        table.add_row(row.connector, row.expected_mode, b, f, d, o, status)

    console.print(table)
    console.print(f"JSON report: {output_path}")

    failures = [r for r in rows if not (r.baseline_ok and r.filtered_ok)]
    if failures:
        err_table = Table(title="Connector Errors")
        err_table.add_column("Connector")
        err_table.add_column("Baseline Error")
        err_table.add_column("Filtered Error")
        for r in failures:
            err_table.add_row(r.connector, r.baseline_error or "--", r.filtered_error or "--")
        console.print(err_table)


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time live comparison for primary-study query filter impact.")
    parser.add_argument("--max-results", type=int, default=40, help="Max results per connector per run")
    parser.add_argument("--overlap-top-n", type=int, default=50, help="Top-N results used for overlap snapshot")
    parser.add_argument(
        "--review-path",
        type=str,
        default="config/review.yaml",
        help="Path to review yaml or config_snapshot yaml to drive query generation",
    )
    parser.add_argument(
        "--settings-path",
        type=str,
        default="config/settings.yaml",
        help="Path to settings yaml for fallback config loading",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="run",
        help="Short label used in output json filename",
    )
    args = parser.parse_args()

    async def _run() -> None:
        rows, out_path = await run_delta_test(
            args.max_results,
            args.overlap_top_n,
            args.review_path,
            args.settings_path,
            args.label,
        )
        _print_summary(rows, out_path, args.overlap_top_n)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
