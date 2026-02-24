#!/usr/bin/env python3
"""Retroactively regenerate doc_manuscript.md sections (Figures, Declarations,
Study Characteristics Table, References) for an existing run directory.

Usage:
    uv run python scripts/finalize_manuscript.py --run-dir <path-to-run-directory>

Example:
    uv run python scripts/finalize_manuscript.py \
        --run-dir runs/2026-02-22/how-do-conversational-ai-tutors-impact-learning-outcomes-engagem/run_03-29-23PM
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    is_extraction_failed,
    strip_appended_sections,
)

def _inject_imrad_headings(body: str) -> str:
    """Inject missing H2 IMRaD headings into an existing LLM-generated body.

    Handles manuscripts written before the heading-injection pipeline was
    added.  Each substitution is idempotent: if the heading already exists
    the pattern will not match and the body is returned unchanged.
    """
    # 1. Methods: insert before the PRISMA opening statement.
    body = re.sub(
        r"(?m)^(This systematic review follows the Preferred Reporting Items)",
        r"## Methods\n\n\1",
        body, count=1,
    )
    # 2. Results: upgrade ### **Results** (H3 with bold) to ## Results.
    body = re.sub(r"(?m)^### \*\*Results\*\*\s*$", "## Results", body)
    # 3. Discussion: insert before ### Principal Findings.
    body = re.sub(
        r"(?m)^(### Principal Findings)",
        r"## Discussion\n\n\1",
        body, count=1,
    )
    # 4. Introduction: insert after the last abstract bold-field line
    #    (the line that starts with **Funding: or **Keywords: etc.)
    #    The abstract always ends with one of these fields followed by a
    #    blank line and the first prose sentence (capital letter).
    body = re.sub(
        r"(\*\*(?:Funding|Protocol Registration|Keywords)[^\n]*\n)(\n)([A-Z])",
        r"\1\n## Introduction\n\n\3",
        body, count=1,
    )
    return body


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
    body = _inject_imrad_headings(body)

    artifacts = {key: str(run_path / filename) for key, filename in ARTIFACT_MAP.items()}

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        citation_rows = await CitationRepository(db).get_all_citations_for_export()

        # Determine workflow_id from the workflows table (use the most recent row).
        cursor = await db.execute(
            "SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        workflow_id = str(row[0]) if row else None

        papers = []
        extraction_records = []
        if workflow_id:
            extraction_records = await repo.load_extraction_records(workflow_id)
            # Derive included paper IDs from extraction records (works regardless of
            # whether the run had a fulltext screening stage).
            included_ids = {r.paper_id for r in extraction_records}
            if not included_ids:
                # Fallback: use fulltext/title_abstract screening decisions
                included_ids = await repo.get_included_paper_ids(workflow_id)
            papers = await repo.load_papers_by_ids(included_ids)

    # Apply post-extraction quality gate: exclude papers where LLM extraction
    # produced only placeholder data (all NR outcomes, "other" design, no count).
    clean_records = [r for r in extraction_records if not is_extraction_failed(r)]
    failed_count = len(extraction_records) - len(clean_records)
    clean_paper_ids = {r.paper_id for r in clean_records}
    clean_papers = [p for p in papers if p.paper_id in clean_paper_ids]

    found_figs = [k for k, v in artifacts.items() if pathlib.Path(v).exists()]
    print(f"Found {len(found_figs)} figure(s): {found_figs}")
    print(f"Found {len(citation_rows)} citation(s) in database.")
    print(f"Found {len(papers)} included paper(s), {len(extraction_records)} extraction record(s).")
    if failed_count:
        print(
            f"Quality gate: {failed_count} extraction record(s) excluded (all-placeholder data). "
            f"{len(clean_records)} clean records forwarded to manuscript."
        )

    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=citation_rows,
        papers=clean_papers,
        extraction_records=clean_records,
    )

    manuscript_path.write_text(full_manuscript, encoding="utf-8")
    print(f"Done. Updated {manuscript_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Regenerate appended sections in an existing doc_manuscript.md"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing doc_manuscript.md and runtime.db",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.run_dir)))
