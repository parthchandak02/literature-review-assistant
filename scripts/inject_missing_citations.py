#!/usr/bin/env python3
"""Inject missing included-study citations into any completed run's manuscript.

Works on any literature review topic. Does NOT make paper-specific assumptions.

The problem this solves: the writing LLM sometimes omits included-study citekeys
from the manuscript prose. This script:
  1. Reads ALL section_drafts from the run DB (in [AuthorYear] format).
  2. Computes which included-study citekeys are not cited in any draft.
  3. Groups uncited keys into compact citation clusters.
  4. Patches the Results section_draft (before ### Risk of Bias) and saves to DB.
  5. Re-assembles doc_manuscript.md from ALL section_drafts (not from the .md file).
  6. Regenerates doc_manuscript.tex and references.bib from the updated .md.

Usage:
    uv run python scripts/inject_missing_citations.py --run-dir <path-to-run-directory>

Example:
    uv run python scripts/inject_missing_citations.py \\
        --run-dir runs/2026-03-08/wf-0004-.../run_10-41-36PM

The script is idempotent: re-running it will not double-inject citations.

Backward compatibility: For run DBs that predate the source_type column (before
the Robust Citation Pipeline fix), the script identifies methodology keys using
a hardcoded pattern set (known methodology citekey names + background SR suffix
'SR') and excludes them from the required coverage check.
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
from src.export.bibtex_builder import build_bibtex
from src.export.ieee_latex import markdown_to_latex
from src.export.markdown_refs import (
    assemble_submission_manuscript,
    is_extraction_failed,
    strip_appended_sections,
)
from src.export.submission_packager import _build_number_to_citekey, llm_resolve_unmatched_citations
from src.writing.prompts.sections import SECTIONS

# Methodology citekeys that must NOT be counted as "missing" included-study refs.
# This set covers runs produced before the source_type column was added.
_FALLBACK_METHODOLOGY_KEYS: frozenset[str] = frozenset(
    {
        "Page2021",
        "Sterne2019",
        "Sterne2016",
        "Guyatt2011",
        "Cohen1960",
    }
)

# IMRaD headings identical to WritingNode in workflow.py
_SECTION_HEADINGS: dict[str, str] = {
    "abstract": "",
    "introduction": "## Introduction",
    "methods": "## Methods",
    "results": "## Results",
    "discussion": "## Discussion",
    "conclusion": "## Conclusion",
}

# Sentinel inserted into patched drafts so re-runs are idempotent.
_SENTINEL = "<!-- CITATION_COVERAGE_INJECTED -->"

# Artifact paths relative to the run directory (mirrors finalize_manuscript.py).
ARTIFACT_MAP: dict[str, str] = {
    "prisma_flow": "fig_prisma_flow.png",
    "rob_traffic_light": "fig_rob2_traffic_light.png",
    "rob_traffic_light_svg": "fig_rob2_traffic_light.svg",
    "forest_plot": "fig_forest_plot.png",
    "funnel_plot": "fig_funnel_plot.png",
    "publication_timeline": "fig_publication_timeline.png",
    "geographic_distribution": "fig_geographic_distribution.png",
    "evidence_network": "fig_evidence_network.png",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_uncited_included_keys(
    all_drafts_text: str,
    all_db_keys: list[str],
    source_type_map: dict[str, str],
) -> list[str]:
    """Return included-study citekeys that appear in the DB but not in any section draft.

    source_type_map: {citekey -> source_type} from the citations table.
    Falls back to the _FALLBACK_METHODOLOGY_KEYS set for older DBs.

    Even when source_type_map is present, the fallback heuristics are applied as a
    belt-and-suspenders safety net: keys in _FALLBACK_METHODOLOGY_KEYS or ending in
    'SR' are always excluded regardless of what the DB says.  This guards against
    the case where the ensure_schema() retroactive UPDATE ran but the key was already
    present before the migration (old DBs may still have 'included' as source_type
    for methodology keys if ensure_schema was not called in this session).
    """
    cited = set(re.findall(r"\[([A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?)\]", all_drafts_text))
    uncited = []
    for key in sorted(all_db_keys):
        if key in cited:
            continue
        # Hard-exclude known methodology and background SR keys regardless of DB value.
        if key in _FALLBACK_METHODOLOGY_KEYS:
            continue
        if key.endswith("SR"):
            continue
        # Use DB source_type when available.
        if source_type_map:
            st = source_type_map.get(key, "included")
            if st != "included":
                continue  # methodology or background_sr set by the registration functions
        uncited.append(key)
    return uncited


def _build_coverage_paragraph(uncited_keys: list[str]) -> str:
    """Build a paragraph that groups uncited keys as citation clusters.

    Uses chunks of 8 to keep lines readable. Returns empty string if no keys.
    """
    if not uncited_keys:
        return ""
    _CHUNK = 8
    groups = [uncited_keys[i : i + _CHUNK] for i in range(0, len(uncited_keys), _CHUNK)]
    cite_clusters = "; ".join("[" + ", ".join(g) + "]" for g in groups)
    return (
        f"{_SENTINEL}\n"
        "Additional included studies contributing to the evidence base are acknowledged "
        f"here for complete citation coverage: {cite_clusters}."
    )


def _patch_results_draft(draft: str, coverage_paragraph: str) -> str:
    """Insert coverage_paragraph into the Results draft before Risk of Bias heading.

    Idempotent: if sentinel is already present, returns the draft unchanged.
    """
    if _SENTINEL in draft:
        return draft  # already patched
    _rob_marker = "### Risk of Bias"
    if _rob_marker in draft:
        return draft.replace(_rob_marker, coverage_paragraph + "\n\n" + _rob_marker, 1)
    # Fallback: append at end of draft
    return draft.rstrip() + "\n\n" + coverage_paragraph


def _assemble_body_from_drafts(section_drafts: dict[str, str]) -> str:
    """Build the IMRaD body from section_drafts in canonical section order.

    This reads from the DB drafts ([AuthorYear] format), not from doc_manuscript.md
    ([N] format). This ensures uncited keys injected into the draft survive the
    convert_to_numbered_citations step in assemble_submission_manuscript.
    """
    titled: list[str] = []
    for section in SECTIONS:
        content = section_drafts.get(section, "")
        if not content:
            continue
        heading = _SECTION_HEADINGS.get(section, "")
        titled.append(f"{heading}\n\n{content}" if heading else content)
    return "\n\n".join(titled)


# ---------------------------------------------------------------------------
# Main async logic
# ---------------------------------------------------------------------------


async def main(run_dir_str: str) -> int:
    run_path = pathlib.Path(run_dir_str).resolve()
    db_path = run_path / "runtime.db"
    manuscript_path = run_path / "doc_manuscript.md"
    tex_path = run_path / "doc_manuscript.tex"
    bib_path = run_path / "references.bib"

    if not db_path.exists():
        print(f"ERROR: runtime.db not found in {run_path}")
        return 1
    if not manuscript_path.exists():
        print(f"ERROR: doc_manuscript.md not found in {run_path}")
        return 1

    # ------------------------------------------------------------------
    # 1. Load everything from the DB
    # ------------------------------------------------------------------
    async with get_db(str(db_path)) as db:
        citation_repo = CitationRepository(db)
        # Run migration so old DBs get source_type column.
        await citation_repo.ensure_schema()

        all_citekeys = await citation_repo.get_citekeys()
        citation_rows = await citation_repo.get_all_citations_for_export()

        # Build source_type map (may be empty for very old DBs)
        try:
            _st_cur = await db.execute("SELECT citekey, source_type FROM citations")
            _st_rows = await _st_cur.fetchall()
            source_type_map = {str(r[0]): str(r[1]) for r in _st_rows}
        except Exception:
            source_type_map = {}

        # Load section_drafts (latest version per section)
        cursor = await db.execute(
            """
            SELECT section, content
            FROM section_drafts
            WHERE (section, version) IN (
                SELECT section, MAX(version) FROM section_drafts GROUP BY section
            )
            """
        )
        rows = await cursor.fetchall()
        section_drafts: dict[str, str] = {str(r[0]): str(r[1]) for r in rows}

        # Load workflow_id for subsequent queries
        _wf_cur = await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
        _wf_row = await _wf_cur.fetchone()
        workflow_id = str(_wf_row[0]) if _wf_row else None

        repo = WorkflowRepository(db)
        extraction_records: list = []
        papers: list = []
        grade_assessments: list = []
        robins_i_assessments: list = []
        casp_assessments: list = []
        mmat_assessments: list = []
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

    if not section_drafts:
        print("ERROR: No section_drafts found in DB. Run may not have completed the writing phase.")
        return 1

    # ------------------------------------------------------------------
    # 2. Find uncited included-study keys
    # ------------------------------------------------------------------
    all_drafts_text = " ".join(section_drafts.values())
    uncited = _find_uncited_included_keys(all_drafts_text, all_citekeys, source_type_map)

    print(f"Total citekeys in DB: {len(all_citekeys)}")
    print(f"Uncited included-study keys: {len(uncited)}")
    if uncited:
        for k in uncited:
            print(f"  - {k}")

    # ------------------------------------------------------------------
    # 3. Patch results section_draft if needed
    # ------------------------------------------------------------------
    coverage_paragraph = _build_coverage_paragraph(uncited)

    if uncited:
        results_draft = section_drafts.get("results", "")
        if _SENTINEL in results_draft:
            print("Results draft already patched (sentinel present). Skipping DB update.")
        else:
            patched_results = _patch_results_draft(results_draft, coverage_paragraph)
            section_drafts["results"] = patched_results

            # Persist to DB
            async with get_db(str(db_path)) as db:
                await db.execute(
                    "UPDATE section_drafts SET content=? WHERE section='results'",
                    (patched_results,),
                )
                await db.commit()
            print("Results section_draft patched and saved to DB.")
    else:
        print("All included-study keys already cited. No patch needed.")

    # ------------------------------------------------------------------
    # 4. Load review config for assembly
    # ------------------------------------------------------------------
    review_yaml_path = run_path / "review.yaml"
    config_snapshot_path = run_path / "config_snapshot.yaml"
    research_question = ""
    review_config = None

    for cfg_path in (config_snapshot_path, review_yaml_path):
        if cfg_path.exists():
            try:
                config_data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                research_question = research_question or config_data.get("research_question", "") or ""
                if review_config is None:
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
                        funding=SimpleNamespace(source=funding_data.get("source", "")),
                        conflicts_of_interest=config_data.get("conflicts_of_interest", ""),
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 5. Re-assemble body from section_drafts ([AuthorYear] format)
    # ------------------------------------------------------------------
    body = _assemble_body_from_drafts(section_drafts)

    clean_records = [r for r in extraction_records if not is_extraction_failed(r)]
    failed_count = len(extraction_records) - len(clean_records)
    clean_paper_ids = {r.paper_id for r in clean_records}
    clean_papers = [p for p in papers if p.paper_id in clean_paper_ids]

    artifacts = {key: str(run_path / filename) for key, filename in ARTIFACT_MAP.items()}

    _search_appendix_path = run_path / "doc_search_strategies_appendix.md"

    # Build set of paper_ids that have full-text on disk
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
                _fp_resolved = (_manifest_dir / _fp_raw).resolve() if not _fp.is_absolute() else _fp
                if _fp_resolved.exists() and _fp_resolved.stat().st_size > 0:
                    _fulltext_paper_ids.add(str(_pid))
        except Exception:
            pass
    if not _fulltext_paper_ids:
        _papers_dir = run_path / "papers"
        if _papers_dir.exists():
            for _f in _papers_dir.iterdir():
                if _f.suffix in {".pdf", ".txt"} and _f.stat().st_size > 0:
                    _fulltext_paper_ids.add(_f.stem)

    print(f"Re-assembling manuscript from {len(section_drafts)} section_drafts...")

    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=citation_rows,
        papers=clean_papers,
        extraction_records=clean_records,
        grade_assessments=grade_assessments,
        robins_i_assessments=robins_i_assessments,
        casp_assessments=casp_assessments,
        mmat_assessments=mmat_assessments,
        paper_id_to_citekey=paper_id_to_citekey if paper_id_to_citekey else None,
        review_config=review_config,
        failed_count=failed_count,
        search_appendix_path=_search_appendix_path if _search_appendix_path.exists() else None,
        research_question=research_question,
    )

    manuscript_path.write_text(full_manuscript, encoding="utf-8")
    print(f"doc_manuscript.md written ({len(full_manuscript):,} chars)")

    # ------------------------------------------------------------------
    # 6. Regenerate .tex and .bib
    # ------------------------------------------------------------------
    md_text = manuscript_path.read_text(encoding="utf-8")
    _citekeys = {c[1] for c in citation_rows}
    # Three mechanical layers (DOI -> URL -> title), then LLM batch fallback.
    num_to_citekey = _build_number_to_citekey(md_text, citation_rows)
    print("Running LLM fallback resolver for any remaining unmatched citations...")
    num_to_citekey = await llm_resolve_unmatched_citations(
        md_text,
        citation_rows,
        num_to_citekey,
        db_path=str(db_path),
        workflow_id=workflow_id,
    )

    _author_name = str(getattr(review_config, "author_name", "") or "") if review_config else ""
    tex_content = markdown_to_latex(
        md_text, citekeys=_citekeys, num_to_citekey=num_to_citekey, author_name=_author_name
    )
    tex_path.write_text(tex_content, encoding="utf-8")
    print(f"doc_manuscript.tex written ({len(tex_content):,} chars)")

    bib_content = build_bibtex(citation_rows)
    bib_path.write_text(bib_content, encoding="utf-8")
    print(f"references.bib written ({len(bib_content):,} chars)")

    # ------------------------------------------------------------------
    # 7. Report final citation coverage
    # ------------------------------------------------------------------
    all_drafts_after = manuscript_path.read_text(encoding="utf-8")
    import re as _re2

    cited_in_tex = set()
    for raw in _re2.findall(r"\\cite\{([^}]+)\}", tex_content):
        for k in raw.split(","):
            cited_in_tex.add(k.strip())
    still_uncited = [k for k in uncited if k not in cited_in_tex]
    print(f"\nCoverage report:")
    print(f"  Uncited before: {len(uncited)}")
    print(f"  Uncited after:  {len(still_uncited)}")
    if still_uncited:
        print("  Still missing (likely no DOI/URL for roundtrip):")
        for k in still_uncited:
            print(f"    - {k}")
    else:
        print("  All included-study keys now appear in manuscript.tex [OK]")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inject missing included-study citations into a completed run's manuscript."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing runtime.db and doc_manuscript.md",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.run_dir)))
