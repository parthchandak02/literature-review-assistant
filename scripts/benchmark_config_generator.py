"""Benchmark config generation across 10 cross-domain topics.

Modes:
- direct: call generate_config_yaml() in-process
- api: call /api/config/generate/stream and parse SSE payloads
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from rich.console import Console
from rich.table import Table

from src.web.config_generator import evaluate_config_quality_yaml, generate_config_yaml

console = Console()

QUALITY_REQUIRED_KEYS = ("total", "keyword_quality", "database_relevance", "override_complexity")
_MIXED_TOPIC_MARKERS = {
    "ux",
    "user experience",
    "usability",
    "prototype",
    "prototyping",
    "engineering",
    "human-ai",
    "dashboard",
    "workflow",
}
_STRONG_BIOMEDICAL_MARKERS = {
    "medication",
    "clinical",
    "hospital",
    "patient",
    "nursing",
    "therapy",
    "treatment",
    "disease",
    "pharmacy",
    "adherence",
}
TOPICS = [
    "How do trust-aware social robots in outpatient waiting rooms affect patient trust, satisfaction, and clinic throughput?",
    "What is the impact of no-code configurable nursing workflow robots on nurse workload, task completion time, and error rates?",
    "How effective are voice-first care coordination interfaces for older adults with low digital literacy in improving medication adherence and appointment completion?",
    "What is the impact of integrated hybrid care UX journeys (chatbot to telehealth to in-person) on patient drop-off and continuity of care?",
    "How do wearable-to-clinician dashboard systems influence early intervention rates and alarm fatigue in chronic disease monitoring?",
    "What is the effect of adaptive VR or AR rehabilitation interfaces on adherence, fatigue, and functional recovery outcomes?",
    "How do micro-interaction design patterns in digital therapeutics apps affect long-term engagement and treatment adherence?",
    "What is the impact of human-AI shared decision support interfaces with uncertainty display on clinician confidence and decision quality?",
    "How effective are community pharmacy service robots for patient education, refill support, and dispensing workflow efficiency?",
    "What co-creation frameworks best improve adoption, usability, and safety outcomes in healthcare robotics pilot deployments?",
]


@dataclass
class BenchmarkRecord:
    topic: str
    ok: bool
    error: str | None
    route_domain: str | None
    route_policy: str | None
    route_confidence: float | None
    target_databases: list[str]
    keyword_count: int
    unique_keyword_roots: int
    one_char_keyword_count: int
    brand_like_keyword_ratio: float
    quality: dict[str, Any]


@dataclass
class GateThresholds:
    min_total: float
    min_keyword_quality: float
    min_database_relevance: float
    min_override_complexity: float
    min_unique_keyword_roots: int
    max_brand_like_keyword_ratio: float


def _parse_yaml_metrics(yaml_text: str) -> tuple[list[str], int]:
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except Exception:
        return [], 0
    if not isinstance(raw, dict):
        return [], 0
    dbs_raw = raw.get("target_databases") or []
    kw_raw = raw.get("keywords") or []
    dbs = [str(x) for x in dbs_raw if x]
    return dbs, len(list(kw_raw))


def _parse_yaml_keywords(yaml_text: str) -> list[str]:
    try:
        raw = yaml.safe_load(yaml_text) or {}
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    return [str(x).strip() for x in (raw.get("keywords") or []) if str(x).strip()]


def _keyword_quality_signals(keywords: list[str]) -> tuple[int, float, int]:
    if not keywords:
        return 0, 0.0, 0
    one_char_count = 0
    brand_like_count = 0
    roots: set[str] = set()
    for kw in keywords:
        parts = [p for p in re.split(r"[^A-Za-z0-9]+", kw) if p]
        lower_parts = [p.lower() for p in parts]
        if parts and all(len(p) < 2 for p in parts):
            one_char_count += 1
        is_brand_like = False
        for part in parts:
            if any(ch.isdigit() for ch in part):
                is_brand_like = True
                break
            if len(part) >= 2 and part.isupper():
                is_brand_like = True
                break
        if not is_brand_like and re.search(r"[A-Z][a-z]+[A-Z]", kw):
            is_brand_like = True
        if is_brand_like:
            brand_like_count += 1
        for p in lower_parts:
            if len(p) >= 4:
                roots.add(p)
    return one_char_count, (brand_like_count / len(keywords)), len(roots)


def _load_topics(topics_file: str) -> list[str]:
    if not topics_file:
        return list(TOPICS)
    path = Path(topics_file)
    if not path.exists():
        raise ValueError(f"topics file not found: {topics_file}")
    if path.suffix.lower() in {".yml", ".yaml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if isinstance(raw, dict):
        topics_raw = raw.get("topics")
    else:
        topics_raw = raw
    if not isinstance(topics_raw, list):
        raise ValueError("topics file must contain a list or a dict with key 'topics'")
    topics = [str(t).strip() for t in topics_raw if str(t).strip()]
    if not topics:
        raise ValueError("topics list is empty")
    return topics


async def _run_direct_topic(topic: str) -> BenchmarkRecord:
    progress: list[dict[str, Any]] = []

    def _cb(payload: dict[str, Any]) -> None:
        progress.append(dict(payload))

    try:
        yaml_text = await generate_config_yaml(topic, progress_cb=_cb)
        quality = evaluate_config_quality_yaml(yaml_text)
        dbs, keyword_count = _parse_yaml_metrics(yaml_text)
        keywords = _parse_yaml_keywords(yaml_text)
        one_char_count, brand_ratio, unique_roots = _keyword_quality_signals(keywords)
        route = next((p for p in progress if p.get("step") == "topic_routing"), {})
        return BenchmarkRecord(
            topic=topic,
            ok=True,
            error=None,
            route_domain=route.get("domain"),
            route_policy=route.get("policy"),
            route_confidence=route.get("confidence"),
            target_databases=dbs,
            keyword_count=keyword_count,
            unique_keyword_roots=unique_roots,
            one_char_keyword_count=one_char_count,
            brand_like_keyword_ratio=brand_ratio,
            quality=quality,
        )
    except Exception as exc:
        return BenchmarkRecord(
            topic=topic,
            ok=False,
            error=str(exc),
            route_domain=None,
            route_policy=None,
            route_confidence=None,
            target_databases=[],
            keyword_count=0,
            unique_keyword_roots=0,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.0,
            quality={},
        )


def _parse_sse_payloads(text: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
    progress: list[dict[str, Any]] = []
    done: dict[str, Any] | None = None
    error: str | None = None
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except Exception:
            continue
        p_type = payload.get("type")
        if p_type == "progress":
            progress.append(payload)
        elif p_type == "done":
            done = payload
        elif p_type == "error":
            error = str(payload.get("detail") or "unknown_error")
    return progress, done, error


def _run_api_topic(
    topic: str,
    base_url: str,
    timeout_s: float,
    gemini_api_key: str,
) -> BenchmarkRecord:
    endpoint = f"{base_url.rstrip('/')}/api/config/generate/stream"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(
                endpoint,
                json={"research_question": topic, "gemini_api_key": gemini_api_key},
            )
        if resp.status_code != 200:
            return BenchmarkRecord(
                topic=topic,
                ok=False,
                error=f"http_{resp.status_code}",
                route_domain=None,
                route_policy=None,
                route_confidence=None,
                target_databases=[],
                keyword_count=0,
                unique_keyword_roots=0,
                one_char_keyword_count=0,
                brand_like_keyword_ratio=0.0,
                quality={},
            )
        progress, done, error = _parse_sse_payloads(resp.text)
        if error is not None:
            return BenchmarkRecord(
                topic=topic,
                ok=False,
                error=error,
                route_domain=None,
                route_policy=None,
                route_confidence=None,
                target_databases=[],
                keyword_count=0,
                unique_keyword_roots=0,
                one_char_keyword_count=0,
                brand_like_keyword_ratio=0.0,
                quality={},
            )
        if done is None:
            return BenchmarkRecord(
                topic=topic,
                ok=False,
                error="missing_done",
                route_domain=None,
                route_policy=None,
                route_confidence=None,
                target_databases=[],
                keyword_count=0,
                unique_keyword_roots=0,
                one_char_keyword_count=0,
                brand_like_keyword_ratio=0.0,
                quality={},
            )
        yaml_text = str(done.get("yaml") or "")
        quality = done.get("quality") if isinstance(done.get("quality"), dict) else {}
        dbs, keyword_count = _parse_yaml_metrics(yaml_text)
        keywords = _parse_yaml_keywords(yaml_text)
        one_char_count, brand_ratio, unique_roots = _keyword_quality_signals(keywords)
        route = next((p for p in progress if p.get("step") == "topic_routing"), {})
        return BenchmarkRecord(
            topic=topic,
            ok=True,
            error=None,
            route_domain=route.get("domain"),
            route_policy=route.get("policy"),
            route_confidence=route.get("confidence"),
            target_databases=dbs,
            keyword_count=keyword_count,
            unique_keyword_roots=unique_roots,
            one_char_keyword_count=one_char_count,
            brand_like_keyword_ratio=brand_ratio,
            quality=quality,
        )
    except Exception as exc:
        return BenchmarkRecord(
            topic=topic,
            ok=False,
            error=str(exc),
            route_domain=None,
            route_policy=None,
            route_confidence=None,
            target_databases=[],
            keyword_count=0,
            unique_keyword_roots=0,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.0,
            quality={},
        )


def evaluate_gates(records: list[BenchmarkRecord], mode: str, thresholds: GateThresholds) -> dict[str, Any]:
    failures = [r for r in records if not r.ok]
    generic_policy_leaks: list[BenchmarkRecord] = []
    missing_quality: list[BenchmarkRecord] = []
    below_total: list[BenchmarkRecord] = []
    below_keyword_quality: list[BenchmarkRecord] = []
    below_database_relevance: list[BenchmarkRecord] = []
    below_override_complexity: list[BenchmarkRecord] = []
    low_diversity: list[BenchmarkRecord] = []
    one_char_keyword_failures: list[BenchmarkRecord] = []
    brand_ratio_failures: list[BenchmarkRecord] = []
    mixed_topic_bio_failures: list[BenchmarkRecord] = []

    for rec in records:
        if not rec.ok:
            continue
        policy = rec.route_policy or str(rec.quality.get("route_policy") or "")
        dbs = set(rec.target_databases)
        if policy == "high_confidence_generic" and ("pubmed" in dbs or "clinicaltrials_gov" in dbs):
            generic_policy_leaks.append(rec)
        topic_text = rec.topic.lower()
        has_mixed_markers = any(marker in topic_text for marker in _MIXED_TOPIC_MARKERS)
        has_strong_bio_markers = any(marker in topic_text for marker in _STRONG_BIOMEDICAL_MARKERS)
        if has_mixed_markers and (not has_strong_bio_markers) and policy == "high_confidence_biomedical":
            mixed_topic_bio_failures.append(rec)
        if rec.one_char_keyword_count > 0:
            one_char_keyword_failures.append(rec)
        if rec.unique_keyword_roots < thresholds.min_unique_keyword_roots:
            low_diversity.append(rec)
        if rec.brand_like_keyword_ratio > thresholds.max_brand_like_keyword_ratio:
            brand_ratio_failures.append(rec)
        if mode == "api":
            if any(key not in rec.quality for key in QUALITY_REQUIRED_KEYS):
                missing_quality.append(rec)
        if rec.quality:
            total = float(rec.quality.get("total", 0.0))
            keyword_quality = float(rec.quality.get("keyword_quality", 0.0))
            database_relevance = float(rec.quality.get("database_relevance", 0.0))
            override_complexity = float(rec.quality.get("override_complexity", 0.0))
            if total < thresholds.min_total:
                below_total.append(rec)
            if keyword_quality < thresholds.min_keyword_quality:
                below_keyword_quality.append(rec)
            if database_relevance < thresholds.min_database_relevance:
                below_database_relevance.append(rec)
            if override_complexity < thresholds.min_override_complexity:
                below_override_complexity.append(rec)

    gate_ok = (
        not failures
        and not generic_policy_leaks
        and not missing_quality
        and not below_total
        and not below_keyword_quality
        and not below_database_relevance
        and not below_override_complexity
        and not low_diversity
        and not one_char_keyword_failures
        and not brand_ratio_failures
    )
    return {
        "gate_ok": gate_ok,
        "failure_count": len(failures),
        "generic_policy_db_leak_count": len(generic_policy_leaks),
        "missing_quality_count": len(missing_quality),
        "below_total_count": len(below_total),
        "below_keyword_quality_count": len(below_keyword_quality),
        "below_database_relevance_count": len(below_database_relevance),
        "below_override_complexity_count": len(below_override_complexity),
        "low_diversity_count": len(low_diversity),
        "one_char_keyword_failure_count": len(one_char_keyword_failures),
        "brand_ratio_failure_count": len(brand_ratio_failures),
        "mixed_topic_bio_failure_count": len(mixed_topic_bio_failures),
        "thresholds": asdict(thresholds),
        "failures": [asdict(r) for r in failures],
        "generic_policy_leaks": [asdict(r) for r in generic_policy_leaks],
        "missing_quality": [asdict(r) for r in missing_quality],
        "below_total": [asdict(r) for r in below_total],
        "below_keyword_quality": [asdict(r) for r in below_keyword_quality],
        "below_database_relevance": [asdict(r) for r in below_database_relevance],
        "below_override_complexity": [asdict(r) for r in below_override_complexity],
        "low_diversity": [asdict(r) for r in low_diversity],
        "one_char_keyword_failures": [asdict(r) for r in one_char_keyword_failures],
        "brand_ratio_failures": [asdict(r) for r in brand_ratio_failures],
        "mixed_topic_bio_failures": [asdict(r) for r in mixed_topic_bio_failures],
    }


def _print_summary(records: list[BenchmarkRecord], gate: dict[str, Any]) -> None:
    table = Table(title="Config Generation Benchmark")
    table.add_column("Topic #", justify="right")
    table.add_column("Status")
    table.add_column("Route policy")
    table.add_column("DB count", justify="right")
    table.add_column("Keywords", justify="right")
    table.add_column("Roots", justify="right")
    table.add_column("Brand ratio", justify="right")
    table.add_column("Score", justify="right")
    for idx, rec in enumerate(records, 1):
        status = "ok" if rec.ok else "fail"
        score = rec.quality.get("total") if rec.quality else None
        table.add_row(
            str(idx),
            status,
            rec.route_policy or "-",
            str(len(rec.target_databases)),
            str(rec.keyword_count),
            str(rec.unique_keyword_roots),
            f"{rec.brand_like_keyword_ratio:.2f}",
            f"{score}" if score is not None else "-",
        )
    console.print(table)
    console.print(
        f"gate_ok={gate['gate_ok']} "
        f"failures={gate['failure_count']} "
        f"generic_db_leaks={gate['generic_policy_db_leak_count']} "
        f"missing_quality={gate['missing_quality_count']} "
        f"below_total={gate['below_total_count']} "
        f"below_keyword_quality={gate['below_keyword_quality_count']} "
        f"below_database_relevance={gate['below_database_relevance_count']} "
        f"below_override_complexity={gate['below_override_complexity_count']} "
        f"low_diversity={gate['low_diversity_count']} "
        f"one_char_keyword_failures={gate['one_char_keyword_failure_count']} "
        f"brand_ratio_failures={gate['brand_ratio_failure_count']} "
        f"mixed_topic_bio_failures={gate['mixed_topic_bio_failure_count']}"
    )


def _to_json(records: list[BenchmarkRecord], gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "records": [asdict(r) for r in records],
        "gate": gate,
    }


async def _run_direct(topics: list[str], attempts: int) -> list[BenchmarkRecord]:
    out: list[BenchmarkRecord] = []
    for topic in topics:
        rec = await _run_direct_topic(topic)
        tries = 1
        while (not rec.ok) and tries < attempts:
            tries += 1
            rec = await _run_direct_topic(topic)
        out.append(rec)
    return out


def _run_api(
    topics: list[str],
    base_url: str,
    timeout_s: float,
    gemini_api_key: str,
    attempts: int,
) -> list[BenchmarkRecord]:
    out: list[BenchmarkRecord] = []
    for topic in topics:
        rec = _run_api_topic(topic, base_url, timeout_s, gemini_api_key)
        tries = 1
        while (not rec.ok) and tries < attempts:
            tries += 1
            rec = _run_api_topic(topic, base_url, timeout_s, gemini_api_key)
        out.append(rec)
    return out


def _wait_for_api_ready(base_url: str, timeout_s: float) -> bool:
    endpoint = f"{base_url.rstrip('/')}/api/health"
    attempts = 12
    wait_s = max(1.0, min(5.0, timeout_s / 30.0))
    for _ in range(attempts):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(endpoint)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        import time

        time.sleep(wait_s)
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark config generation on 10 topics.")
    parser.add_argument("--mode", choices=("direct", "api"), default="direct")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--gemini-api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    parser.add_argument("--out-json", default="")
    parser.add_argument("--topics-file", default="")
    parser.add_argument("--min-total", type=float, default=80.0)
    parser.add_argument("--min-keyword-quality", type=float, default=70.0)
    parser.add_argument("--min-database-relevance", type=float, default=70.0)
    parser.add_argument("--min-override-complexity", type=float, default=65.0)
    parser.add_argument("--min-unique-keyword-roots", type=int, default=14)
    parser.add_argument("--max-brand-like-keyword-ratio", type=float, default=0.35)
    parser.add_argument("--attempts", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        topics = _load_topics(args.topics_file)
    except Exception as exc:
        console.print(f"invalid topics input: {exc}")
        return 2
    if args.mode == "direct" and not args.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
        console.print("direct mode requires GEMINI_API_KEY in env or --gemini-api-key")
        return 2
    thresholds = GateThresholds(
        min_total=args.min_total,
        min_keyword_quality=args.min_keyword_quality,
        min_database_relevance=args.min_database_relevance,
        min_override_complexity=args.min_override_complexity,
        min_unique_keyword_roots=int(args.min_unique_keyword_roots),
        max_brand_like_keyword_ratio=args.max_brand_like_keyword_ratio,
    )

    attempts = max(1, int(args.attempts))
    if args.mode == "direct":
        records = asyncio.run(_run_direct(topics, attempts))
    else:
        if not _wait_for_api_ready(args.base_url, args.timeout_s):
            console.print("api mode could not reach /api/health after retries")
            return 2
        records = _run_api(topics, args.base_url, args.timeout_s, args.gemini_api_key, attempts)

    gate = evaluate_gates(records, args.mode, thresholds)
    _print_summary(records, gate)
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(_to_json(records, gate), indent=2), encoding="utf-8")
    return 0 if gate["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
