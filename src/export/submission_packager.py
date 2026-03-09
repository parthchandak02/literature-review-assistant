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


def _normalize_title_for_match(title: str) -> str:
    """Return a lowercase, punctuation-stripped version of a title for fuzzy matching."""
    import string

    return title.lower().translate(str.maketrans("", "", string.punctuation)).split()[:8]


def _build_number_to_citekey(
    md_content: str,
    citations: list[tuple],
) -> dict[str, str]:
    """Build mapping from [N] to citekey by parsing References section.

    Manuscripts use numbered refs [1], [2]. References section lists [N] Author... doi: URL.
    Uses three-layer fallback to handle papers without DOIs:
    1. DOI match (primary)
    2. URL match (for ClinicalTrials, arXiv, preprints, etc.)
    3. Title-based fuzzy match (for papers with neither DOI nor URL)

    Returns {str(N): citekey} for all successfully mapped entries.
    """
    doi_to_citekey: dict[str, str] = {}
    url_to_citekey: dict[str, str] = {}
    title_words_to_citekey: dict[str, str] = {}
    for row in citations:
        citekey = str(row[1])
        doi = row[2]
        url = row[8] if len(row) > 8 else None
        title = row[3] if len(row) > 3 else ""
        if doi:
            norm = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip().rstrip(".,")
            doi_to_citekey[norm] = citekey
        if url:
            url_norm = str(url).strip().rstrip("/")
            url_to_citekey[url_norm] = citekey
        if title:
            # Index first 8 words of title for approximate matching
            title_key = " ".join(_normalize_title_for_match(str(title)))
            if title_key and title_key not in title_words_to_citekey:
                title_words_to_citekey[title_key] = citekey

    in_refs = False
    num_to_citekey: dict[str, str] = {}
    ref_num_re = re.compile(r"^\[(\d+)\]\s+")
    doi_re = re.compile(r"doi:\s*(https?://doi\.org/)?([^\s\)\]]+)")
    url_re = re.compile(r"https?://[^\s\)\]]+")
    # Capture quoted title: e.g. "Some title text,"
    title_re = re.compile(r'"([^"]{8,120})"')

    for line in md_content.split("\n"):
        if line.strip().startswith("## References") or line.strip() == "## References":
            in_refs = True
            continue
        if in_refs and line.strip().startswith("## "):
            break
        if not in_refs:
            continue
        m = ref_num_re.match(line)
        if not m:
            continue
        num = m.group(1)
        if num in num_to_citekey:
            continue

        # Layer 1: DOI match
        doi_match = doi_re.search(line)
        if doi_match:
            norm_doi = doi_match.group(2).rstrip(".,")
            if norm_doi in doi_to_citekey:
                num_to_citekey[num] = doi_to_citekey[norm_doi]
                continue

        # Layer 2: URL match (catches ClinicalTrials, arXiv, GitHub, etc.)
        url_matches = url_re.findall(line)
        for raw_url in url_matches:
            url_norm = raw_url.rstrip("/.,)").rstrip()
            if url_norm in url_to_citekey:
                num_to_citekey[num] = url_to_citekey[url_norm]
                break
        if num in num_to_citekey:
            continue

        # Layer 3: Title-based fuzzy match (last resort for grey literature)
        title_match = title_re.search(line)
        if title_match:
            candidate_words = " ".join(_normalize_title_for_match(title_match.group(1)))
            if candidate_words and candidate_words in title_words_to_citekey:
                num_to_citekey[num] = title_words_to_citekey[candidate_words]

    return num_to_citekey


# ---------------------------------------------------------------------------
# Layer 4: LLM batch citation resolver (last-resort fallback)
# ---------------------------------------------------------------------------

