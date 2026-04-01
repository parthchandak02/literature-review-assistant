from __future__ import annotations

import argparse
import asyncio
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from rich.console import Console
from rich.table import Table

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import candidate_run_roots, resolve_workflow_db_path
from src.llm.provider import LLMProvider
from src.models import CandidatePaper, ReviewConfig, ReviewType, SettingsConfig
from src.models.config import ScreeningConfig
from src.screening.dual_screener import DualReviewerScreener
from src.screening.gemini_client import PydanticAIScreeningClient

console = Console()


@dataclass(frozen=True)
class ReplayProfile:
    label: str
    exclude_fast_path_requires_dual: bool


@dataclass
class ReplayResult:
    label: str
    papers_used: int
    results_returned: int
    reviewer_a_rows: int
    reviewer_b_rows: int
    parse_degraded_entries: int
    id_mismatch_entries: int
    batch_parse_degraded: int
    batch_id_mismatch: int
    batch_missing_fallback: int
    fast_path_include: int
    fast_path_exclude: int
    cross_reviewed: int
    array_schema_calls: int
    paper_id_enum_present: bool
    paper_id_enum_len: int


class ScriptedBatchClient:
    def __init__(self, id_drift_mode: str) -> None:
        self.id_drift_mode = id_drift_mode
        self.array_schema_calls = 0
        self.last_item_schema: dict[str, Any] | None = None

    @staticmethod
    def _extract_allowed_ids(prompt: str) -> list[str]:
        marker = "Allowed paper_ids:"
        idx = prompt.rfind(marker)
        if idx >= 0:
            tail = prompt[idx + len(marker) :].strip().splitlines()
            if tail:
                first = tail[0]
                ids = [part.strip() for part in first.split(",") if part.strip()]
                if ids:
                    return ids
        ids = re.findall(r"paper_id=([A-Za-z0-9_:-]+)", prompt)
        return ids

    def _build_batch_payload(self, allowed_ids: list[str]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for idx, paper_id in enumerate(allowed_ids, start=1):
            if self.id_drift_mode == "exact_ids":
                item_id = paper_id
            else:
                item_id = f"[{idx}]" if idx % 2 == 1 else f"index_{idx}"
            payload.append(
                {
                    "id": item_id,
                    "decision": "include",
                    "confidence": 0.93,
                    "reasoning": "dry-run include",
                    "exclusion_reason": None,
                }
            )
        return payload

    async def complete_json_array_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
        item_schema: dict[str, Any],
    ) -> tuple[str, int, int, int, int]:
        _ = (prompt, agent_name, model, temperature)
        self.array_schema_calls += 1
        self.last_item_schema = item_schema
        allowed_ids = self._extract_allowed_ids(prompt)
        payload = self._build_batch_payload(allowed_ids)
        return json.dumps(payload), 1800, 1100, 0, 0

    async def complete_json_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[str, int, int, int, int]:
        _ = (prompt, agent_name, model, temperature)
        payload = {
            "decision": "include",
            "confidence": 0.9,
            "reasoning": "dry-run fallback include",
            "exclusion_reason": None,
        }
        return json.dumps(payload), 500, 200, 0, 0

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = (prompt, agent_name, model, temperature)
        payload = {
            "decision": "include",
            "confidence": 0.9,
            "reasoning": "dry-run fallback include",
            "exclusion_reason": None,
        }
        return json.dumps(payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay screening batch logic on real workflow DB papers.")
    parser.add_argument("--workflow-id", required=True, help="Workflow ID to replay (for example: wf-0046).")
    parser.add_argument(
        "--registry-db",
        default="runs/workflows_registry.db",
        help="Path to workflows registry DB used to resolve workflow runtime.db path.",
    )
    parser.add_argument(
        "--db-path",
        default="",
        help="Optional direct runtime.db path (skips registry lookup when provided).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of title/abstract papers to load from runtime DB.",
    )
    parser.add_argument(
        "--id-drift-mode",
        choices=["index_alias", "exact_ids"],
        default="index_alias",
        help="Scripted response ID style. index_alias simulates [1]/index_2 drift.",
    )
    parser.add_argument(
        "--compare-exclude-fastpath",
        action="store_true",
        help="Run both baseline (true) and cost_mode (false) for exclude_fast_path_requires_dual.",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Use real screening client (live Gemini calls). If false, uses scripted responses only.",
    )
    return parser.parse_args()


async def _resolve_runtime_db(workflow_id: str, registry_db: str, db_path_override: str) -> Path:
    if db_path_override.strip():
        return Path(db_path_override).expanduser().resolve()
    run_root = str(Path(registry_db).expanduser().resolve().parent)
    roots = candidate_run_roots(run_root, anchor_file=__file__)
    resolved = await resolve_workflow_db_path(workflow_id, roots)
    if not resolved:
        raise RuntimeError(
            f"Could not resolve db_path for workflow_id={workflow_id} using run roots: {roots}"
        )
    return Path(resolved).expanduser().resolve()


async def _load_title_abstract_sample(runtime_db: Path, workflow_id: str, sample_size: int) -> list[CandidatePaper]:
    query = """
        SELECT p.paper_id, p.title, p.abstract, p.authors, p.source_database
        FROM papers p
        JOIN screening_decisions sd
          ON sd.paper_id = p.paper_id
        WHERE sd.workflow_id = ?
          AND sd.stage = 'title_abstract'
          AND sd.reviewer_type = 'reviewer_a'
          AND p.abstract IS NOT NULL
          AND length(trim(p.abstract)) >= 80
        GROUP BY p.paper_id
        LIMIT ?
    """
    papers: list[CandidatePaper] = []
    async with aiosqlite.connect(str(runtime_db)) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(query, (workflow_id, sample_size))).fetchall()
    for row in rows:
        authors: list[str] = []
        raw_authors = row["authors"]
        if raw_authors:
            try:
                parsed = json.loads(str(raw_authors))
                if isinstance(parsed, list):
                    authors = [str(item) for item in parsed if item]
            except Exception:
                authors = [str(raw_authors)]
        papers.append(
            CandidatePaper(
                paper_id=str(row["paper_id"]),
                title=str(row["title"] or ""),
                abstract=str(row["abstract"] or ""),
                authors=authors or ["Unknown"],
                source_database=str(row["source_database"] or "openalex"),
            )
        )
    return papers


