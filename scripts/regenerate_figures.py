"""
Regenerate all figures from a completed workflow run without any LLM calls.

IMPORTANT: Edit the four variables in the "Target run" block below before
running.  There is no auto-discovery -- the values below are set to a
specific historical run and WILL fail with FileNotFoundError on any other
machine.

How to find the values you need:
  - DB_PATH: the runtime.db inside the run's log directory, e.g.
      logs/<date>/<topic-slug>/run_<time>/runtime.db
  - WORKFLOW_ID: printed at the end of the run, or in run_summary.json
  - DEDUP_COUNT: "papers_after_dedup" in run_summary.json
  - OUTPUT_DIR: the folder under data/outputs/ where you want figures written

Usage (after editing the variables):
  uv run python scripts/regenerate_figures.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Target run -- edit these to point at a different run
# ---------------------------------------------------------------------------
DB_PATH = (
    "logs/2026-02-19"
    "/how-do-conversational-ai-tutors-impact-learning-outcomes-engagem"
    "/run_09-29-36PM/runtime.db"
)
WORKFLOW_ID = "wf-e95fcb33"
DEDUP_COUNT = 42  # from run_summary.json
OUTPUT_DIR = (
    "data/outputs/2026-02-19"
    "/how-do-conversational-ai-tutors-impact-learning-outcomes-engagem"
    "/run_09-29-36PM"
)
# ---------------------------------------------------------------------------


async def _get_included_papers(db_path: str, workflow_id: str):
    """
    This pipeline uses title_abstract-only screening (skip_fulltext_if_no_pdf=True).
    dual_screening_results therefore has NO 'fulltext' stage rows.
    We query 'title_abstract' directly instead of using get_included_paper_ids().
    """
    from src.db.database import get_db
    from src.db.repositories import WorkflowRepository
    from src.search.deduplication import deduplicate_papers

    async with get_db(db_path) as db:
        repo = WorkflowRepository(db)

        all_papers = await repo.get_all_papers()
        deduped, _ = deduplicate_papers(all_papers)

        # Query for papers that passed title_abstract screening
        cursor = await db.execute(
            """
            SELECT DISTINCT paper_id
            FROM dual_screening_results
            WHERE workflow_id = ?
              AND stage = 'title_abstract'
              AND final_decision IN ('include', 'uncertain')
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        included_ids = {str(r[0]) for r in rows}

        included_papers = [p for p in deduped if p.paper_id in included_ids]
        return included_papers, repo, db


async def main() -> None:
    from rich.console import Console

    from src.db.database import get_db
    from src.db.repositories import WorkflowRepository
    from src.prisma import build_prisma_counts, render_prisma_diagram
    from src.search.deduplication import deduplicate_papers
    from src.visualization import render_geographic, render_rob_traffic_light, render_timeline

    console = Console()
    out = Path(OUTPUT_DIR)

    console.print(f"[bold]Regenerating figures for {WORKFLOW_ID}[/]")
    console.print(f"  DB  : {DB_PATH}")
    console.print(f"  Out : {out}")

    async with get_db(DB_PATH) as db:
        repo = WorkflowRepository(db)

        # --- Load included papers (title_abstract stage only run) ---
        all_papers = await repo.get_all_papers()
        deduped, _ = deduplicate_papers(all_papers)

        cursor = await db.execute(
            """
            SELECT DISTINCT paper_id
            FROM dual_screening_results
            WHERE workflow_id = ?
              AND stage = 'title_abstract'
              AND final_decision IN ('include', 'uncertain')
            """,
            (WORKFLOW_ID,),
        )
        rows = await cursor.fetchall()
        included_ids = {str(r[0]) for r in rows}
        included_papers = [p for p in deduped if p.paper_id in included_ids]
        console.print(f"  Papers loaded: {len(included_papers)}")

        # --- Load RoB assessments ---
        rob2_rows, robins_i_rows = await repo.load_rob_assessments(WORKFLOW_ID)
        console.print(
            f"  RoB2: {len(rob2_rows)} studies | ROBINS-I: {len(robins_i_rows)} studies"
        )

        # --- Build PRISMA counts ---
        prisma_counts = await build_prisma_counts(
            repo,
            WORKFLOW_ID,
            DEDUP_COUNT,
            included_qualitative=0,
            included_quantitative=len(included_papers),
        )
        console.print(f"  PRISMA counts built (arithmetic_valid check applied)")

    # --- Render figures (all synchronous) ---
    prisma_path = str(out / "fig_prisma_flow.png")
    render_prisma_diagram(prisma_counts, prisma_path)
    console.print(f"  [green]OK[/] PRISMA flow -> {Path(prisma_path).name}")

    timeline_path = str(out / "fig_publication_timeline.png")
    render_timeline(included_papers, timeline_path)
    console.print(f"  [green]OK[/] Timeline    -> {Path(timeline_path).name}")

    geo_path = str(out / "fig_geographic_distribution.png")
    render_geographic(included_papers, geo_path)
    console.print(f"  [green]OK[/] Geographic  -> {Path(geo_path).name}")

    paper_lookup = {p.paper_id: p for p in included_papers}
    rob_path = str(out / "fig_rob_traffic_light.png")
    rob2_path = str(out / "fig_rob2_traffic_light.png")
    # not_applicable_count=0 because the existing run did not track NOT_APPLICABLE routing;
    # a fresh run will have accurate counts once study_router.py changes take effect.
    render_rob_traffic_light(
        rob2_rows,
        robins_i_rows,
        rob_path,
        paper_lookup=paper_lookup,
        not_applicable_count=0,
        rob2_output_path=rob2_path,
    )
    console.print(f"  [green]OK[/] RoB figure  -> {Path(rob_path).name}")
    if Path(rob2_path).exists():
        console.print(f"  [green]OK[/] RoB2 figure -> {Path(rob2_path).name}")

    console.print("\n[bold green]All figures regenerated.[/]")
    console.print("Open the output directory to inspect the updated PNGs:")
    console.print(f"  open {out}")


if __name__ == "__main__":
    asyncio.run(main())
