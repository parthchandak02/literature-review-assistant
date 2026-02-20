"""
Regenerate all figures from a completed workflow run without any LLM calls.

Key improvements over naive approach:
  - Does NOT re-deduplicate after loading. Queries the exact paper IDs that
    were included in the original run (via dual_screening_results) then loads
    those papers directly, preserving the original 36-paper count.
  - Recomputes display_label for every paper using the current (fixed)
    compute_display_label() so stale DB values are overridden in memory.

Usage:
  uv run python scripts/regenerate_figures.py

Override DB_PATH / WORKFLOW_ID / OUTPUT_DIR to target a different run.
"""
from __future__ import annotations

import asyncio
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


async def main() -> None:
    from rich.console import Console

    from src.db.database import get_db
    from src.db.repositories import WorkflowRepository
    from src.models.papers import compute_display_label
    from src.prisma import build_prisma_counts, render_prisma_diagram
    from src.visualization import render_geographic, render_rob_traffic_light, render_timeline

    console = Console()
    out = Path(OUTPUT_DIR)

    console.print(f"[bold]Regenerating figures for {WORKFLOW_ID}[/]")
    console.print(f"  DB  : {DB_PATH}")
    console.print(f"  Out : {out}")

    async with get_db(DB_PATH) as db:
        repo = WorkflowRepository(db)

        # --- Load included papers by ID without re-deduplication ---
        # Query the exact paper IDs that the original run included.
        # This pipeline used title_abstract-only screening (skip_fulltext_if_no_pdf=True)
        # so dual_screening_results has NO 'fulltext' stage rows.
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
        console.print(f"  Included IDs from DB: {len(included_ids)}")

        included_papers = await repo.load_papers_by_ids(included_ids)
        console.print(f"  Papers loaded: {len(included_papers)}")

        # Override stale display_labels stored in the DB with the current
        # (fixed) compute_display_label logic so figures show clean labels.
        for p in included_papers:
            p.display_label = compute_display_label(p)

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
        console.print("  PRISMA counts built")

    # --- Render all figures (synchronous) ---
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
    # not_applicable_count=0 because the existing run did not track NOT_APPLICABLE
    # routing (study_router.py fix only takes effect on a fresh run).
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
    console.print(f"  open {out}")


if __name__ == "__main__":
    asyncio.run(main())