def _build_review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Local DB screening replay for cost and fallback diagnostics",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "health science students",
            "intervention": "generative ai tutoring",
            "comparison": "non generative or traditional tutoring",
            "outcome": "efficacy, user experience, implementation",
        },
        keywords=["generative ai", "tutoring", "health education"],
        domain="health education",
        scope="local replay",
        inclusion_criteria=["topic relevance"],
        exclusion_criteria=["out of scope"],
        date_range_start=2000,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _build_settings(exclude_fast_path_requires_dual: bool) -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_adjudicator": {"model": "google-gla:gemini-2.5-flash-lite", "temperature": 0.2},
        },
        screening=ScreeningConfig(
            reviewer_batch_size=10,
            insufficient_content_min_words=0,
            exclude_fast_path_requires_dual=exclude_fast_path_requires_dual,
        ),
    )


async def _run_profile(
    profile: ReplayProfile,
    papers: list[CandidatePaper],
    id_drift_mode: str,
    use_live_llm: bool,
) -> ReplayResult:
    client: ScriptedBatchClient | None = None
    if not use_live_llm:
        client = ScriptedBatchClient(id_drift_mode=id_drift_mode)
    settings = _build_settings(profile.exclude_fast_path_requires_dual)
    with tempfile.TemporaryDirectory() as tmp_dir:
        async with get_db(str(Path(tmp_dir) / "replay.db")) as db:
            repo = WorkflowRepository(db)
            wf_id = f"wf-replay-{profile.label}"
            await repo.create_workflow(wf_id, "screening replay", "replay-hash")
            provider = LLMProvider(settings, repo)
            screener = DualReviewerScreener(
                repository=repo,
                provider=provider,
                review=_build_review(),
                settings=settings,
                llm_client=(client if client is not None else PydanticAIScreeningClient()),
            )
            results = await screener.screen_batch(
                workflow_id=wf_id,
                stage="title_abstract",
                papers=papers,
            )
            parse_degraded_entries = int(
                (
                    await (
                        await db.execute(
                            "SELECT COUNT(*) FROM decision_log WHERE decision_type='screening_batch_parse_coverage'"
                        )
                    ).fetchone()
                )[0]
            )
            id_mismatch_entries = int(
                (
                    await (
                        await db.execute(
                            "SELECT COUNT(*) FROM decision_log WHERE decision_type='screening_batch_id_mismatch'"
                        )
                    ).fetchone()
                )[0]
            )
            reviewer_a_rows = int(
                (
                    await (
                        await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE reviewer_type='reviewer_a'")
                    ).fetchone()
                )[0]
            )
            reviewer_b_rows = int(
                (
                    await (
                        await db.execute("SELECT COUNT(*) FROM screening_decisions WHERE reviewer_type='reviewer_b'")
                    ).fetchone()
                )[0]
            )
            array_schema_calls = client.array_schema_calls if client else 0
            has_enum = False
            enum_len = 0
            if client and client.last_item_schema:
                props = client.last_item_schema.get("properties", {})
                if isinstance(props, dict):
                    paper_id_schema = props.get("paper_id")
                    if isinstance(paper_id_schema, dict):
                        enum_values = paper_id_schema.get("enum")
                        if isinstance(enum_values, list):
                            has_enum = True
                            enum_len = len(enum_values)
            return ReplayResult(
                label=profile.label,
                papers_used=len(papers),
                results_returned=len(results),
                reviewer_a_rows=reviewer_a_rows,
                reviewer_b_rows=reviewer_b_rows,
                parse_degraded_entries=parse_degraded_entries,
                id_mismatch_entries=id_mismatch_entries,
                batch_parse_degraded=getattr(screener, "batch_parse_degraded_count", 0),
                batch_id_mismatch=getattr(screener, "batch_id_mismatch_count", 0),
                batch_missing_fallback=getattr(screener, "batch_missing_fallback_count", 0),
                fast_path_include=getattr(screener, "fast_path_include_count", 0),
                fast_path_exclude=getattr(screener, "fast_path_exclude_count", 0),
                cross_reviewed=getattr(screener, "cross_review_count", 0),
                array_schema_calls=array_schema_calls,
                paper_id_enum_present=has_enum,
                paper_id_enum_len=enum_len,
            )


