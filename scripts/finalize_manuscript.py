#!/usr/bin/env python3
"""Retroactively regenerate doc_manuscript.md sections for an existing run directory.

Useful for historical runs that were produced before a pipeline fix, or for
re-assembling the manuscript after tweaking config without re-running everything.

What this script does:
  1. Reads the run's doc_manuscript.md and strips previously-appended sections
     (idempotent -- safe to run multiple times on the same run).
  2. Repairs IMRaD heading structure for manuscripts produced before P6 prompt fix.
  3. Re-assembles the full manuscript via assemble_submission_manuscript(), which:
     - Converts [AuthorYear] citekeys to [N] numbered citations
     - Appends Declarations, GRADE Evidence Profile, GRADE SoF Table,
       Study Characteristics Table, Figures, References, and Search Strategies Appendix
  4. Strips any surviving unresolved [AuthorYear] citekeys (safety net).

Note: All root-cause fixes (GRADE SoF, search appendix, excluded studies footnote,
kappa framing) are now handled by the primary pipeline. This script is a thin
regeneration utility for historical runs.

Usage:
    uv run python scripts/finalize_manuscript.py --run-dir <path-to-run-directory>

Example:
    uv run python scripts/finalize_manuscript.py \\
        --run-dir runs/2026-03-01/what-is-the-impact.../run_01-42-59PM
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys
from types import SimpleNamespace
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    is_extraction_failed,
    strip_appended_sections,
)


# ---------------------------------------------------------------------------
# Unresolved citekey cleanup (Fix 1)
# ---------------------------------------------------------------------------
# Matches author-year citekeys like [Mounir2020], [Mounir2020; Margaux2021],
# [lise2013; Tomoki2022], [Bryan2016; Hisham2021; NANDINI2023].
# These survived numbered-citation conversion because they were not in the
# citation ledger. We strip them to keep prose clean for journal submission.
_AUTHOR_YEAR_KEY_RE = re.compile(
    r"\[[A-Za-z][A-Za-z0-9]*\d{4}(?:;\s*[A-Za-z][A-Za-z0-9]*\d{4})*\]"
)


def _strip_unresolved_citekeys(text: str) -> str:
    """Remove author-year citation keys that were not resolved to [N] numbers."""
    cleaned = _AUTHOR_YEAR_KEY_RE.sub("", text)
    # Collapse any double spaces left by removed inline citations
    cleaned = re.sub(r"  +", " ", cleaned)
    # Collapse trailing spaces before punctuation
    cleaned = re.sub(r" ([,.:;])", r"\1", cleaned)
    return cleaned



# ---------------------------------------------------------------------------
# IMRaD heading injection (safety net for historical runs)
# ---------------------------------------------------------------------------

def _inject_imrad_headings(body: str) -> str:
    """Inject missing H2 IMRaD headings into an existing LLM-generated body."""
    body = re.sub(
        r"(?m)^(This systematic review follows the Preferred Reporting Items)",
        r"## Methods\n\n\1",
        body, count=1,
    )
    body = re.sub(r"(?m)^### \*\*Results\*\*\s*$", "## Results", body)
    body = re.sub(
        r"(?m)^(?<!## Discussion\n\n)(### Principal Findings)",
        r"## Discussion\n\n\1",
        body, count=1,
    )
    body = re.sub(r"(?m)^## Discussion\n+## Discussion\n", "## Discussion\n", body)
    body = re.sub(
        r"(\*\*(?:Funding|Protocol Registration|Keywords)[^\n]*\n)(\n)([A-Z])",
        r"\1\n## Introduction\n\n\3",
        body, count=1,
    )
    return body


# ---------------------------------------------------------------------------
# Artifact map
# ---------------------------------------------------------------------------

ARTIFACT_MAP = {
    "prisma_diagram": "fig_prisma_flow.png",
    "rob_traffic_light": "fig_rob_traffic_light.png",
    "rob2_traffic_light": "fig_rob2_traffic_light.png",
    "fig_forest_plot": "fig_forest_plot.png",
    "fig_funnel_plot": "fig_funnel_plot.png",
    "timeline": "fig_publication_timeline.png",
    "geographic": "fig_geographic_distribution.png",
    "concept_taxonomy": "fig_concept_taxonomy.svg",
    "conceptual_framework": "fig_conceptual_framework.svg",
    "methodology_flow": "fig_methodology_flow.svg",
    "evidence_network": "fig_evidence_network.png",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    # --- Read and clean manuscript body ---
    body = strip_appended_sections(manuscript_path.read_text(encoding="utf-8"))
    body = _inject_imrad_headings(body)

    artifacts = {key: str(run_path / filename) for key, filename in ARTIFACT_MAP.items()}

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        citation_rows = await CitationRepository(db).get_all_citations_for_export()

        cursor = await db.execute(
            "SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        workflow_id = str(row[0]) if row else None

        papers = []
        extraction_records = []
        grade_assessments = []

        robins_i_assessments = []
        if workflow_id:
            extraction_records = await repo.load_extraction_records(workflow_id)
            included_ids = {r.paper_id for r in extraction_records}
            if not included_ids:
                included_ids = await repo.get_included_paper_ids(workflow_id)
            papers = await repo.load_papers_by_ids(included_ids)

            grade_assessments = await repo.load_grade_assessments(workflow_id)
            _rob2_rows, robins_i_assessments = await repo.load_rob_assessments(
                workflow_id
            )

    # Quality gate: exclude extraction records with only placeholder data
    clean_records = [r for r in extraction_records if not is_extraction_failed(r)]
    failed_count = len(extraction_records) - len(clean_records)
    clean_paper_ids = {r.paper_id for r in clean_records}
    clean_papers = [p for p in papers if p.paper_id in clean_paper_ids]

    found_figs = [k for k, v in artifacts.items() if pathlib.Path(v).exists()]
    print(f"Found {len(found_figs)} figure(s): {found_figs}")
    print(f"Found {len(citation_rows)} citation(s) in database.")
    print(f"Found {len(papers)} included paper(s), {len(extraction_records)} extraction record(s).")
    print(f"Found {len(grade_assessments)} GRADE assessment(s).")
    if failed_count:
        print(
            f"Quality gate: {failed_count} extraction record(s) excluded (all-placeholder data). "
            f"{len(clean_records)} clean records forwarded to manuscript."
        )

    _search_appendix_path = run_path / "doc_search_strategies_appendix.md"
    research_question = ""
    review_config = None
    review_yaml_path = run_path / "review.yaml"
    if review_yaml_path.exists():
        try:
            config_data = yaml.safe_load(review_yaml_path.read_text(encoding="utf-8")) or {}
            research_question = config_data.get("research_question", "") or ""
            pico_data = config_data.get("pico") or {}
            review_config = SimpleNamespace(
                pico=SimpleNamespace(
                    population=pico_data.get("population", ""),
                    intervention=pico_data.get("intervention", ""),
                    comparison=pico_data.get("comparison", ""),
                    outcome=pico_data.get("outcome", ""),
                ),
                inclusion_criteria=config_data.get("inclusion_criteria", []),
                exclusion_criteria=config_data.get("exclusion_criteria", []),
            )
        except Exception:
            pass

    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=citation_rows,
        papers=clean_papers,
        extraction_records=clean_records,
        grade_assessments=grade_assessments if grade_assessments else None,
        robins_i_assessments=robins_i_assessments if robins_i_assessments else None,
        review_config=review_config,
        failed_count=failed_count,
        search_appendix_path=_search_appendix_path if _search_appendix_path.exists() else None,
        research_question=research_question,
        title=None,
    )

    # Strip any surviving unresolved [AuthorYear] citekeys (hallucinated or ledger gaps)
    full_manuscript = _strip_unresolved_citekeys(full_manuscript)

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
