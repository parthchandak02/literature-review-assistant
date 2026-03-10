from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_module():
    script_path = Path("/Users/parthchandak/projects/literature-review-assistant/scripts/benchmark_config_generator.py")
    spec = importlib.util.spec_from_file_location("benchmark_config_generator", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_yaml_metrics_extracts_databases_and_keyword_count() -> None:
    mod = _load_module()
    yaml_text = """
research_question: "x"
keywords:
  - "a"
  - "b"
target_databases:
  - openalex
  - scopus
"""
    dbs, kw_count = mod._parse_yaml_metrics(yaml_text)
    assert dbs == ["openalex", "scopus"]
    assert kw_count == 2


def test_evaluate_gates_flags_generic_policy_database_leak() -> None:
    mod = _load_module()
    thresholds = mod.GateThresholds(50.0, 50.0, 50.0, 50.0, 1, 1.0)
    records = [
        mod.BenchmarkRecord(
            topic="t1",
            ok=True,
            error=None,
            route_domain="generic",
            route_policy="high_confidence_generic",
            route_confidence=0.9,
            target_databases=["openalex", "pubmed"],
            keyword_count=18,
            unique_keyword_roots=12,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.1,
            quality={"total": 80.0, "keyword_quality": 81.0, "database_relevance": 70.0, "override_complexity": 75.0},
        )
    ]
    gate = mod.evaluate_gates(records, "direct", thresholds)
    assert gate["gate_ok"] is False
    assert gate["generic_policy_db_leak_count"] == 1


def test_evaluate_gates_flags_missing_quality_in_api_mode() -> None:
    mod = _load_module()
    thresholds = mod.GateThresholds(50.0, 50.0, 50.0, 50.0, 1, 1.0)
    records = [
        mod.BenchmarkRecord(
            topic="t2",
            ok=True,
            error=None,
            route_domain="ambiguous",
            route_policy="low_confidence_fallback",
            route_confidence=0.2,
            target_databases=["openalex", "scopus"],
            keyword_count=19,
            unique_keyword_roots=12,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.1,
            quality={"total": 70.0},
        )
    ]
    gate = mod.evaluate_gates(records, "api", thresholds)
    assert gate["gate_ok"] is False
    assert gate["missing_quality_count"] == 1


def test_to_json_contains_expected_schema_keys() -> None:
    mod = _load_module()
    thresholds = mod.GateThresholds(50.0, 50.0, 50.0, 50.0, 1, 1.0)
    records = [
        mod.BenchmarkRecord(
            topic="t3",
            ok=False,
            error="timeout",
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
    ]
    gate = mod.evaluate_gates(records, "direct", thresholds)
    payload = mod._to_json(records, gate)
    assert set(payload.keys()) == {"records", "gate"}
    assert isinstance(payload["records"], list)
    assert isinstance(payload["gate"], dict)
    assert payload["records"][0]["topic"] == "t3"


def test_load_topics_from_json_file() -> None:
    mod = _load_module()
    topics_path = Path("/tmp/config_topics_test.json")
    topics_path.write_text(json.dumps({"topics": ["topic a", "topic b"]}), encoding="utf-8")
    topics = mod._load_topics(str(topics_path))
    assert topics == ["topic a", "topic b"]


def test_evaluate_gates_flags_below_threshold_total() -> None:
    mod = _load_module()
    thresholds = mod.GateThresholds(90.0, 50.0, 50.0, 50.0, 1, 1.0)
    records = [
        mod.BenchmarkRecord(
            topic="t4",
            ok=True,
            error=None,
            route_domain="biomedical",
            route_policy="high_confidence_biomedical",
            route_confidence=1.0,
            target_databases=["openalex", "scopus", "pubmed"],
            keyword_count=20,
            unique_keyword_roots=12,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.1,
            quality={"total": 80.0, "keyword_quality": 80.0, "database_relevance": 85.0, "override_complexity": 90.0},
        )
    ]
    gate = mod.evaluate_gates(records, "direct", thresholds)
    assert gate["gate_ok"] is False
    assert gate["below_total_count"] == 1


def test_keyword_quality_signals_detect_one_char_and_brand_ratio() -> None:
    mod = _load_module()
    one_char_count, ratio, roots = mod._keyword_quality_signals(
        ["n", "VR", "UiPath", "patient trust", "throughput"]
    )
    assert one_char_count == 1
    assert ratio > 0.0
    assert roots >= 2


def test_evaluate_gates_flags_low_keyword_diversity() -> None:
    mod = _load_module()
    thresholds = mod.GateThresholds(50.0, 50.0, 50.0, 50.0, 15, 1.0)
    records = [
        mod.BenchmarkRecord(
            topic="t5",
            ok=True,
            error=None,
            route_domain="generic",
            route_policy="high_confidence_generic",
            route_confidence=0.9,
            target_databases=["openalex", "scopus"],
            keyword_count=20,
            unique_keyword_roots=8,
            one_char_keyword_count=0,
            brand_like_keyword_ratio=0.1,
            quality={"total": 90.0, "keyword_quality": 85.0, "database_relevance": 90.0, "override_complexity": 85.0},
        )
    ]
    gate = mod.evaluate_gates(records, "direct", thresholds)
    assert gate["gate_ok"] is False
    assert gate["low_diversity_count"] == 1
