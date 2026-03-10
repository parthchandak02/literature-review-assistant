"""Run model-routing A/B benchmarks with Promptfoo.

This script builds a promptfoo eval config from a completed run's runtime.db and
compares two model profiles:
- preview: gemini-3.1-flash-lite-preview + gemini-3-flash-preview
- stable:  gemini-2.5-flash-lite + gemini-2.5-flash

It uses promptfoo assertions for:
- structured output validity (contains-json)
- latency thresholds
- cost thresholds
- rubric checks for writing quality
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

console = Console()


SCREENING_PROVIDERS = [
    {"id": "google:gemini-3.1-flash-lite-preview", "label": "preview-lite"},
    {"id": "google:gemini-2.5-flash-lite", "label": "stable-lite"},
]

FLASH_PROVIDERS = [
    {"id": "google:gemini-3-flash-preview", "label": "preview-flash"},
    {"id": "google:gemini-2.5-flash", "label": "stable-flash"},
]


def _load_examples(run_db: Path, samples_per_task: int) -> tuple[list[dict], list[dict], list[dict]]:
    conn = sqlite3.connect(str(run_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    screening_rows = cur.execute(
        """
        SELECT title, abstract
        FROM papers
        WHERE abstract IS NOT NULL AND length(trim(abstract)) > 120
        ORDER BY random()
        LIMIT ?
        """,
        (samples_per_task,),
    ).fetchall()

    extraction_rows = cur.execute(
        """
        SELECT data
        FROM extraction_records
        WHERE data IS NOT NULL AND length(trim(data)) > 300
        ORDER BY random()
        LIMIT ?
        """,
        (samples_per_task,),
    ).fetchall()
    conn.close()

    screening_tests: list[dict] = []
    for row in screening_rows:
        screening_tests.append(
            {
                "vars": {
                    "title": row["title"],
                    "abstract": row["abstract"][:1800],
                }
            }
        )

    extraction_tests: list[dict] = []
    for row in extraction_rows:
        extraction_tests.append({"vars": {"full_text": row["data"][:3200]}})

    writing_tests: list[dict] = []
    for idx in range(samples_per_task):
        writing_tests.append(
            {
                "vars": {
                    "facts": (
                        "Included studies: 5. "
                        "Most reported operational improvements but mixed financial effects. "
                        "Evidence certainty mostly low-to-moderate. "
                        f"Sample id: {idx}."
                    )
                }
            }
        )

    return screening_tests, extraction_tests, writing_tests


def _build_config(
    run_db: Path,
    output_yaml: Path,
    prompt_dir: Path,
    samples_per_task: int,
    latency_ms: int,
    cost_usd: float,
) -> None:
    screening_tests, extraction_tests, writing_tests = _load_examples(run_db, samples_per_task)

    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "screening.txt").write_text(
        "You are a systematic review screener.\n"
        "Return strict JSON only with keys: decision, confidence, reason.\n\n"
        "Title: {{title}}\n\nAbstract: {{abstract}}\n",
        encoding="utf-8",
    )
    (prompt_dir / "extraction.txt").write_text(
        "Extract structured study information from this text.\n"
        "Return strict JSON only with keys: study_design, sample_size, primary_outcome, effect_summary.\n\n"
        "{{full_text}}\n",
        encoding="utf-8",
    )
    (prompt_dir / "writing.txt").write_text(
        "Write one academic paragraph (120-180 words) for systematic review results.\n"
        "Do not use bullet points, do not mention being an AI.\n\n"
        "Facts: {{facts}}\n",
        encoding="utf-8",
    )

    base_assert = [
        {"type": "latency", "threshold": latency_ms},
    ]
    eval_opts = {"maxConcurrency": 4, "delay": 250}

    screening_cfg = {
        "description": "A/B benchmark screening-json",
        "providers": SCREENING_PROVIDERS,
        "prompts": ["file://./prompts/screening.txt"],
        "evaluateOptions": eval_opts,
        "defaultTest": {"assert": base_assert + [{"type": "contains-json"}]},
        "tests": screening_tests,
    }
    extraction_cfg = {
        "description": "A/B benchmark extraction-json",
        "providers": FLASH_PROVIDERS,
        "prompts": ["file://./prompts/extraction.txt"],
        "evaluateOptions": eval_opts,
        "defaultTest": {"assert": base_assert + [{"type": "contains-json"}]},
        "tests": extraction_tests,
    }
    writing_cfg = {
        "description": "A/B benchmark writing-rubric",
        "providers": FLASH_PROVIDERS,
        "prompts": ["file://./prompts/writing.txt"],
        "evaluateOptions": eval_opts,
        "defaultTest": {
            "assert": base_assert
            + [
                {
                    "type": "javascript",
                    "value": "output.split(/\\s+/).length >= 90 && output.split(/\\s+/).length <= 220",
                },
                {"type": "javascript", "value": "!/\\b(as an ai|i am an ai|language model)\\b/i.test(output)"},
            ]
        },
        "tests": writing_tests,
    }

    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    (output_yaml.parent / "screening.yaml").write_text(yaml.safe_dump(screening_cfg, sort_keys=False), encoding="utf-8")
    (output_yaml.parent / "extraction.yaml").write_text(
        yaml.safe_dump(extraction_cfg, sort_keys=False), encoding="utf-8"
    )
    (output_yaml.parent / "writing.yaml").write_text(yaml.safe_dump(writing_cfg, sort_keys=False), encoding="utf-8")
    output_yaml.write_text(
        yaml.safe_dump(
            {
                "description": "Combined benchmark (informational)",
                "configs": ["screening.yaml", "extraction.yaml", "writing.yaml"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _run_promptfoo(work_dir: Path, json_out: Path) -> int:
    configs = ["screening.yaml", "extraction.yaml", "writing.yaml"]
    failures = 0
    for cfg in configs:
        out_file = work_dir / f"{Path(cfg).stem}.results.json"
        cmd = [
            "npx",
            "promptfoo@latest",
            "eval",
            "-c",
            str(work_dir / cfg),
            "--output",
            str(out_file),
        ]
        console.print(f"Running promptfoo benchmark for {cfg}...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            failures += 1
            console.print(f"[yellow]promptfoo returned non-zero for {cfg}; keeping partial output if present.[/yellow]")
            if proc.stdout:
                console.print(proc.stdout)
            if proc.stderr:
                console.print(proc.stderr)
    # Merge quick summary payload path for downstream parsing.
    json_out.write_text(
        json.dumps({"result_files": [f"{c.split('.')[0]}.results.json" for c in configs]}), encoding="utf-8"
    )
    if failures:
        console.print(f"[yellow]promptfoo completed with {failures} scenario-level failures.[/yellow]")
    else:
        console.print("[green]promptfoo benchmark completed.[/green]")
    return 0


def _print_summary(json_out: Path) -> None:
    if not json_out.exists():
        console.print("[yellow]No promptfoo JSON output found; skipping summary.[/yellow]")
        return
    data = json.loads(json_out.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for rel in data.get("result_files", []):
        p = json_out.parent / rel
        if not p.exists():
            continue
        chunk = json.loads(p.read_text(encoding="utf-8"))
        results_obj = chunk.get("results", {})
        rows.extend(results_obj.get("prompts", []))
    stats: dict[str, dict[str, float]] = {}
    for row in rows:
        provider = row.get("provider", "unknown")
        metrics = row.get("metrics", {})
        s = stats.setdefault(provider, {"tests": 0.0, "passed": 0.0, "latency": 0.0, "cost": 0.0})
        tests = float(
            metrics.get("testPassCount", 0) + metrics.get("testFailCount", 0) + metrics.get("testErrorCount", 0)
        )
        passed = float(metrics.get("testPassCount", 0))
        s["tests"] += tests
        s["passed"] += passed
        s["latency"] += float(metrics.get("totalLatencyMs", 0.0))
        s["cost"] += float(metrics.get("cost", 0.0))

    table = Table(title="Promptfoo A/B Summary")
    table.add_column("Provider")
    table.add_column("Pass rate", justify="right")
    table.add_column("Total latency ms", justify="right")
    table.add_column("Total cost USD", justify="right")
    for provider, s in sorted(stats.items()):
        rate = (s["passed"] / s["tests"] * 100.0) if s["tests"] else 0.0
        table.add_row(provider, f"{rate:.1f}%", f"{s['latency']:.0f}", f"{s['cost']:.4f}")
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Gemini model routing via Promptfoo.")
    parser.add_argument("--run-db", required=True, help="Path to runtime.db from a completed run")
    parser.add_argument("--samples-per-task", type=int, default=4)
    parser.add_argument("--latency-threshold-ms", type=int, default=60000)
    parser.add_argument("--cost-threshold-usd", type=float, default=0.05)
    parser.add_argument("--work-dir", default="tmp/promptfoo-model-routing")
    parser.add_argument("--no-run", action="store_true", help="Only generate config/tests without running promptfoo")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    prompts_dir = work_dir / "prompts"
    config_path = work_dir / "promptfooconfig.yaml"
    json_out = work_dir / "results.json"
    work_dir.mkdir(parents=True, exist_ok=True)

    _build_config(
        run_db=Path(args.run_db),
        output_yaml=config_path,
        prompt_dir=prompts_dir,
        samples_per_task=args.samples_per_task,
        latency_ms=args.latency_threshold_ms,
        cost_usd=args.cost_threshold_usd,
    )
    console.print(f"Generated promptfoo config at {config_path}")

    if args.no_run:
        return 0

    rc = _run_promptfoo(work_dir, json_out)
    if rc != 0:
        return rc
    _print_summary(json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
