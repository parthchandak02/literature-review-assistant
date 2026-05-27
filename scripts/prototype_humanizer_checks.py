#!/usr/bin/env python3
"""PROTOTYPE: quick local probe for humanizer checks and guardrails."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.writing.humanizer_checks import scan_humanizer_flags
from src.writing.humanizer_guardrails import apply_deterministic_guardrails

SAMPLE_PATH = Path("tests/fixtures/humanizer_sample.txt")

BAD_AI_EXAMPLE = (
    "In today's rapidly evolving digital landscape, cybersecurity has become a crucial and pivotal concern for "
    "organizations worldwide. Moreover, the increasing sophistication of cyber threats underscores the importance "
    "of implementing robust and comprehensive security measures. Studies show that a holistic approach serves as "
    "the most effective strategy."
)


def severity_counts(flags: list) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for flag in flags:
        counts[flag.tier] = counts.get(flag.tier, 0) + 1
    return counts


def print_counts(console: Console, title: str, flags: list) -> None:
    counts = severity_counts(flags)
    table = Table(title=title)
    table.add_column("tier")
    table.add_column("count", justify="right")
    for tier in ("high", "medium", "low"):
        table.add_row(tier, str(counts.get(tier, 0)))
    console.print(table)


def main() -> None:
    console = Console()
    sample_text = SAMPLE_PATH.read_text(encoding="utf-8").strip()

    for label, raw in (
        ("fixture_sample", sample_text),
        ("skill_before_example", BAD_AI_EXAMPLE),
    ):
        cleaned = apply_deterministic_guardrails(raw)
        before = scan_humanizer_flags(raw)
        after = scan_humanizer_flags(cleaned)

        console.rule(f"[bold]{label}")
        print_counts(console, "before guardrails", before)
        print_counts(console, "after guardrails", after)
        console.print("[dim]Preview after guardrails:[/dim]")
        console.print(cleaned[:400] + ("..." if len(cleaned) > 400 else ""))


if __name__ == "__main__":
    main()
