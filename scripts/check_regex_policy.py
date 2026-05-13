#!/usr/bin/env python3
"""Guardrail for regex policy in pilot migration files.

Policy:
- No new `re.` usage may be introduced in pilot boundary files.
- Files already carrying approved formatting regex are frozen to a baseline
  maximum count until they are fully migrated.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PILOT_BASELINES: dict[str, int] = {
    "src/writing/orchestration.py": 67,
    "src/writing/section_writer.py": 0,
    "src/extraction/extractor.py": 35,
    "src/screening/dual_screener.py": 0,
    "src/manuscript/reviewer.py": 0,
    # Scale wave (post-pilot): freeze regex growth in adjacent boundary modules.
    "src/extraction/table_extraction.py": 14,
    "src/screening/criteria_refinement.py": 2,
    "src/export/markdown_refs.py": 41,
}

RE_USAGE_PATTERN = re.compile(r"\bre\.")


def count_re_usage(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if RE_USAGE_PATTERN.search(line))


def main() -> int:
    violations: list[str] = []
    for rel_path, baseline in PILOT_BASELINES.items():
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            violations.append(f"Missing pilot file: {rel_path}")
            continue
        current = count_re_usage(abs_path)
        if current > baseline:
            violations.append(
                f"{rel_path}: found {current} regex usages, baseline allows {baseline}."
            )
    if violations:
        print("Regex policy check failed:")
        for item in violations:
            print(f"- {item}")
        return 1
    print("Regex policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