_CITATION_MATCH_SYSTEM = (
    "You are a bibliography matching assistant for a systematic literature review.\n"
    "Your task: match each numbered reference entry to the correct citekey from the provided database.\n\n"
    "RESPONSE FORMAT: Return ONLY a valid JSON object where keys are reference numbers (as strings)\n"
    "and values are exact citekeys from the database. Example: {\"3\": \"Brown2021\", \"7\": \"ClinTrial2019\"}\n\n"
    "RULES:\n"
    "- Match only when confident (>=85% certainty based on author, year, and title similarity).\n"
    "- Omit entries where you cannot find a confident match -- do NOT guess.\n"
    "- Never invent citekeys not present in the database.\n"
    "- If two reference entries could plausibly match the same citekey, pick the closest one and omit the other.\n"
    "- Return an empty JSON object {} if no confident matches can be made."
)

_CITATION_MATCH_USER_TEMPLATE = """\
## UNMATCHED REFERENCE ENTRIES ({n_unmatched} entries)

These reference lines could not be resolved via DOI, URL, or title matching:

{unmatched_lines}

## CITATION DATABASE ({n_db} entries)

| Citekey | Authors | Year | Title |
|---------|---------|------|-------|
{db_table}

## TASK

Match each unmatched reference entry [N] to its citekey in the database.
Return ONLY the JSON mapping. Omit entries where you are not confident.
"""


def _format_citation_db_table(citations: list[tuple]) -> str:
    """Format citations DB as a compact pipe table for the LLM prompt."""
    rows: list[str] = []
    for row in citations:
        citekey = str(row[1])
        title = str(row[3] or "")[:80].replace("|", " ")
        try:
            authors_raw = json.loads(str(row[4] or "[]"))
            first_author = str(authors_raw[0]) if authors_raw else ""
        except Exception:
            first_author = str(row[4] or "")[:40]
        year = str(row[5] or "")
        rows.append(f"| {citekey} | {first_author[:40]} | {year} | {title} |")
    return "\n".join(rows)


