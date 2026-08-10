"""Unified run path helpers for all phases.

All per-run files (operational DB, app log, output documents, figures) live
under a single run directory:
    <run_root>/<YYYY-MM-DD>/<topic-slug>/run_<HH-MM-SSAM>/
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def workflow_slug(text: str, max_len: int = 64) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9\s-]", "", normalized)
    normalized = re.sub(r"\s+", "-", normalized).strip("-")
    if not normalized:
        normalized = "workflow"
    return normalized[:max_len].rstrip("-")


@dataclass(frozen=True)
class RunPaths:
    """All paths for a single workflow run, under one directory."""

    run_dir: Path
    date_folder: str
    run_dir_name: str
    # Operational
    runtime_db: Path
    app_log: Path
    run_summary: Path
    acceptance_checklist: Path
    revalidation_log: Path
    phase_readiness: Path
    # Output documents / figures
    search_appendix: Path
    protocol_markdown: Path


def default_run_artifacts(run_dir: Path) -> dict[str, str]:
    """Canonical artifact path map for a run directory (start + resume)."""
    return {
        "run_summary": str(run_dir / "run_summary.json"),
        "search_appendix": str(run_dir / "doc_search_strategies_appendix.md"),
        "protocol": str(run_dir / "doc_protocol.md"),
        "coverage_report": str(run_dir / "doc_fulltext_retrieval_coverage.md"),
        "disagreements_report": str(run_dir / "doc_disagreements_report.md"),
        "rob_traffic_light": str(run_dir / "fig_rob_traffic_light.png"),
        "rob2_traffic_light": str(run_dir / "fig_rob2_traffic_light.png"),
        "narrative_synthesis": str(run_dir / "data_narrative_synthesis.json"),
        "manuscript_md": str(run_dir / "doc_manuscript.md"),
        "manuscript_tex": str(run_dir / "doc_manuscript.tex"),
        "references_bib": str(run_dir / "references.bib"),
        "prisma_diagram": str(run_dir / "fig_prisma_flow.png"),
        "timeline": str(run_dir / "fig_publication_timeline.png"),
        "geographic": str(run_dir / "fig_geographic_distribution.png"),
        "fig_forest_plot": str(run_dir / "fig_forest_plot.png"),
        "fig_funnel_plot": str(run_dir / "fig_funnel_plot.png"),
        "concept_taxonomy": str(run_dir / "fig_concept_taxonomy.svg"),
        "conceptual_framework": str(run_dir / "fig_conceptual_framework.svg"),
        "methodology_flow": str(run_dir / "fig_methodology_flow.svg"),
        "custom_diagram_01": str(run_dir / "fig_custom_01.png"),
        "custom_diagram_02": str(run_dir / "fig_custom_02.png"),
        "custom_diagram_03": str(run_dir / "fig_custom_03.png"),
        "diagram_brief_pack": str(run_dir / "data_diagram_brief_pack.json"),
        "diagram_placement_plan": str(run_dir / "data_diagram_placement_plan.json"),
        "diagram_generation_report": str(run_dir / "data_diagram_generation_report.json"),
        "evidence_network": str(run_dir / "fig_evidence_network.png"),
        "papers_dir": str(run_dir / "papers"),
        "papers_manifest": str(run_dir / "data_papers_manifest.json"),
        "prospero_form_md": str(run_dir / "doc_prospero_registration.md"),
        "prospero_form": str(run_dir / "doc_prospero_registration.docx"),
    }


def create_run_paths(run_root: str, workflow_description: str, workflow_id: str = "") -> RunPaths:
    """Create and return all paths for a new workflow run.

    Creates the run directory on disk. Every log and output artifact for
    this run lives inside the returned run_dir.

    If workflow_id is provided (e.g. "wf-0007"), it is prepended to the
    topic slug so the folder is easily identifiable:
        runs/YYYY-MM-DD/wf-0007-<topic-slug>/run_<HH-MM-SSAM>/
    """
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    run_dir_name = f"run_{now.strftime('%I-%M-%S%p')}"
    slug = workflow_slug(workflow_description)
    folder_name = f"{workflow_id}-{slug}" if workflow_id else slug
    run_dir = Path(run_root) / date_folder / folder_name / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        run_dir=run_dir,
        date_folder=date_folder,
        run_dir_name=run_dir_name,
        runtime_db=run_dir / "runtime.db",
        app_log=run_dir / "app.jsonl",
        run_summary=run_dir / "run_summary.json",
        acceptance_checklist=run_dir / "acceptance_checklist.md",
        revalidation_log=run_dir / "revalidation.log",
        phase_readiness=run_dir / "phase_readiness.md",
        search_appendix=run_dir / "doc_search_strategies_appendix.md",
        protocol_markdown=run_dir / "doc_protocol.md",
    )
