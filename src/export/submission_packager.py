"""Package submission directory: LaTeX, BibTeX, figures, supplementary CSVs."""

from __future__ import annotations

import asyncio
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

from src.db.database import get_db
from src.db.repositories import CitationRepository
from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback
from src.export.bibtex_builder import build_bibtex
from src.export.docx_exporter import generate_docx
from src.export.ieee_latex import markdown_to_latex


async def _get_run_info(run_root: str, workflow_id: str) -> tuple[str, str, str] | None:
    """Resolve workflow_id to (db_path, output_dir, log_dir). Returns None if not found."""
    entry = await find_by_workflow_id(run_root, workflow_id)
    if entry is None:
        entry = await find_by_workflow_id_fallback(run_root, workflow_id)
    if entry is None:
        return None
    db_path = entry.db_path
    log_dir = str(Path(db_path).parent)
    run_summary_path = Path(log_dir) / "run_summary.json"
    if not run_summary_path.exists():
        return None
    try:
        data = json.loads(run_summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    output_dir = data.get("output_dir")
    if not output_dir or not Path(output_dir).is_dir():
        return None
    return db_path, output_dir, log_dir


async def _export_screening_decisions(db_path: str, workflow_id: str, out_path: Path) -> None:
    """Export screening_decisions to CSV."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT workflow_id, paper_id, stage, decision, reason, exclusion_reason, reviewer_type, confidence
            FROM screening_decisions
            WHERE workflow_id = ?
            ORDER BY paper_id, stage
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
    if not rows:
        out_path.write_text(
            "workflow_id,paper_id,stage,decision,reason,exclusion_reason,reviewer_type,confidence\n", encoding="utf-8"
        )
        return
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "workflow_id",
                "paper_id",
                "stage",
                "decision",
                "reason",
                "exclusion_reason",
                "reviewer_type",
                "confidence",
            ]
        )
        for row in rows:
            writer.writerow([str(c) for c in row])


async def _export_extraction_records(db_path: str, workflow_id: str, out_path: Path) -> None:
    """Export extraction_records to CSV (flatten JSON data)."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT paper_id, study_design, data
            FROM extraction_records
            WHERE workflow_id = ?
            ORDER BY paper_id
            """,
            (workflow_id,),
        )
        rows = await cursor.fetchall()
    if not rows:
        out_path.write_text("paper_id,study_design,intervention_description,results_summary\n", encoding="utf-8")
        return
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["paper_id", "study_design", "intervention_description", "results_summary"])
        for row in rows:
            paper_id, study_design, data_json = str(row[0]), str(row[1]), row[2]
            try:
                data = json.loads(data_json) if isinstance(data_json, str) else {}
            except json.JSONDecodeError:
                data = {}
            intervention = (data.get("intervention_description") or "").replace("\n", " ")[:500]
            results = (data.get("results_summary") or {}).get("summary") or ""
            results = str(results).replace("\n", " ")[:500]
            writer.writerow([paper_id, study_design, intervention, results])


def _generate_search_appendix_pdf(md_path: Path, pdf_path: Path) -> None:
    """Convert doc_search_strategies_appendix.md to PDF. Uses pdflatex if available, else md->html->weasyprint.
    If both fail, copies the markdown to supplementary so user can convert manually."""
    try:
        import pypandoc

        pypandoc.convert_file(
            str(md_path.resolve()),
            "pdf",
            outputfile=str(pdf_path),
            extra_args=["--pdf-engine=pdflatex"],
        )
        return
    except Exception:
        pass
    try:
        import pypandoc
        from weasyprint import HTML

        html_path = pdf_path.with_suffix(".html")
        pypandoc.convert_file(str(md_path.resolve()), "html", outputfile=str(html_path))
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        html_path.unlink(missing_ok=True)
        return
    except Exception:
        pass
    md_copy = pdf_path.with_suffix(".md")
    shutil.copy2(md_path, md_copy)
    if pdf_path.exists() and pdf_path.stat().st_size == 0:
        pdf_path.unlink()


def _build_number_to_citekey(
    md_content: str,
    citations: list[tuple],
) -> dict[str, str]:
    """Build mapping from [N] to citekey by parsing References section.

    Manuscripts use numbered refs [1], [2]. References section lists [N] Author... doi: URL.
    Match by DOI to get ordered citekeys, then return {str(N): citekey}.
    """
    doi_to_citekey: dict[str, str] = {}
    for row in citations:
        citekey = str(row[1])
        doi = row[2]
        if doi:
            norm = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            doi_to_citekey[norm] = citekey
    in_refs = False
    num_to_citekey: dict[str, str] = {}
    ref_num_re = re.compile(r"^\[(\d+)\]\s+")
    doi_re = re.compile(r"doi:\s*(https?://doi\.org/)?([^\s\)\]]+)")
    for line in md_content.split("\n"):
        if line.strip().startswith("## References") or line.strip() == "## References":
            in_refs = True
            continue
        if in_refs and line.strip().startswith("## "):
            break
        if in_refs:
            m = ref_num_re.match(line)
            if m:
                num = m.group(1)
                doi_match = doi_re.search(line)
                if doi_match:
                    norm_doi = doi_match.group(2).rstrip(".,")
                    if norm_doi in doi_to_citekey:
                        num_to_citekey[num] = doi_to_citekey[norm_doi]
    return num_to_citekey


def _run_pdflatex(tex_path: Path, cwd: Path) -> bool:
    """Run pdflatex and bibtex to produce PDF. Returns True on success."""
    try:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=cwd,
            capture_output=True,
            timeout=60,
        )
        stem = tex_path.stem
        subprocess.run(
            ["bibtex", stem],
            cwd=cwd,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=cwd,
            capture_output=True,
            timeout=60,
        )
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=cwd,
            capture_output=True,
            timeout=60,
        )
        pdf_path = tex_path.with_suffix(".pdf")
        return pdf_path.exists()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


async def package_submission(
    workflow_id: str,
    run_root: str = "runs",
) -> Path | None:
    """Package submission directory for a workflow.

    Creates submission/ with manuscript.tex, references.bib, figures/, supplementary/.
    Runs pdflatex to produce manuscript.pdf.

    Returns Path to submission/ directory, or None if workflow not found.
    """
    info = await _get_run_info(run_root, workflow_id)
    if info is None:
        return None
    db_path, output_dir, _log_dir = info
    output_path = Path(output_dir)
    manuscript_md = output_path / "doc_manuscript.md"
    if not manuscript_md.exists():
        return None

    submission_dir = output_path / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = submission_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    supp_dir = submission_dir / "supplementary"
    supp_dir.mkdir(exist_ok=True)

    citekeys: set[str] = set()
    async with get_db(db_path) as db:
        citation_repo = CitationRepository(db)
        citations = await citation_repo.get_all_citations_for_export()
        citekeys = {c[1] for c in citations}

    bib_content = build_bibtex(citations)
    (submission_dir / "references.bib").write_text(bib_content, encoding="utf-8")

    figure_paths: list[str] = []
    _figure_names = [
        "fig_prisma_flow.png",
        "fig_rob_traffic_light.png",
        "fig_rob2_traffic_light.png",
        "fig_publication_timeline.png",
        "fig_geographic_distribution.png",
        "fig_forest_plot.png",
        "fig_funnel_plot.png",
        "fig_forest_plot.svg",
        "fig_publication_timeline.svg",
        "fig_geographic_distribution.svg",
        "fig_concept_taxonomy.svg",
        "fig_conceptual_framework.svg",
        "fig_methodology_flow.svg",
        "fig_evidence_network.png",
        "fig_evidence_network.svg",
    ]
    for fig_name in _figure_names:
        src = output_path / fig_name
        if src.exists():
            dst = figures_dir / fig_name
            shutil.copy2(src, dst)
            figure_paths.append(fig_name)

    _author_name = ""
    try:
        from src.config.loader import load_configs as _load_cfgs

        _review_cfg, _ = _load_cfgs()
        _author_name = str(getattr(_review_cfg, "author_name", "") or "")
    except Exception:
        pass

    md_content = manuscript_md.read_text(encoding="utf-8")
    num_to_citekey = _build_number_to_citekey(md_content, citations)
    latex_content = markdown_to_latex(
        md_content,
        citekeys=citekeys,
        figure_paths=figure_paths,
        num_to_citekey=num_to_citekey,
        author_name=_author_name,
    )
    manuscript_tex = submission_dir / "manuscript.tex"
    manuscript_tex.write_text(latex_content, encoding="utf-8")

    await _export_screening_decisions(db_path, workflow_id, supp_dir / "screening_decisions.csv")
    await _export_extraction_records(db_path, workflow_id, supp_dir / "extracted_data.csv")

    (supp_dir / "cover_letter.md").write_text(
        "# Cover Letter\n\n[Add cover letter content here.]\n",
        encoding="utf-8",
    )
    search_appendix_md = output_path / "doc_search_strategies_appendix.md"
    if search_appendix_md.exists():
        _generate_search_appendix_pdf(search_appendix_md, supp_dir / "search_strategies_appendix.pdf")
    else:
        (supp_dir / "search_strategies_appendix.pdf").write_bytes(b"")
    (supp_dir / "prisma_checklist.pdf").write_bytes(b"")

    if _run_pdflatex(manuscript_tex, submission_dir):
        pass

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, generate_docx, manuscript_md, submission_dir / "manuscript.docx")
    except Exception:
        pass  # docx generation is best-effort; do not fail the whole export

    return submission_dir
