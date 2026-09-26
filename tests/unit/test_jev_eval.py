from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.lib import check_jev_eval as ev

_SCHEMA = """
CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT NOT NULL, authors TEXT NOT NULL, year INTEGER,
    source_database TEXT NOT NULL, doi TEXT, abstract TEXT);
CREATE TABLE screening_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL, stage TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT, exclusion_reason TEXT,
    reviewer_type TEXT NOT NULL, confidence REAL NOT NULL);
CREATE TABLE dual_screening_results (workflow_id TEXT NOT NULL, paper_id TEXT NOT NULL, stage TEXT NOT NULL,
    agreement INTEGER NOT NULL, final_decision TEXT NOT NULL, adjudication_needed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE study_cohort_membership (workflow_id TEXT NOT NULL, paper_id TEXT NOT NULL,
    synthesis_eligibility TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE cost_records (id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL, tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL, cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL, phase TEXT NOT NULL);
CREATE TABLE jev_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL, phase TEXT NOT NULL,
    surface TEXT NOT NULL, paper_id TEXT, choice TEXT, confidence REAL, routed TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}');
"""

# paper_id, llm_b, jev_choice, jev_conf, final_ta, included_primary, latency
_ROWS = [
    ("p1", "include", "INCLUDE", 0.95, "include", True, 150),
    ("p2", "include", "EXCLUDE", 0.90, "include", False, 200),
    ("p3", "exclude", "EXCLUDE", 0.99, "exclude", False, 120),
    ("p4", "exclude", "INCLUDE", 0.70, "exclude", False, 180),
    ("p5", "exclude", "EXCLUDE", 0.80, "exclude", False, 160),
    ("p6", "include", "UNCERTAIN", 0.60, "include", True, 300),
]


def _build_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    for pid, llm_b, choice, conf, final, included, latency in _ROWS:
        conn.execute(
            "INSERT INTO papers VALUES (?, ?, '[]', 2024, 'openalex', NULL, 'abstract text')", (pid, f"Title {pid}")
        )
        conn.execute(
            "INSERT INTO screening_decisions (workflow_id, paper_id, stage, decision, reason, reviewer_type, confidence)"
            " VALUES ('wf', ?, 'title_abstract', ?, 'llm', 'reviewer_b', 0.8)",
            (pid, llm_b),
        )
        conn.execute(
            "INSERT INTO dual_screening_results VALUES ('wf', ?, 'title_abstract', 1, ?, 0)", (pid, final)
        )
        conn.execute(
            "INSERT INTO study_cohort_membership VALUES ('wf', ?, ?)",
            (pid, "included_primary" if included else "excluded_screening"),
        )
        details = {"mode": "shadow", "latency_ms": latency, "cost_usd": 0.001, "llm_decision": llm_b}
        conn.execute(
            "INSERT INTO jev_decisions (workflow_id, phase, surface, paper_id, choice, confidence, routed, details_json)"
            " VALUES ('wf', 'phase_3_screening', 'screening_reviewer_b', ?, ?, ?, 'shadow', ?)",
            (pid, choice, conf, json.dumps(details)),
        )
    conn.execute(
        "INSERT INTO jev_decisions (workflow_id, phase, surface, paper_id, choice, confidence, routed, details_json)"
        " VALUES ('wf', 'phase_3_screening', 'screening_reviewer_b', 'p7', '', 0, 'shadow_error', ?)",
        (json.dumps({"mode": "shadow", "reason": "error:TimeoutError"}),),
    )
    conn.execute(
        "INSERT INTO jev_decisions (workflow_id, phase, surface, paper_id, choice, confidence, routed, details_json)"
        " VALUES ('wf', 'phase_6_rerank', 'rag_rerank', NULL, 'score_rank', 1.0, 'shadow', ?)",
        (json.dumps({"mode": "shadow", "latency_ms": 400, "cost_usd": 0.002, "overlap_at_k": 0.75}),),
    )
    conn.execute(
        "INSERT INTO cost_records (workflow_id, model, tokens_in, tokens_out, cost_usd, latency_ms, phase)"
        " VALUES ('wf', 'jev-1.13.0', 300, 40, 0.001, 150, 'jev_shadow_phase_3_screening')"
    )
    conn.commit()
    conn.close()
    return path


def test_kappa_and_binary_metrics() -> None:
    assert ev.cohen_kappa([(True, True), (False, False)]) == 1.0
    assert ev.cohen_kappa([(True, False), (False, True)]) == pytest.approx(-1.0)
    m = ev.binary_metrics([True, False, True, None], [True, True, False, True])
    assert (m["n"], m["tp"], m["fn"], m["fp"]) == (3, 1, 1, 1)
    assert m["recall_include"] == 0.5
    assert m["precision_include"] == 0.5


def test_evaluate_synthetic_db(tmp_path) -> None:
    report = ev.evaluate_db(_build_db(tmp_path / "runtime.db"))
    s = report["screening"]
    assert s["n_rows"] == 7
    assert s["n_jev_answers"] == 6
    assert s["n_jev_errors"] == 1
    # Jev include-like: p1, p4, p6. Final TA includes: p1, p2, p6.
    fin = s["jev_vs_final_ta"]
    assert (fin["tp"], fin["fp"], fin["fn"], fin["tn"]) == (2, 1, 1, 2)
    assert fin["recall_include"] == pytest.approx(0.6667)
    assert fin["kappa"] == pytest.approx(0.3333)
    assert s["llm_b_vs_final_ta"]["agreement"] == 1.0
    assert s["jev_vs_final_included"]["recall_include"] == 1.0
    assert s["jev_vs_llm_b_3class_agreement"] == pytest.approx(0.5)
    live = s["live_routing_at_current_thresholds"]
    # route 0.6 / exclude 0.85 -> p1, p2, p3, p4, p6 routed; p5 (exclude 0.80) escalates.
    assert live["coverage"] == pytest.approx(0.8333)
    sweep = {t["exclude_threshold"]: t for t in s["exclude_threshold_sweep"]}
    assert sweep[0.85]["false_excludes"] == 1
    assert sweep[0.95]["false_excludes"] == 0
    assert s["jev_latency"]["p50_ms"] == 170
    assert s["jev_cost_usd"] == pytest.approx(0.006)
    assert report["surfaces"]["rag_rerank"]["mean_overlap_at_k"] == 0.75
    assert any(c["phase"] == "jev_shadow_phase_3_screening" for c in report["cost_records"])
    assert "jev_vs_final_ta" in ev._format_text(report)


def test_live_sample_refuses_without_confirm(tmp_path, capsys) -> None:
    db = _build_db(tmp_path / "runtime.db")
    assert ev.main(["--db", str(db), "--live-sample", "5"]) == 2
    assert "Refusing live sample" in capsys.readouterr().err


def test_live_sample_selection_prefers_includes(tmp_path) -> None:
    conn = ev.open_readonly(_build_db(tmp_path / "runtime.db"))
    try:
        picked = ev.select_live_sample(conn, 4)
    finally:
        conn.close()
    assert len(picked) == 4
    assert {"p1", "p2", "p6"} & set(picked)


def test_offline_cli_prints_report(tmp_path, capsys) -> None:
    db = _build_db(tmp_path / "runtime.db")
    assert ev.main(["--db", str(db)]) == 0
    assert "jev_vs_llm_b" in capsys.readouterr().out
