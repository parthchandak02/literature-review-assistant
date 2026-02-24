#!/usr/bin/env python3
"""Re-run LLM extraction for papers whose prior extraction produced only placeholder data.

This script repairs runs where the extraction LLM received the wrong research question
(e.g. config.yaml was changed between runs) and stored all-placeholder results.

Usage:
    uv run python scripts/re_extract.py --run-dir <path-to-run-directory>
    uv run python scripts/re_extract.py --run-dir <path> --config <path-to-review.yaml>

The script:
  1. Loads extraction records from the run DB.
  2. Identifies records where is_extraction_failed() is True.
  3. Re-runs ExtractionService LLM extraction for each, using:
       - run_dir/config_snapshot.yaml if it exists (preferred -- original config)
       - --config override if provided
       - config/review.yaml as last resort
  4. Overwrites the improved record in the DB (INSERT OR REPLACE).
  5. Prints a Rich summary table showing N attempted, N improved, N still failed.

After this script completes, run scripts/finalize_manuscript.py to regenerate the
manuscript with the improved extraction data.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.export.markdown_refs import is_extraction_failed
from src.extraction import ExtractionService, StudyClassifier
from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import StudyDesign

console = Console()


async def main(run_dir: str, config_override: str | None) -> int:
    run_path = pathlib.Path(run_dir).resolve()
    db_path = run_path / "runtime.db"

    if not db_path.exists():
        console.print(f"[red]ERROR: runtime.db not found: {db_path}[/]")
        return 1

    # Resolve config: snapshot > explicit override > live config
    config_path = str(run_path / "config_snapshot.yaml")
    if config_override:
        config_path = config_override
        console.print(f"[dim]Using provided config: {config_path}[/]")
    elif pathlib.Path(config_path).exists():
        console.print(f"[dim]Using run config snapshot: {config_path}[/]")
    else:
        config_path = "config/review.yaml"
        console.print(
            "[yellow]Warning: no config_snapshot.yaml found in run dir. "
            f"Using current config/review.yaml. If this does not match the original "
            f"run topic, results may still be wrong.[/]"
        )

    review, settings = load_configs(review_path=config_path)
    console.print(f"[bold]Research question:[/] {review.research_question[:120]}...")

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)

        # Get the workflow_id for this run
        cursor = await db.execute(
            "SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            console.print("[red]ERROR: no workflow found in DB.[/]")
            return 1
        workflow_id = str(row[0])
        console.print(f"[dim]Workflow ID: {workflow_id}[/]")

        # Load all extraction records and find failed ones
        all_records = await repo.load_extraction_records(workflow_id)
        failed_records = [r for r in all_records if is_extraction_failed(r)]
        console.print(
            f"Found [bold]{len(all_records)}[/] extraction records, "
            f"[red]{len(failed_records)}[/] have failed/placeholder data."
        )

        if not failed_records:
            console.print("[green]All extraction records are clean. Nothing to re-extract.[/]")
            return 0

        # Load the corresponding papers
        failed_paper_ids = {r.paper_id for r in failed_records}
        papers = await repo.load_papers_by_ids(failed_paper_ids)
        paper_map = {p.paper_id: p for p in papers}
        console.print(f"Loaded [bold]{len(papers)}[/] papers for re-extraction.")

        # Set up LLM clients
        provider = LLMProvider(settings=settings, repository=repo)
        llm_client = PydanticAIClient()
        classifier = StudyClassifier(
            repository=repo,
            provider=provider,
            review=review,
        )
        extractor = ExtractionService(
            repository=repo,
            llm_client=llm_client,
            settings=settings,
            review=review,
            provider=provider,
        )

        # Re-extract each failed record
        improved = 0
        still_failed = 0
        results: list[dict[str, str]] = []

        for i, rec in enumerate(failed_records, 1):
            paper = paper_map.get(rec.paper_id)
            if paper is None:
                console.print(f"[yellow]  [{i}/{len(failed_records)}] Paper {rec.paper_id[:12]} not found in DB -- skipping.[/]")
                still_failed += 1
                continue

            console.print(
                f"[dim]  [{i}/{len(failed_records)}] Re-extracting: {paper.title[:70]}...[/]"
            )

            try:
                study_design = await classifier.classify(workflow_id, paper)
            except Exception as exc:
                console.print(f"[yellow]    Classification failed ({exc}); using StudyDesign.OTHER.[/]")
                study_design = StudyDesign.OTHER

            full_text = (paper.abstract or paper.title or "").strip()

            try:
                new_rec = await extractor._llm_extract(paper, study_design, full_text)
                # Overwrite in DB (repositories.py uses INSERT OR REPLACE)
                await repo.save_extraction_record(workflow_id=workflow_id, record=new_rec)

                if is_extraction_failed(new_rec):
                    still_failed += 1
                    status = "[yellow]STILL FAILED[/]"
                else:
                    improved += 1
                    status = "[green]IMPROVED[/]"

                outcome_names = [
                    o.get("name", "") for o in (new_rec.outcomes or []) if isinstance(o, dict)
                ]
                results.append({
                    "paper": paper.title[:55],
                    "status": status,
                    "design": str(new_rec.study_design.value if hasattr(new_rec.study_design, "value") else new_rec.study_design),
                    "n": str(new_rec.participant_count or "NR"),
                    "outcomes": "; ".join(outcome_names[:2]) or "NR",
                })

            except Exception as exc:
                console.print(f"[red]    Re-extraction failed: {exc}[/]")
                still_failed += 1
                results.append({
                    "paper": paper.title[:55],
                    "status": "[red]ERROR[/]",
                    "design": "?",
                    "n": "?",
                    "outcomes": str(exc)[:60],
                })

    # Print summary table
    table = Table(title="Re-Extraction Summary", show_lines=True)
    table.add_column("Paper", style="dim", max_width=56)
    table.add_column("Status", min_width=14)
    table.add_column("Design", min_width=12)
    table.add_column("N", min_width=6)
    table.add_column("Key Outcomes", max_width=50)
    for r in results:
        table.add_row(r["paper"], r["status"], r["design"], r["n"], r["outcomes"])
    console.print(table)

    console.print(
        f"\n[bold]Total:[/] {len(failed_records)} attempted, "
        f"[green]{improved} improved[/], "
        f"[red]{still_failed} still failed[/]."
    )
    if improved:
        console.print(
            "\n[bold]Next step:[/] run "
            "[cyan]uv run python scripts/finalize_manuscript.py --run-dir "
            f"{run_dir}[/] to regenerate the manuscript."
        )
    return 0 if still_failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-run LLM extraction for papers with failed/placeholder extraction data."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing runtime.db",
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to the review.yaml config to use. "
            "Defaults to run_dir/config_snapshot.yaml if present, "
            "then config/review.yaml."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.run_dir, args.config)))
