#!/usr/bin/env python3
"""Validate review YAML through ReviewConfig and resolve_profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from src.models import ReviewConfig, resolve_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate review YAML methodology profile resolution")
    parser.add_argument(
        "config_path",
        nargs="?",
        default="tests/fixtures/scoping/review_scoping_smoke.yaml",
        help="Path to review YAML (default: scoping smoke fixture)",
    )
    args = parser.parse_args(argv)

    path = Path(args.config_path)
    if not path.exists():
        print(f"Config file not found: {path}", file=sys.stderr)
        return 1

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        print("Config root must be a mapping", file=sys.stderr)
        return 1

    try:
        review = ReviewConfig.model_validate(raw)
        profile = resolve_profile(review)
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "config_path": str(path),
        "review_type": review.review_type.value,
        "question_framework": review.question_framework,
        "methodology_profile": profile.model_dump(mode="json"),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
