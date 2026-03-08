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
# Unresolved citekey cleanup
# ---------------------------------------------------------------------------
# Matches author-year citekeys like [Mounir2020], [Mounir2020; Margaux2021],
# [lise2013; Tomoki2022], [Bryan2016; Hisham2021; NANDINI2023].
# These survived numbered-citation conversion because they were not in the
# citation ledger. We strip them to keep prose clean for journal submission.
# Matches ASCII and non-ASCII author-year citekeys (e.g. [Smith2023], [Perez-Encinas2020SR]).
# Accepts: Unicode word characters, hyphens (compound surnames), underscores, colons.
# The \d{4} anchor ensures we only strip author-year patterns, not figure/table labels.
_AUTHOR_YEAR_KEY_RE = re.compile(
    r"\[[\w][\w0-9_:.-]*\d{4}[A-Za-z]*(?:;\s*[\w][\w0-9_:.-]*\d{4}[A-Za-z]*)*\]",
    re.UNICODE,
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


def _remove_protocol_from_results_opening(body: str) -> str:
    """Remove the protocol non-registration sentence from the Results section opening.

    The LLM sometimes places "We did not register a protocol for this systematic
    review." at the very start of the Results section.  This is Methods-level
    content; it is already present in the Declarations block.  Strip the sentence
    (and any immediately following blank line) when it appears within 600
    characters of the ## Results heading.
    """
    results_re = re.compile(r"(## Results\s*\n)", re.IGNORECASE)
    m = results_re.search(body)
    if not m:
        return body
    # Look at the 600 chars immediately after the heading
    window_start = m.end()
    window_end = window_start + 600
    window = body[window_start:window_end]
    protocol_re = re.compile(
        r"We did not register a protocol[^.]*\.\s*",
        re.IGNORECASE,
    )
    cleaned_window = protocol_re.sub("", window, count=1)
    return body[:window_start] + cleaned_window + body[window_end:]


def _add_ai_screening_disclosure(body: str) -> str:
    """Insert an AI-assisted screening disclosure sentence in the Methods section.

    Finds the first occurrence of a sentence containing "two independent reviewers"
    (the neutral phrasing produced by _sanitize_body) and appends a disclosure
    sentence immediately after it.  Safe to call multiple times: the sentence is
    only inserted once (idempotent check via the disclosure text itself).
    """
    disclosure = "Screening was conducted using an AI-assisted dual-reviewer pipeline."
    if disclosure in body:
        return body
    target_re = re.compile(
        r"(two independent reviewers[^.!?]*[.!?])",
        re.IGNORECASE,
    )
    return target_re.sub(r"\1 " + disclosure, body, count=1)


def _inject_imrad_headings(body: str) -> str:
    """Inject missing H2 IMRaD headings into an existing LLM-generated body."""
    body = re.sub(
        r"(?m)^(This systematic review follows the Preferred Reporting Items)",
        r"## Methods\n\n\1",
        body,
        count=1,
    )
    body = re.sub(r"(?m)^### \*\*Results\*\*\s*$", "## Results", body)
    body = re.sub(
        r"(?m)^(?<!## Discussion\n\n)(### Principal Findings)",
        r"## Discussion\n\n\1",
        body,
        count=1,
    )
    body = re.sub(r"(?m)^## Discussion\n+## Discussion\n", "## Discussion\n", body)
    body = re.sub(
        r"(\*\*(?:Funding|Protocol Registration|Keywords)[^\n]*\n)(\n)([A-Z])",
        r"\1\n## Introduction\n\n\3",
        body,
        count=1,
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
    full_text = manuscript_path.read_text(encoding="utf-8")

    # Preserve the existing References section BEFORE stripping so it can be
    # re-used when the body is already numbered (idempotent re-run case).
    # This avoids a numbering mismatch between the body's [N] citations and
    # a freshly-built reference list that uses DB insertion order.
    _original_refs_section = ""
    _refs_marker_re = re.compile(r"\n\n---\n\n## References\n\n(.+?)(?=\n\n---\n\n|\Z)", re.DOTALL)
    _refs_plain_re = re.compile(r"\n\n## References\n\n(.+?)(?=\n\n---\n\n|\Z)", re.DOTALL)
    for _pat in (_refs_marker_re, _refs_plain_re):
        _m = _pat.search(full_text)
        if _m:
            _original_refs_section = "## References\n\n" + _m.group(1).rstrip()
            break

    body = strip_appended_sections(full_text)
    body = _inject_imrad_headings(body)
    body = _add_ai_screening_disclosure(body)
    body = _remove_protocol_from_results_opening(body)

    # Post-process: replace raw paper_id UUID fragments in the Conflicting Evidence
    # section with citekey labels. This handles runs where the section was written
    # before the paper_id_to_label fix was applied, so re-running finalize fixes them.
    _uuid_fragment_re = re.compile(r"`([0-9a-f]{8}-[0-9a-f]{3,4})`")

    artifacts = {key: str(run_path / filename) for key, filename in ARTIFACT_MAP.items()}

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        citation_rows = await CitationRepository(db).get_all_citations_for_export()

        cursor = await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
        row = await cursor.fetchone()
        workflow_id = str(row[0]) if row else None

        papers = []
        extraction_records = []
        grade_assessments = []

        robins_i_assessments = []
        casp_assessments = []
        mmat_assessments = []
        paper_id_to_citekey: dict[str, str] = {}
        if workflow_id:
            extraction_records = await repo.load_extraction_records(workflow_id)
            included_ids = {r.paper_id for r in extraction_records}
            if not included_ids:
                included_ids = await repo.get_included_paper_ids(workflow_id)
            papers = await repo.load_papers_by_ids(included_ids)

            grade_assessments = await repo.load_grade_assessments(workflow_id)
            _rob2_rows, robins_i_assessments = await repo.load_rob_assessments(workflow_id)
            casp_assessments = await repo.load_casp_assessments(workflow_id)
            mmat_assessments = await repo.load_mmat_assessments(workflow_id)
            paper_id_to_citekey = await repo.get_paper_id_to_citekey_map()

    # Replace UUID fragments in Conflicting Evidence section with citekey labels.
    # This post-processes old runs where labels were not yet applied during writing.
    if paper_id_to_citekey:

        def _replace_uuid(m: re.Match) -> str:
            uid = m.group(1)
            return f"`{paper_id_to_citekey.get(uid, uid)}`"

        # Only replace within the Conflicting Evidence subsection to avoid
        # touching UUIDs that might appear legitimately elsewhere.
        _ce_start = body.find("### Conflicting Evidence")
        _ce_end = body.find("\n### ", _ce_start + 1) if _ce_start >= 0 else -1
        if _ce_start >= 0:
            _ce_slice = body[_ce_start:_ce_end] if _ce_end > _ce_start else body[_ce_start:]
            _ce_fixed = _uuid_fragment_re.sub(_replace_uuid, _ce_slice)
            body = body[:_ce_start] + _ce_fixed + (body[_ce_end:] if _ce_end > _ce_start else "")

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
    print(f"Found {len(casp_assessments)} CASP assessment(s), {len(mmat_assessments)} MMAT assessment(s).")
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
            protocol_data = config_data.get("protocol") or {}
            funding_data = config_data.get("funding") or {}
            review_config = SimpleNamespace(
                pico=SimpleNamespace(
                    population=pico_data.get("population", ""),
                    intervention=pico_data.get("intervention", ""),
                    comparison=pico_data.get("comparison", ""),
                    outcome=pico_data.get("outcome", ""),
                ),
                inclusion_criteria=config_data.get("inclusion_criteria", []),
                exclusion_criteria=config_data.get("exclusion_criteria", []),
                date_range_start=config_data.get("date_range_start"),
                date_range_end=config_data.get("date_range_end"),
                review_type=config_data.get("review_type", "systematic"),
                author_name=config_data.get("author_name", ""),
                protocol=SimpleNamespace(
                    registered=bool(protocol_data.get("registered", False)),
                    registration_number=str(protocol_data.get("registration_number") or ""),
                ),
                funding=SimpleNamespace(
                    source=funding_data.get("source", ""),
                ),
                conflicts_of_interest=config_data.get("conflicts_of_interest", ""),
            )
        except Exception:
            pass

    # Build set of paper_ids that have a full-text file on disk for the
    # "Full Text Retrieved" column in Appendix B.
    # Primary: read from data_papers_manifest.json, resolving relative paths
    # relative to the manifest's own directory (not the process cwd).
    # Fallback: scan run_path/papers/ directly for {paper_id}.pdf/.txt files,
    # which handles runs where the manifest was not written or its file paths
    # were stored relative to a different working directory.
    _manifest_path = run_path / "data_papers_manifest.json"
    _fulltext_paper_ids: set[str] = set()
    if _manifest_path.exists():
        try:
            import json as _json

            _manifest_dir = _manifest_path.parent
            _manifest_data = _json.loads(_manifest_path.read_text(encoding="utf-8"))
            for _pid, _entry in _manifest_data.items():
                _fp_raw = (_entry or {}).get("file_path", "")
                if not _fp_raw:
                    continue
                _fp = pathlib.Path(_fp_raw)
                if not _fp.is_absolute():
                    _fp_resolved = (_manifest_dir / _fp_raw).resolve()
                    if not _fp_resolved.exists():
                        _fp_resolved = pathlib.Path(_fp_raw)
                else:
                    _fp_resolved = _fp
                if _fp_resolved.exists() and _fp_resolved.stat().st_size > 0:
                    _fulltext_paper_ids.add(str(_pid))
        except Exception as _manifest_err:
            print(f"Warning: could not read papers manifest: {_manifest_err}")
    # Fallback: scan papers/ directory directly
    if not _fulltext_paper_ids:
        _papers_dir = run_path / "papers"
        if _papers_dir.exists():
            for _pf in _papers_dir.iterdir():
                if _pf.suffix in {".pdf", ".txt"} and _pf.stat().st_size > 0:
                    _fulltext_paper_ids.add(_pf.stem)
    if _fulltext_paper_ids:
        print(f"Found {len(_fulltext_paper_ids)} paper(s) with full-text files.")

    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=citation_rows,
        papers=clean_papers,
        extraction_records=clean_records,
        grade_assessments=grade_assessments if grade_assessments else None,
        robins_i_assessments=robins_i_assessments if robins_i_assessments else None,
        casp_assessments=casp_assessments if casp_assessments else None,
        mmat_assessments=mmat_assessments if mmat_assessments else None,
        paper_id_to_citekey=paper_id_to_citekey if paper_id_to_citekey else None,
        review_config=review_config,
        failed_count=failed_count,
        search_appendix_path=_search_appendix_path if _search_appendix_path.exists() else None,
        research_question=research_question,
        title=None,
        fulltext_paper_ids=_fulltext_paper_ids if _fulltext_paper_ids else None,
    )

    # Strip any surviving unresolved [AuthorYear] citekeys (hallucinated or ledger gaps)
    full_manuscript = _strip_unresolved_citekeys(full_manuscript)

    # Idempotency fix: if the assembled manuscript is missing a References section
    # (because the body was already numbered from a prior run and no [AuthorYear]
    # citekeys were found), restore the original References section that was
    # extracted before stripping.  This preserves exact [N] -> paper mapping.
    if _original_refs_section and "## References" not in full_manuscript:
        full_manuscript = full_manuscript.rstrip() + "\n\n---\n\n" + _original_refs_section

    manuscript_path.write_text(full_manuscript, encoding="utf-8")
    print(f"Done. Updated {manuscript_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate appended sections in an existing doc_manuscript.md")
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing doc_manuscript.md and runtime.db",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.run_dir)))