def _print_results(runtime_db: Path, workflow_id: str, results: list[ReplayResult], live_llm: bool) -> None:
    console.print(f"Runtime DB: {runtime_db}")
    console.print(f"Workflow: {workflow_id}")
    console.print(f"Mode: {'live_llm' if live_llm else 'scripted'}")
    table = Table(title="Screening Replay Diagnostics")
    table.add_column("profile")
    table.add_column("papers")
    table.add_column("results")
    table.add_column("A_rows")
    table.add_column("B_rows")
    table.add_column("parse_degraded")
    table.add_column("id_mismatch")
    table.add_column("missing_fallback")
    table.add_column("fast_include")
    table.add_column("fast_exclude")
    table.add_column("cross_reviewed")
    table.add_column("schema_enum")
    for item in results:
        table.add_row(
            item.label,
            str(item.papers_used),
            str(item.results_returned),
            str(item.reviewer_a_rows),
            str(item.reviewer_b_rows),
            str(item.batch_parse_degraded),
            str(item.batch_id_mismatch),
            str(item.batch_missing_fallback),
            str(item.fast_path_include),
            str(item.fast_path_exclude),
            str(item.cross_reviewed),
            f"{item.paper_id_enum_present}:{item.paper_id_enum_len}",
        )
    console.print(table)


async def _run() -> None:
    args = _parse_args()
    runtime_db = await _resolve_runtime_db(args.workflow_id, args.registry_db, args.db_path)
    if not runtime_db.exists():
        raise FileNotFoundError(f"runtime.db not found: {runtime_db}")
    papers = await _load_title_abstract_sample(runtime_db, args.workflow_id, args.sample_size)
    if len(papers) < 5:
        raise RuntimeError(f"Not enough papers for replay (loaded {len(papers)}). Increase sample or change workflow.")
    profiles = [ReplayProfile(label="baseline", exclude_fast_path_requires_dual=True)]
    if args.compare_exclude_fastpath:
        profiles.append(ReplayProfile(label="cost_mode", exclude_fast_path_requires_dual=False))
    results: list[ReplayResult] = []
    for profile in profiles:
        results.append(
            await _run_profile(
                profile=profile,
                papers=papers,
                id_drift_mode=args.id_drift_mode,
                use_live_llm=args.live_llm,
            )
        )
    _print_results(runtime_db, args.workflow_id, results, args.live_llm)


if __name__ == "__main__":
    asyncio.run(_run())
