"""Post-writing assembly: citation coverage, contradiction, manuscript assembly, concept/custom diagrams."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.export.markdown_refs import (
    _normalize_subsection_heading_layout,
    assemble_submission_manuscript,
    is_extraction_failed,
)
from src.llm.provider import LLMProvider
from src.models import (
    ManuscriptAssembly,
    ManuscriptAsset,
)
from src.models.diagrams import (
    DiagramPlacementPlan,
    DiagramStyleGuide,
    FlowchartDiagramInput,
    FlowchartPhase,
    FrameworkDiagramInput,
    TaxonomyCategory,
    TaxonomyDiagramInput,
)
from src.orchestration.helpers.runtime import llm_available as helper_llm_available
from src.orchestration.helpers.writing_manuscript import (
    build_citation_coverage_patch,
    replace_template_tokens,
)
from src.orchestration.state import ReviewState
from src.synthesis.contradiction_detector import detect_contradictions
from src.visualization.concept_diagrams import render_concept_diagrams
from src.visualization.research_diagram_placement import plan_inline_diagram_placements
from src.visualization.research_diagram_preparer import prepare_research_diagram_briefs
from src.visualization.research_diagram_renderer import render_custom_research_diagrams
from src.writing.citation_grounding import extract_used_citekeys, verify_citation_grounding
from src.writing.context_builder import sanitize_summary_text_for_writing
from src.writing.contradiction_resolver import build_conflicting_evidence_section, generate_contradiction_paragraph
from src.writing.prompts.sections import SECTIONS

logger = logging.getLogger(__name__)


def _rc_print(rc, message):
    from src.orchestration.helpers.runtime import rc_print as helper_rc_print

    helper_rc_print(rc, message)


def _llm_available(settings=None, settings_cfg=None):
    return helper_llm_available(settings=settings, settings_cfg=settings_cfg)


_SECTION_HEADINGS: dict[str, str] = {
    "abstract": "## Abstract",
    "introduction": "## Introduction",
    "methods": "## Methods",
    "results": "## Results",
    "discussion": "## Discussion",
    "conclusion": "## Conclusion",
}
_CANONICAL_H2_NAMES = (
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "Acknowledgments",
    "References",
)
_inline_h2_re = re.compile(
    r"\s+(##\s+(?:Abstract|Introduction|Methods|Results|Discussion|Conclusion|Acknowledgments|References)\b)",
    flags=re.IGNORECASE,
)


def _sanitize_section_body_for_assembly(section_key: str, raw_text: str) -> str:
    text = str(raw_text or "").strip()
    text = _normalize_subsection_heading_layout(text)
    text = _inline_h2_re.sub(r"\n\n\1", text)
    heading = _SECTION_HEADINGS.get(section_key, "")
    if heading:
        _name = heading.replace("## ", "").strip()
        text = re.sub(rf"(?is)^\s*##\s*{re.escape(_name)}\b[ \t]*\n?", "", text).lstrip()
    m = re.search(
        r"(?m)^##\s+(?:Abstract|Introduction|Methods|Results|Discussion|Conclusion|Acknowledgments|References)\b",
        text,
    )
    if m:
        text = text[: m.start()].rstrip()
    return text


async def run_post_assembly(
    state: ReviewState,
    *,
    sections_written: list[str],
    failed_sections: list[str],
    citation_catalog: str,
    narrative: dict | None,
    prisma_counts: Any,
    rewound_before_writing: bool,
    rc: Any | None,
    save_subphase_checkpoint: Callable,
) -> None:
    """Execute post-writing assembly: build manuscript body, citation coverage, contradictions, diagrams."""

    # --- Fetch post-loop data ---
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        citation_rows = await CitationRepository(db).get_all_citations_for_export()
        all_extraction_records = await repository.load_extraction_records(state.workflow_id)
        extraction_records_for_table = [r for r in all_extraction_records if not is_extraction_failed(r)]
        _failed_extraction_count = len(all_extraction_records) - len(extraction_records_for_table)
        included_ids = await repository.get_synthesis_included_paper_ids(state.workflow_id)
        if not included_ids:
            included_ids = {r.paper_id for r in extraction_records_for_table}
        if not included_ids:
            included_ids = await repository.get_included_paper_ids(state.workflow_id)
        included_papers_for_table = await repository.load_papers_by_ids(included_ids)

    # --- Build titled sections and body ---
    titled_sections = []
    for section, content in zip(SECTIONS, sections_written):
        content = replace_template_tokens(content, state.review)
        content = _sanitize_section_body_for_assembly(section, content)
        heading = _SECTION_HEADINGS.get(section, "")
        titled_sections.append(f"{heading}\n\n{content}" if heading else content)

    manuscript_path = Path(state.artifacts["manuscript_md"])
    body = "\n\n".join(titled_sections)

    # Try DB-first section assembly
    try:
        async with get_db(state.db_path) as _sec_db:
            _sec_repo = WorkflowRepository(_sec_db)
            db_sections = await _sec_repo.load_latest_manuscript_sections(state.workflow_id)
        if db_sections and not rewound_before_writing:
            _heading_by_section = {
                "abstract": "## Abstract",
                "introduction": "## Introduction",
                "methods": "## Methods",
                "results": "## Results",
                "discussion": "## Discussion",
                "conclusion": "## Conclusion",
            }
            db_body_parts: list[str] = []
            for s in db_sections:
                sec_key = s.section_key
                heading = _heading_by_section.get(sec_key, "")
                sec_content = _sanitize_section_body_for_assembly(sec_key, s.content)
                if heading:
                    db_body_parts.append(f"{heading}\n\n{sec_content}")
                else:
                    db_body_parts.append(sec_content)
            if db_body_parts:
                body = "\n\n".join(db_body_parts)
    except Exception as db_section_exc:
        logger.debug("DB-first section assembly fallback to in-memory drafts: %s", db_section_exc)

    body = _normalize_subsection_heading_layout(body)
    for _h2 in _CANONICAL_H2_NAMES:
        body = re.sub(
            rf"(?im)^(##\s+{re.escape(_h2)}\b)\s+(.+)$",
            r"\1\n\n\2",
            body,
        )
    if not re.search(r"(?m)^## Abstract\s*$", body):
        body = "## Abstract\n\n" + body.lstrip()
    body = replace_template_tokens(body, state.review)

    # --- Contradiction detection pass ---
    if state.extraction_records and len(state.extraction_records) >= 2:
        try:
            _chunk_embeddings: dict[str, list[float]] = {}
            async with get_db(state.db_path) as _emb_db:
                async with _emb_db.execute(
                    "SELECT paper_id, embedding FROM paper_chunks_meta WHERE workflow_id = ? AND embedding IS NOT NULL",
                    (state.workflow_id,),
                ) as _emb_cursor:
                    _paper_vecs: dict[str, list[list[float]]] = {}
                    async for _emb_row in _emb_cursor:
                        try:
                            _vec = json.loads(_emb_row[1])
                            _paper_vecs.setdefault(_emb_row[0], []).append(_vec)
                        except Exception:
                            continue
                for _pid, _vecs in _paper_vecs.items():
                    if _vecs:
                        _dim = len(_vecs[0])
                        _chunk_embeddings[_pid] = [sum(v[i] for v in _vecs) / len(_vecs) for i in range(_dim)]

            flags = detect_contradictions(
                state.extraction_records,
                chunk_embeddings=_chunk_embeddings if _chunk_embeddings else None,
            )
            state.contradiction_flags = flags

            if flags:
                _use_llm_contra = _llm_available(settings_cfg=state.settings) and (rc is None or not rc.offline)
                _contra_model = state.settings.agents.get(
                    "contradiction_resolver", state.settings.agents["writing"]
                ).model
                async with get_db(state.db_path) as _contra_db:
                    _contra_repo = WorkflowRepository(_contra_db)
                    contra_paragraph = await generate_contradiction_paragraph(
                        flags,
                        model_name=_contra_model,
                        api_key=None,
                        repository=_contra_repo,
                        workflow_id=state.workflow_id,
                    )
                if contra_paragraph and "## Discussion" in body:
                    _disc_marker = "## Discussion"
                    _disc_idx = body.index(_disc_marker) + len(_disc_marker)
                    _after_disc = body[_disc_idx:]
                    _first_para_end = _after_disc.find("\n\n")
                    if _first_para_end > 0:
                        _inject_point = _disc_idx + _first_para_end
                        body = body[:_inject_point] + "\n\n" + contra_paragraph + body[_inject_point:]

                _pid_to_label: dict[str, str] = {}
                for _crow in citation_rows:
                    _ckey = (
                        _crow.get("citekey", "") or _crow.get("cite_key", "")
                        if isinstance(_crow, dict)
                        else getattr(_crow, "citekey", None) or getattr(_crow, "cite_key", "")
                    )
                    _cpid = _crow.get("paper_id", "") if isinstance(_crow, dict) else getattr(_crow, "paper_id", "")
                    if _ckey and _cpid:
                        _pid_to_label[str(_cpid)] = str(_ckey)
                _conflict_section = build_conflicting_evidence_section(flags, paper_id_to_label=_pid_to_label)
                if _conflict_section:
                    if "## Conclusion" in body:
                        body = body.replace(
                            "## Conclusion",
                            _conflict_section + "\n\n## Conclusion",
                            1,
                        )
                    else:
                        body = body.rstrip() + "\n\n" + _conflict_section + "\n"
        except Exception as _contra_exc:
            logger.warning("Contradiction detection failed (non-fatal): %s", _contra_exc)

    # --- Citation grounding verification ---
    if citation_catalog:
        _valid_citekeys = [
            line.strip()[1 : line.strip().index("]")]
            for line in citation_catalog.splitlines()
            if line.strip().startswith("[") and "]" in line.strip()
        ]
        if _valid_citekeys:
            _verified, _hallucinated = verify_citation_grounding(body, _valid_citekeys, "full_manuscript")
            if _hallucinated:
                logger.warning(
                    "Citation grounding: detected %d unresolved citekeys in assembled manuscript: %s",
                    len(_hallucinated),
                    _hallucinated[:5],
                )

    # --- Programmatic citation coverage check ---
    try:
        async with get_db(state.db_path) as _cov_db:
            _cov_repo = CitationRepository(_cov_db)
            _included_keys = set(await _cov_repo.get_included_citekeys())
        if _included_keys:
            _cited_in_body = set(extract_used_citekeys(body))
            _uncited = sorted(_included_keys - _cited_in_body)
            if _uncited:
                logger.info(
                    "WritingNode: detected %d uncited included-study citekeys before coverage patch: %s",
                    len(_uncited),
                    _uncited[:10],
                )
                _pid_to_design_cov: dict[str, str] = {}
                for _er in extraction_records_for_table or []:
                    _dv = getattr(_er, "study_design", None)
                    _ds = str(_dv.value if hasattr(_dv, "value") else _dv) if _dv else ""
                    if _ds:
                        _pid_to_design_cov[str(_er.paper_id)] = _ds
                _citekey_to_design_cov: dict[str, str] = {}
                for _crow in citation_rows or []:
                    _ckey = _crow.get("citekey", "") if isinstance(_crow, dict) else getattr(_crow, "citekey", "")
                    _cpid = _crow.get("paper_id", "") if isinstance(_crow, dict) else getattr(_crow, "paper_id", "")
                    if _ckey and _cpid and str(_cpid) in _pid_to_design_cov:
                        _citekey_to_design_cov[str(_ckey)] = _pid_to_design_cov[str(_cpid)]

                _cov_patch = build_citation_coverage_patch(
                    _uncited,
                    citekey_to_design=_citekey_to_design_cov if _citekey_to_design_cov else None,
                    chunk_size=getattr(getattr(state.settings, "writing", None), "citation_cluster_chunk_size", 8),
                )
                _rob_marker = "### Risk of Bias"
                if _rob_marker in body:
                    body = body.replace(_rob_marker, _cov_patch + "\n\n" + _rob_marker, 1)
                else:
                    _disc_marker = "## Discussion"
                    if _disc_marker in body:
                        body = body.replace(_disc_marker, _cov_patch + "\n\n" + _disc_marker, 1)
                    else:
                        body = body.rstrip() + "\n\n" + _cov_patch + "\n"
                try:
                    async with get_db(state.db_path) as _patch_db:
                        _results_content_cur = await _patch_db.execute(
                            """
                            SELECT content
                            FROM section_drafts
                            WHERE workflow_id = ?
                              AND section = 'results'
                              AND generation = COALESCE(
                                  (SELECT writing_generation FROM workflows WHERE workflow_id = ?),
                                  1
                              )
                            ORDER BY version DESC
                            LIMIT 1
                            """,
                            (state.workflow_id, state.workflow_id),
                        )
                        _results_row = await _results_content_cur.fetchone()
                        if _results_row:
                            _patched_results = _results_row[0]
                            if _rob_marker in _patched_results:
                                _patched_results = _patched_results.replace(
                                    _rob_marker, _cov_patch + "\n\n" + _rob_marker, 1
                                )
                            else:
                                _patched_results = _patched_results.rstrip() + "\n\n" + _cov_patch
                            await _patch_db.execute(
                                """
                                UPDATE section_drafts
                                SET content = ?
                                WHERE workflow_id = ?
                                  AND section = 'results'
                                  AND generation = COALESCE(
                                      (SELECT writing_generation FROM workflows WHERE workflow_id = ?),
                                      1
                                  )
                                """,
                                (_patched_results, state.workflow_id, state.workflow_id),
                            )
                            await _patch_db.commit()
                            logger.info(
                                "WritingNode: injected %d uncited keys into Results section_draft",
                                len(_uncited),
                            )
                except Exception as _db_patch_exc:
                    logger.debug("WritingNode: DB draft patch failed (non-fatal): %s", _db_patch_exc)
                _remaining_uncited = sorted(_included_keys - set(extract_used_citekeys(body)))
                if _remaining_uncited:
                    logger.warning(
                        "WritingNode: %d included-study citekeys remained uncited after coverage patch: %s",
                        len(_remaining_uncited),
                        _remaining_uncited[:10],
                    )
                else:
                    logger.info("WritingNode: citation coverage patch resolved all included-study citekeys.")
            else:
                logger.info("WritingNode: citation coverage OK -- all %d included keys cited", len(_included_keys))
    except Exception as _cov_exc:
        logger.warning("WritingNode: citation coverage check failed (non-fatal): %s", _cov_exc)

    # --- Load GRADE/RoB for manuscript assembly ---
    async with get_db(state.db_path) as _grade_db:
        _grade_repo = WorkflowRepository(_grade_db)
        _grade_assessments = await _grade_repo.load_grade_assessments(state.workflow_id)
        _rob2_rows, _robins_i_rows = await _grade_repo.load_rob_assessments(state.workflow_id)
        _casp_rows = await _grade_repo.load_casp_assessments(state.workflow_id)
        _mmat_rows = await _grade_repo.load_mmat_assessments(state.workflow_id)
        _paper_id_to_citekey = await _grade_repo.get_paper_id_to_citekey_map()

    _search_appendix_path = Path(state.artifacts["search_appendix"]) if "search_appendix" in state.artifacts else None

    _papers_manifest_path = Path(state.artifacts.get("papers_manifest", ""))
    _fulltext_paper_ids: set[str] = set()
    if _papers_manifest_path.exists():
        try:
            _manifest_dir = _papers_manifest_path.parent
            _manifest_data = json.loads(_papers_manifest_path.read_text(encoding="utf-8"))
            for _pid, _entry in _manifest_data.items():
                _fp_raw = (_entry or {}).get("file_path", "")
                if not _fp_raw:
                    continue
                _fp = Path(_fp_raw)
                if not _fp.is_absolute():
                    _fp_resolved = (_manifest_dir / _fp_raw).resolve()
                    if not _fp_resolved.exists():
                        _fp_resolved = Path(_fp_raw)
                else:
                    _fp_resolved = _fp
                if _fp_resolved.exists() and _fp_resolved.stat().st_size > 0:
                    _fulltext_paper_ids.add(str(_pid))
        except Exception as _manifest_err:
            logger.warning("Could not read papers manifest for Appendix B: %s", _manifest_err)
    if not _fulltext_paper_ids:
        _papers_dir = Path(state.db_path).parent / "papers"
        if _papers_dir.exists():
            for _pf in _papers_dir.iterdir():
                if _pf.suffix in {".pdf", ".txt"} and _pf.stat().st_size > 0:
                    _fulltext_paper_ids.add(_pf.stem)

    # --- First manuscript assembly ---
    full_manuscript = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=state.artifacts,
        citation_rows=citation_rows,
        papers=included_papers_for_table,
        extraction_records=extraction_records_for_table,
        grade_assessments=_grade_assessments if _grade_assessments else None,
        rob2_assessments=_rob2_rows if _rob2_rows else None,
        robins_i_assessments=_robins_i_rows if _robins_i_rows else None,
        casp_assessments=_casp_rows if _casp_rows else None,
        mmat_assessments=_mmat_rows if _mmat_rows else None,
        paper_id_to_citekey=_paper_id_to_citekey if _paper_id_to_citekey else None,
        review_config=state.review,
        failed_count=_failed_extraction_count,
        search_appendix_path=_search_appendix_path,
        research_question=state.review.research_question if state.review else "",
        title=None,
        fulltext_paper_ids=_fulltext_paper_ids if _fulltext_paper_ids else None,
        diagram_placement_plan_path=state.artifacts.get("diagram_placement_plan", ""),
        ir_validated=True,
    )
    manuscript_path.write_text(full_manuscript, encoding="utf-8")

    # --- Persist manuscript assets ---
    try:

        def _extract_md_section(text: str, heading: str) -> str:
            pat = re.compile(rf"(^## {re.escape(heading)}\n.*?)(?=\n\n---\n\n## |\Z)", re.MULTILINE | re.DOTALL)
            m = pat.search(text)
            return m.group(1).strip() if m else ""

        _assets: list[ManuscriptAsset] = []
        _compact_match = re.search(
            r"(_Table 1\. Summary of .*?included studies.*?_\n\n"
            r"\| Study \(Year\) \| Country \| Design \| N \| Key Finding \|\n"
            r"\|---\|---\|---\|---\|---\|\n"
            r"(?:\|.*\|\n)+)",
            full_manuscript,
            re.DOTALL,
        )
        if _compact_match:
            _assets.append(
                ManuscriptAsset(
                    workflow_id=state.workflow_id,
                    asset_key="tbl_study_characteristics_compact",
                    asset_type="table",
                    format="md",
                    content=_compact_match.group(1).strip(),
                    version=1,
                )
            )
        _figures = _extract_md_section(full_manuscript, "Figures")
        if _figures:
            _assets.append(
                ManuscriptAsset(
                    workflow_id=state.workflow_id,
                    asset_key="sec_figures",
                    asset_type="figure",
                    format="md",
                    content=_figures,
                    version=1,
                )
            )
        _refs = _extract_md_section(full_manuscript, "References")
        if _refs:
            _assets.append(
                ManuscriptAsset(
                    workflow_id=state.workflow_id,
                    asset_key="sec_references",
                    asset_type="appendix",
                    format="md",
                    content=_refs,
                    version=1,
                )
            )
        _appendix_c = _extract_md_section(full_manuscript, "Appendix C: Search Strategies")
        if _appendix_c:
            _assets.append(
                ManuscriptAsset(
                    workflow_id=state.workflow_id,
                    asset_key="appendix_search_strategies",
                    asset_type="appendix",
                    format="md",
                    content=_appendix_c,
                    version=1,
                )
            )
        async with get_db(state.db_path) as _asm_db:
            _asm_repo = WorkflowRepository(_asm_db)
            _latest_sections = await _asm_repo.load_latest_manuscript_sections(state.workflow_id)
            for _asset in _assets:
                await _asm_repo.save_manuscript_asset(_asset)
            _manifest = {
                "sections": [
                    {
                        "section_key": s.section_key,
                        "version": s.version,
                        "order": s.section_order,
                    }
                    for s in _latest_sections
                ],
                "assets": [{"asset_key": a.asset_key, "version": a.version} for a in _assets],
            }
            await _asm_repo.save_manuscript_assembly(
                ManuscriptAssembly(
                    workflow_id=state.workflow_id,
                    assembly_id="latest",
                    target_format="md",
                    content=full_manuscript,
                    manifest_json=json.dumps(_manifest, ensure_ascii=True),
                )
            )
    except Exception as asm_exc:
        logger.debug("Failed to persist markdown manuscript assembly (non-fatal): %s", asm_exc)
    await save_subphase_checkpoint("phase_6d_assembly", papers_processed=len(SECTIONS))

    # --- Concept diagrams (LLM -> Graphviz/Kroki -> SVG) ---
    try:
        _out_dir = Path(state.artifacts["concept_taxonomy"]).parent
        _review = state.review
        _pico = _review.pico if _review else None
        _n_included = len(state.included_papers)
        _topic = _review.research_question if _review else "Systematic Review"

        _taxonomy_spec: TaxonomyDiagramInput | None = None
        if state.extraction_records and _pico:
            _design_counter = Counter(
                r.study_design.value if r.study_design else "Other" for r in state.extraction_records
            )
            if len(_design_counter) >= 2:
                _categories = [
                    TaxonomyCategory(label=design, items=[f"n={count} studies"])
                    for design, count in _design_counter.most_common()
                ]
                _taxonomy_spec = TaxonomyDiagramInput(
                    title=f"Study Design Taxonomy ({_n_included} studies)",
                    root_label="Included Studies",
                    categories=_categories,
                    review_topic=_topic,
                )

        _framework_spec: FrameworkDiagramInput | None = None
        if _pico and _n_included >= 1:
            _narr_themes: list[str] = []
            if narrative and "narrative" in narrative:
                _narr_data = narrative["narrative"]
                if isinstance(_narr_data, dict):
                    _narr_themes = _narr_data.get("key_themes", [])
                elif isinstance(_narr_data, list):
                    for _n in _narr_data:
                        if isinstance(_n, dict):
                            _narr_themes.extend(_n.get("key_themes", []))
            _framework_spec = FrameworkDiagramInput(
                title="Conceptual Framework",
                population=_pico.population,
                interventions=[_pico.intervention],
                outcomes=[_pico.outcome],
                comparator=_pico.comparison if _pico.comparison else None,
                key_themes=list(dict.fromkeys(_narr_themes))[:6],
                study_count=_n_included,
                review_topic=_topic,
            )

        _flowchart_spec: FlowchartDiagramInput | None = None
        if prisma_counts:
            _phases = [
                FlowchartPhase(
                    label="Database Search",
                    count=prisma_counts.total_identified_databases,
                ),
                FlowchartPhase(
                    label="After Deduplication",
                    count=prisma_counts.records_screened + prisma_counts.records_excluded_screening,
                ),
                FlowchartPhase(
                    label="Title/Abstract Screening",
                    count=prisma_counts.records_screened,
                    sublabel=f"{prisma_counts.records_excluded_screening} excluded",
                ),
                FlowchartPhase(
                    label="Eligible for Inclusion",
                    count=prisma_counts.reports_sought,
                ),
                FlowchartPhase(
                    label="Included in Review",
                    count=prisma_counts.studies_included_qualitative + prisma_counts.studies_included_quantitative,
                ),
            ]
            _flowchart_spec = FlowchartDiagramInput(
                title="Systematic Review Methodology",
                phases=_phases,
                review_topic=_topic,
            )

        _concept_model = state.settings.agents.get(
            "concept_diagrams", state.settings.agents.get("abstract_generation", state.settings.agents["writing"])
        ).model
        _concept_style_seed = f"{state.workflow_id}|{_topic[:280]}"
        async with get_db(state.db_path) as _cd_db:
            _cd_repo = WorkflowRepository(_cd_db)
            _cd_provider = LLMProvider(state.settings, _cd_repo)
            _concept_results = await asyncio.wait_for(
                render_concept_diagrams(
                    taxonomy_spec=_taxonomy_spec,
                    framework_spec=_framework_spec,
                    flowchart_spec=_flowchart_spec,
                    out_dir=_out_dir,
                    model=_concept_model,
                    style_seed=_concept_style_seed,
                    provider=_cd_provider,
                    workflow_id=state.workflow_id,
                ),
                timeout=180.0,
            )
        if rc and rc.verbose:
            for _key, _path in _concept_results.items():
                if _path:
                    _rc_print(rc, f"  Concept diagram ({_key}): {_path.name}")
    except TimeoutError:
        logger.warning("Concept diagram generation timed out after 180s -- skipping")
    except asyncio.CancelledError:
        logger.warning("Concept diagram generation cancelled -- skipping")
    except Exception as _cd_exc:  # noqa: BLE001
        logger.warning("Concept diagram generation failed: %s", _cd_exc)
    else:
        await save_subphase_checkpoint("phase_6e_concepts", papers_processed=len(SECTIONS))

    # --- Custom diagrams (direct Gemini image generation) ---
    try:
        _dg_cfg = state.settings.diagram_generation
        _topic = state.review.research_question if state.review else "Systematic Review"
        _rq = state.review.research_question if state.review else _topic
        _manifest_path = Path(state.artifacts.get("papers_manifest", ""))
        _manifest_entries: dict[str, dict] | list[dict] = {}
        if _manifest_path.exists():
            try:
                _manifest_entries = json.loads(_manifest_path.read_text(encoding="utf-8"))
            except Exception as _manifest_exc:  # noqa: BLE001
                logger.warning("Custom diagram: invalid papers manifest: %s", _manifest_exc)

        async with get_db(state.db_path) as _dg_db:
            _dg_repo = WorkflowRepository(_dg_db)
            _dg_provider = LLMProvider(state.settings, _dg_repo)
            _canonical_ids = await _dg_repo.get_synthesis_included_paper_ids(state.workflow_id)

            _included_rows: list[dict[str, object]] = []
            _canonical_set = set(_canonical_ids)
            for _p in state.included_papers:
                if _canonical_set and _p.paper_id not in _canonical_set:
                    continue
                _included_rows.append(
                    {
                        "paper_id": _p.paper_id,
                        "title": _p.title,
                        "year": _p.year,
                    }
                )
            if not _included_rows:
                _included_rows = [
                    {"paper_id": _p.paper_id, "title": _p.title, "year": _p.year} for _p in state.included_papers
                ]

            _max_papers = int(getattr(_dg_cfg, "max_papers_for_brief", 24) or 24)
            if _max_papers > 0:
                _included_rows = _included_rows[:_max_papers]

            _extraction_rows: list[dict[str, object]] = []
            for _rec in state.extraction_records or []:
                if _canonical_set and _rec.paper_id not in _canonical_set:
                    continue
                _summary = (_rec.results_summary or {}).get("summary", "")
                _first_outcome = _rec.outcomes[0].description if _rec.outcomes else ""
                _extraction_rows.append(
                    {
                        "paper_id": _rec.paper_id,
                        "study_design": _rec.study_design.value if _rec.study_design else "",
                        "summary": sanitize_summary_text_for_writing(_summary),
                        "primary_outcome": _first_outcome,
                        "intervention": _rec.intervention_description or "",
                        "population": _rec.participant_demographics or "",
                    }
                )

            _prep_agent = state.settings.agents.get(
                "research_diagram_preparer",
                state.settings.agents.get("concept_diagrams", state.settings.agents["writing"]),
            )
            _brief_pack, _prep_usage = await prepare_research_diagram_briefs(
                workflow_id=state.workflow_id,
                review_topic=_topic,
                research_question=_rq,
                included_studies=_included_rows,
                extraction_summaries=_extraction_rows,
                manifest_entries=_manifest_entries,
                model=_prep_agent.model,
                temperature=_prep_agent.temperature,
                provider=_dg_provider,
            )
            _brief_path = Path(state.artifacts.get("diagram_brief_pack", ""))
            if _brief_path.name:
                _brief_path.write_text(_brief_pack.model_dump_json(indent=2), encoding="utf-8")

            _placement_plan = DiagramPlacementPlan(workflow_id=state.workflow_id)
            _placement_agent = state.settings.agents.get(
                "research_diagram_placement",
                state.settings.agents.get("writing"),
            )
            _placement_usage: dict[str, int] = {}
            try:
                _placement_plan, _placement_usage = await plan_inline_diagram_placements(
                    workflow_id=state.workflow_id,
                    brief_pack=_brief_pack,
                    manuscript_body=body,
                    model=_placement_agent.model,
                    temperature=_placement_agent.temperature,
                    provider=_dg_provider,
                )
            except Exception as _placement_exc:  # noqa: BLE001
                logger.warning("Custom diagram placement planning failed: %s", _placement_exc)
            _placement_path = Path(state.artifacts.get("diagram_placement_plan", ""))
            if _placement_path.name:
                _placement_path.write_text(_placement_plan.model_dump_json(indent=2), encoding="utf-8")

            _style_refs: list[str] = []
            if bool(getattr(_dg_cfg, "include_reference_style_images", True)):
                for _k in ("concept_taxonomy", "conceptual_framework", "methodology_flow"):
                    _p = Path(state.artifacts.get(_k, ""))
                    if _p.exists():
                        _style_refs.append(str(_p))
            _style = DiagramStyleGuide(style_reference_paths=_style_refs[:6])

            _drawing_agent = state.settings.agents.get(
                "research_diagram_drawing",
                state.settings.agents.get("concept_diagrams", state.settings.agents["writing"]),
            )
            _critic_agent = state.settings.agents.get(
                "research_diagram_critic",
                state.settings.agents.get("writing"),
            )

            _report = await asyncio.wait_for(
                render_custom_research_diagrams(
                    brief_pack=_brief_pack,
                    out_dir=Path(state.output_dir),
                    drawing_model=_drawing_agent.model,
                    critic_model=_critic_agent.model,
                    style_guide=_style,
                    max_rounds=int(getattr(_dg_cfg, "max_rounds", 1) or 1),
                    image_size=str(getattr(_dg_cfg, "image_size", "2K")),
                    aspect_ratio=str(getattr(_dg_cfg, "aspect_ratio", "16:9")),
                    repository=_dg_repo,
                    provider=_dg_provider,
                ),
                timeout=420.0,
            )

        for _result in _report.results:
            _decision = next(
                (d for d in _placement_plan.decisions if d.diagram_id == _result.diagram_id),
                None,
            )
            if _decision is not None:
                _result.placement = _decision
            state.artifacts[_result.artifact_key] = _result.output_path

        _report_path = Path(state.artifacts.get("diagram_generation_report", ""))
        if _report_path.name:
            _report_path.write_text(_report.model_dump_json(indent=2), encoding="utf-8")
        await save_subphase_checkpoint(
            "phase_6f_custom_diagrams",
            papers_processed=len(_report.results),
        )
        if rc and rc.verbose:
            _rc_print(rc, f"  Custom diagram outputs: {len(_report.results)}")
    except TimeoutError:
        logger.warning("Custom diagram generation timed out -- skipping")
    except asyncio.CancelledError:
        logger.warning("Custom diagram generation cancelled -- skipping")
    except Exception as _custom_diag_exc:  # noqa: BLE001
        logger.warning("Custom diagram generation failed: %s", _custom_diag_exc)

    # --- Re-assemble manuscript with concept diagram SVGs ---
    try:
        patched = assemble_submission_manuscript(
            body=body,
            manuscript_path=manuscript_path,
            artifacts=state.artifacts,
            citation_rows=citation_rows,
            papers=included_papers_for_table,
            extraction_records=extraction_records_for_table,
            grade_assessments=_grade_assessments if _grade_assessments else None,
            rob2_assessments=_rob2_rows if _rob2_rows else None,
            robins_i_assessments=_robins_i_rows if _robins_i_rows else None,
            casp_assessments=_casp_rows if _casp_rows else None,
            mmat_assessments=_mmat_rows if _mmat_rows else None,
            paper_id_to_citekey=_paper_id_to_citekey if _paper_id_to_citekey else None,
            review_config=state.review,
            failed_count=_failed_extraction_count,
            search_appendix_path=_search_appendix_path,
            research_question=state.review.research_question if state.review else "",
            title=None,
            fulltext_paper_ids=_fulltext_paper_ids if _fulltext_paper_ids else None,
            diagram_placement_plan_path=state.artifacts.get("diagram_placement_plan", ""),
            ir_validated=True,
        )
        manuscript_path.write_text(patched, encoding="utf-8")
        logger.info("WritingNode: manuscript patched with concept diagram figures")
    except Exception as _patch_exc:  # noqa: BLE001
        logger.warning("WritingNode: concept diagram manuscript patch failed (non-fatal): %s", _patch_exc)
