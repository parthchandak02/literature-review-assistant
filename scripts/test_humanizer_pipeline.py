#!/usr/bin/env python3
"""Stage-wise validator for humanizer guardrails and citation integrity.

Usage:
  uv run python scripts/test_humanizer_pipeline.py --input-file sample.txt
  uv run python scripts/test_humanizer_pipeline.py --input-file sample.txt --citation-catalog-file catalog.txt --run-llm
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.writing.citation_grounding import verify_citation_grounding
from src.writing.humanizer import humanize_async
from src.writing.humanizer_guardrails import (
    apply_deterministic_guardrails,
    count_guardrail_phrases,
    extract_citation_blocks,
    extract_numeric_tokens,
)

console = Console()


def _parse_valid_citekeys(catalog_text: str) -> list[str]:
    keys: list[str] = []
    for line in catalog_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            keys.append(stripped[1 : stripped.index("]")])
    return keys


@dataclass
class StageResult:
    name: str
    text: str
    citation_blocks_same: bool
    numeric_tokens_same: bool
    hallucinated_count: int
    filler_phrases: int
    repeated_ngrams: int


def _evaluate_stage(
    name: str,
    candidate_text: str,
    baseline_text: str,
    valid_citekeys: list[str],
) -> StageResult:
    baseline_citations = extract_citation_blocks(baseline_text)
    baseline_numbers = extract_numeric_tokens(baseline_text)
    cand_citations = extract_citation_blocks(candidate_text)
    cand_numbers = extract_numeric_tokens(candidate_text)

    hallucinated_count = 0
    if valid_citekeys:
        _, hallucinated = verify_citation_grounding(candidate_text, valid_citekeys, name)
        hallucinated_count = len(hallucinated)

    phrase_counts = count_guardrail_phrases(candidate_text)
    return StageResult(
        name=name,
        text=candidate_text,
        citation_blocks_same=(cand_citations == baseline_citations),
        numeric_tokens_same=(cand_numbers == baseline_numbers),
        hallucinated_count=hallucinated_count,
        filler_phrases=phrase_counts.get("filler_phrases", 0),
        repeated_ngrams=phrase_counts.get("repeated_ngrams", 0),
    )


async def _run(args: argparse.Namespace) -> int:
    input_path = pathlib.Path(args.input_file)
    if not input_path.exists():
        console.print(f"[red]Input file not found:[/] {input_path}")
        return 1
    original = input_path.read_text(encoding="utf-8")

    valid_citekeys: list[str] = []
    if args.citation_catalog_file:
        catalog_path = pathlib.Path(args.citation_catalog_file)
        if not catalog_path.exists():
            console.print(f"[red]Citation catalog file not found:[/] {catalog_path}")
            return 1
        valid_citekeys = _parse_valid_citekeys(catalog_path.read_text(encoding="utf-8"))

    out_dir = pathlib.Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    stage1 = apply_deterministic_guardrails(original)
    stage2 = original
    stage3 = stage1

    if args.run_llm:
        stage2 = await humanize_async(
            original,
            model=args.model,
            temperature=args.temperature,
            max_chars=args.max_chars,
            provider=None,
        )
        stage3 = await humanize_async(
            stage1,
            model=args.model,
            temperature=args.temperature,
            max_chars=args.max_chars,
            provider=None,
        )

    results = [
        _evaluate_stage("original", original, original, valid_citekeys),
        _evaluate_stage("deterministic_only", stage1, original, valid_citekeys),
        _evaluate_stage("llm_only", stage2, original, valid_citekeys),
        _evaluate_stage("combined", stage3, original, valid_citekeys),
    ]

    summary = Table(title="Humanizer Stage Validation")
    summary.add_column("Stage")
    summary.add_column("Citation blocks preserved")
    summary.add_column("Numeric tokens preserved")
    summary.add_column("Hallucinated citekeys", justify="right")
    summary.add_column("Filler phrases", justify="right")
    summary.add_column("Repeated ngrams", justify="right")

    for row in results:
        summary.add_row(
            row.name,
            "YES" if row.citation_blocks_same else "NO",
            "YES" if row.numeric_tokens_same else "NO",
            str(row.hallucinated_count),
            str(row.filler_phrases),
            str(row.repeated_ngrams),
        )

    console.print(summary)

    if out_dir:
        (out_dir / "stage_original.txt").write_text(original, encoding="utf-8")
        (out_dir / "stage_deterministic_only.txt").write_text(stage1, encoding="utf-8")
        (out_dir / "stage_llm_only.txt").write_text(stage2, encoding="utf-8")
        (out_dir / "stage_combined.txt").write_text(stage3, encoding="utf-8")
        console.print(f"[green]Wrote stage outputs to:[/] {out_dir}")

    failed = [
        row
        for row in results[1:]
        if (not row.citation_blocks_same) or (not row.numeric_tokens_same) or row.hallucinated_count > 0
    ]
    if failed:
        console.print("[red]Validation failed for one or more stages.[/]")
        return 2
    console.print("[green]All selected stages passed integrity checks.[/]")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate humanizer pipeline stage integrity.")
    parser.add_argument("--input-file", required=True, help="Input section text file.")
    parser.add_argument(
        "--citation-catalog-file",
        default="",
        help="Optional citation catalog with [citekey] lines for hallucination checks.",
    )
    parser.add_argument("--run-llm", action="store_true", help="Run LLM stages in addition to deterministic stage.")
    parser.add_argument("--model", default=None, help="Optional model override for LLM stages.")
    parser.add_argument("--temperature", type=float, default=0.3, help="LLM temperature.")
    parser.add_argument("--max-chars", type=int, default=12000, help="Max chars sent to humanizer.")
    parser.add_argument("--output-dir", default="", help="Optional directory for stage text outputs.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
