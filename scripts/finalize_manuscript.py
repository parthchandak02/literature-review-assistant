#!/usr/bin/env python3
"""Retroactively append Figures and References sections to an existing doc_manuscript.md.

Usage:
    uv run python scripts/finalize_manuscript.py --run-dir <path-to-run-directory>

Example:
    uv run python scripts/finalize_manuscript.py \\
        --run-dir runs/2026-02-22/how-do-conversational-ai-tutors-impact-learning-outcomes-engagem/run_03-29-23PM
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.db.database import get_db
from src.db.repositories import CitationRepository
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    strip_appended_sections,
)

ARTIFACT_MAP = {
    "prisma_diagram": "fig_prisma_flow.png",
    "rob_traffic_light": "fig_rob_traffic_light.png",
    "rob2_traffic_light": "fig_rob2_traffic_light.png",
    "timeline": "fig_publication_timeline.png",
    "geographic": "fig_geographic_distribution.png",
}


async def main(run_dir: str) -> int:
    run_path = pathlib.Path(run_dir).resolve()
    manuscript_path = run_path / "doc_manuscript.md"
    db_path = run_path / "runtime.db"

    if not manuscript_path.exists():
        print(f"ERROR: manuscript not found: {manuscript_path}")
        return 1
    if not db_path.exists():
        print(f"ERROR: runtime.db not found: {db_path}")
        return 1

    body = strip_appended_sections(manuscript_path.read_text(encoding="utf-8"))

    artifacts = {key: str(run_path / filename) for key, filename in ARTIFACT_MAP.items()}

    async with get_db(str(db_path)) as db:
        citation_rows = await CitationRepository(db).get_all_citations_for_export()

    found_figs = [k for k, v in artifacts.items() if pathlib.Path(v).exists()]
    print(f"Found {len(found_figs)} figure(s): {found_figs}")
    print(f"Found {len(citation_rows)} citation(s) in database.")

    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=citation_rows,
    )

    manuscript_path.write_text(full_manuscript, encoding="utf-8")
    print(f"Done. Updated {manuscript_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Append Figures and References sections to an existing doc_manuscript.md"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing doc_manuscript.md and runtime.db",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.run_dir)))