async def llm_resolve_unmatched_citations(
    md_content: str,
    citations: list[tuple],
    num_to_citekey: dict[str, str],
    *,
    db_path: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, str]:
    """LLM batch fallback: resolve [N] -> citekey for entries not matched mechanically.

    Collects all reference lines that are still unmapped after the three mechanical
    layers (DOI, URL, title) and sends them in a SINGLE LLM call alongside the full
    citations database. The LLM returns a JSON mapping {num: citekey} for any it
    can confidently identify.

    This is intentionally a non-blocking best-effort step: if the LLM call fails or
    returns an unparseable response, the existing num_to_citekey is returned unchanged.

    Args:
        md_content: The full doc_manuscript.md text (for parsing the References section).
        citations: All citation_rows from the DB (9-element tuples).
        num_to_citekey: Already-resolved mapping from mechanical layers (mutated in place).
        db_path: Optional path to runtime.db for cost logging.
        workflow_id: Optional workflow ID for cost logging.

    Returns:
        Enriched num_to_citekey dict (same reference as input, with new keys added).
    """
    import logging

    logger = logging.getLogger(__name__)

    # --- Collect unmapped reference lines ---
    in_refs = False
    unmatched: list[tuple[str, str]] = []  # [(num, line_text), ...]
    ref_num_re = re.compile(r"^\[(\d+)\]\s+")
    for line in md_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## References") or stripped == "## References":
            in_refs = True
            continue
        if in_refs and stripped.startswith("## "):
            break
        if not in_refs:
            continue
        m = ref_num_re.match(line)
        if m:
            num = m.group(1)
            if num not in num_to_citekey:
                unmatched.append((num, line.strip()))

    if not unmatched:
        return num_to_citekey  # nothing to resolve

    logger.info(
        "LLM citation resolver: %d unmatched reference entries will be sent to LLM batch call",
        len(unmatched),
    )

    # --- Build prompt ---
    unmatched_lines_str = "\n".join(f"[{num}] {text}" for num, text in unmatched)
    db_table = _format_citation_db_table(citations)

    prompt = (
        _CITATION_MATCH_SYSTEM
        + "\n\n"
        + _CITATION_MATCH_USER_TEMPLATE.format(
            n_unmatched=len(unmatched),
            unmatched_lines=unmatched_lines_str,
            n_db=len(citations),
            db_table=db_table,
        )
    )

    # --- Load model from settings ---
    model_name = ""
    try:
        from src.config.loader import load_configs

        _, settings = load_configs(settings_path="config/settings.yaml")
        agent_cfg = settings.agents.get("citation_matching")
        model_name = agent_cfg.model if agent_cfg else ""
    except Exception:
        pass
    if not model_name:
        from src.llm.model_fallback import get_fallback_model

        model_name = get_fallback_model("lite")

    # --- Call LLM with JSON schema enforcement ---
    _json_schema = {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }
    try:
        from src.llm.pydantic_client import PydanticAIClient

        client = PydanticAIClient(timeout_seconds=60.0)
        raw_json, tokens_in, tokens_out, _, _ = await client.complete_with_usage(
            prompt,
            model=model_name,
            temperature=0.0,
            json_schema=_json_schema,
        )

        # --- Parse and validate response ---
        import ast

        try:
            resolved: dict = json.loads(raw_json)
        except json.JSONDecodeError:
            try:
                resolved = ast.literal_eval(raw_json)
            except Exception:
                logger.warning("LLM citation resolver: could not parse JSON response -- skipping")
                return num_to_citekey

        valid_citekeys = {str(row[1]) for row in citations}
        n_resolved = 0
        for num_str, citekey in resolved.items():
            num_str = str(num_str).strip()
            citekey = str(citekey).strip()
            if num_str not in num_to_citekey and citekey in valid_citekeys:
                num_to_citekey[num_str] = citekey
                n_resolved += 1

        logger.info(
            "LLM citation resolver: resolved %d additional entries (model=%s, tokens_in=%d, tokens_out=%d)",
            n_resolved,
            model_name,
            tokens_in,
            tokens_out,
        )

        # --- Log cost to cost_records if possible ---
        if db_path and workflow_id and (tokens_in + tokens_out) > 0:
            try:
                _cost_per_1m_in = 0.0001  # flash-lite approximate
                _cost_per_1m_out = 0.0004
                _cost_usd = (tokens_in * _cost_per_1m_in + tokens_out * _cost_per_1m_out) / 1_000_000

                async with get_db(db_path) as _cost_db:
                    await _cost_db.execute(
                        """
                        INSERT INTO cost_records (workflow_id, model, phase, tokens_in, tokens_out, cost_usd, latency_ms)
                        VALUES (?, ?, 'citation_matching', ?, ?, ?, 0)
                        """,
                        (workflow_id, model_name, tokens_in, tokens_out, _cost_usd),
                    )
                    await _cost_db.commit()
            except Exception as _log_exc:
                logger.debug("LLM citation resolver: cost logging failed (non-fatal): %s", _log_exc)

    except Exception as exc:
        logger.warning("LLM citation resolver: LLM call failed (non-fatal, using mechanical matches only): %s", exc)

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
        await citation_repo.ensure_schema()
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
            if not fig_name.endswith(".svg"):
                figure_paths.append(fig_name)

    # Read author_name from the run's own config_snapshot.yaml (written by StartNode)
    # so the packaged LaTeX reflects the review that was actually run, not whatever
    # review.yaml is currently loaded on disk.
    _author_name = ""
    _snapshot_path = output_path / "config_snapshot.yaml"
    if _snapshot_path.exists():
        try:
            import yaml as _yaml

            _snap = _yaml.safe_load(_snapshot_path.read_text(encoding="utf-8"))
            _author_name = str((_snap or {}).get("author_name", "") or "")
        except Exception:
            pass
    # Fallback to current review.yaml when no snapshot exists (e.g. legacy runs)
    if not _author_name:
        try:
            from src.config.loader import load_configs as _load_cfgs

            _review_cfg, _ = _load_cfgs()
            _author_name = str(getattr(_review_cfg, "author_name", "") or "")
        except Exception:
            pass

    md_content = manuscript_md.read_text(encoding="utf-8")
    # Three-layer mechanical matching (DOI -> URL -> title), then LLM batch fallback.
    num_to_citekey = _build_number_to_citekey(md_content, citations)
    num_to_citekey = await llm_resolve_unmatched_citations(
        md_content,
        citations,
        num_to_citekey,
        db_path=db_path,
        workflow_id=workflow_id,
    )
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
