from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import ManuscriptAssembly, ReviewConfig
from src.writing.citation_grounding import extract_numeric_citation_refs, extract_used_citekeys

logger = logging.getLogger(__name__)

_TEMPLATE_TOKEN_REGEX = re.compile(
    r"\[(INTERVENTION|OUTCOME|OUTCOME MEASURE|POPULATION|COMPARATOR)\]",
    flags=re.IGNORECASE,
)
_UUID_LIKE_BRACKET_REGEX = re.compile(r"\[(?:[0-9a-f]{7,}(?:-[0-9a-f]{2,})+)\]", flags=re.IGNORECASE)


def build_citation_coverage_patch(
    uncited_keys: list[str],
    citekey_to_design: dict[str, str] | None = None,
    chunk_size: int = 8,
) -> str:
    """Build a Study Characteristics paragraph citing all uncited included-study keys."""
    if not uncited_keys:
        return ""
    chunk_size = max(1, int(chunk_size))

    if citekey_to_design:
        design_buckets: dict[str, list[str]] = {}
        ungrouped: list[str] = []
        for key in uncited_keys:
            design = citekey_to_design.get(key, "")
            d_lower = design.lower().replace("_", " ").strip()
            if "randomized" in d_lower or "rct" in d_lower or "controlled trial" in d_lower:
                bucket = "Randomized controlled trials"
            elif "non-randomized" in d_lower or "quasi" in d_lower or "non randomized" in d_lower:
                bucket = "Non-randomized studies"
            elif "pre" in d_lower and "post" in d_lower:
                bucket = "Pre-post studies"
            elif "qualitative" in d_lower:
                bucket = "Qualitative studies"
            elif "cross" in d_lower and "section" in d_lower:
                bucket = "Cross-sectional studies"
            elif "case" in d_lower:
                bucket = "Case reports and case series"
            elif "development" in d_lower or "feasibility" in d_lower or "usability" in d_lower:
                bucket = "Developmental and feasibility studies"
            elif "review" in d_lower and "system" not in d_lower:
                bucket = "Narrative reviews"
            elif design:
                bucket = f"{design.capitalize()} studies"
            else:
                ungrouped.append(key)
                continue
            design_buckets.setdefault(bucket, []).append(key)
        if ungrouped:
            design_buckets.setdefault("Additional included studies", []).extend(ungrouped)

        sentences = []
        for label, keys in design_buckets.items():
            groups = [keys[i : i + chunk_size] for i in range(0, len(keys), chunk_size)]
            clusters = "; ".join("[" + ", ".join(g) + "]" for g in groups)
            sentences.append(f"{label} in this review also include {clusters}.")
        return " ".join(sentences)

    groups = [uncited_keys[i : i + chunk_size] for i in range(0, len(uncited_keys), chunk_size)]
    sentences = [f"Studies contributing to the evidence base include [{', '.join(groups[0])}]."]
    for group in groups[1:]:
        sentences.append(f"Further included studies are [{', '.join(group)}].")
    return " ".join(sentences)


def replace_template_tokens(text: str, review: ReviewConfig | None) -> str:
    """Replace scaffold placeholders with concrete review-config values."""
    if not text:
        return text
    if review is None or getattr(review, "pico", None) is None:
        cleaned = _TEMPLATE_TOKEN_REGEX.sub("", text)
        cleaned = _UUID_LIKE_BRACKET_REGEX.sub("", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return re.sub(r"\s+([,.;:])", r"\1", cleaned)
    pico = review.pico
    mapping = {
        "INTERVENTION": str(getattr(pico, "intervention", "") or "the intervention"),
        "OUTCOME": str(getattr(pico, "outcome", "") or "the outcome"),
        "OUTCOME MEASURE": str(getattr(pico, "outcome", "") or "the outcome"),
        "POPULATION": str(getattr(pico, "population", "") or "the study population"),
        "COMPARATOR": str(getattr(pico, "comparison", "") or "the comparator"),
    }

    def _repl(match: re.Match[str]) -> str:
        return mapping.get(match.group(1).upper(), "")

    cleaned = _TEMPLATE_TOKEN_REGEX.sub(_repl, text)
    cleaned = _UUID_LIKE_BRACKET_REGEX.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r"\s+([,.;:])", r"\1", cleaned)


def trim_abstract_to_limit(abstract: str, limit: int | None = None) -> str:
    """Trim abstract body to at most `limit` words, excluding the Keywords line."""
    if limit is None:
        from src.models.config import IEEEExportConfig

        limit = int(IEEEExportConfig().max_abstract_words)

    lines = abstract.split("\n")
    kw_line = ""
    body_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip("*").lstrip().lower()
        if stripped.startswith("keywords:") or stripped.startswith("**keywords"):
            kw_line = line
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()

    body_words = body.split()
    if len(body_words) <= limit:
        return abstract

    field_re = re.compile(r"(\*\*[A-Za-z ]+:\*\*[^\n]*(?:\n(?!\*\*)[^\n]*)*)", re.MULTILINE)
    while len(body.split()) > limit:
        fields = field_re.findall(body)
        if not fields:
            body = " ".join(body.split()[:limit])
            break
        excess = len(body.split()) - limit
        longest_idx = max(range(len(fields)), key=lambda i: len(fields[i].split()))
        field_text = fields[longest_idx]
        field_words = field_text.split()
        trim_target = max(1, len(field_words) - excess)
        candidate = " ".join(field_words[:trim_target])
        last_sentence_end = max(
            candidate.rfind(". "),
            candidate.rfind("? "),
            candidate.rfind("! "),
            candidate.rfind(".\n"),
        )
        if last_sentence_end > len(candidate) // 2:
            trimmed_field = candidate[: last_sentence_end + 1].rstrip()
        else:
            trimmed_field = candidate
        body = body.replace(field_text, trimmed_field, 1)

    return (body.strip() + ("\n\n" + kw_line if kw_line else "")).strip()


def build_minimal_sections_for_zero_papers(
    research_question: str,
    minimal_paragraph: str,
    sections: list[str],
) -> list[str]:
    """Build minimal section content when no studies were included."""
    rq = research_question or "the research question"
    result: list[str] = []
    for section in sections:
        if section == "abstract":
            content = (
                f"**Background:** This review examines the available evidence for {rq}. "
                f"**Objectives:** This systematic review addressed {rq}. "
                "**Methods:** Bibliographic databases were searched per protocol. "
                "**Results:** The search identified records as reported; 0 studies "
                "met the eligibility criteria. **Conclusion:** No synthesis was "
                "performed. **Keywords:** systematic review, empty result, evidence gap."
            )
        elif section == "introduction":
            content = (
                f"This systematic review aimed to address {rq}. "
                "No studies met the eligibility criteria after screening."
            )
        elif section == "methods":
            content = (
                "Searches were conducted in bibliographic databases per the "
                "registered protocol. Eligibility criteria were applied by "
                "independent reviewers. No studies were included."
            )
        elif section == "results":
            content = minimal_paragraph
        elif section == "discussion":
            content = (
                "With no studies meeting eligibility criteria, no synthesis or "
                "findings can be reported. This may reflect a narrow search scope, "
                "restrictive eligibility criteria, or a genuine evidence gap."
            )
        elif section == "conclusion":
            content = "No conclusions can be drawn from this review. No studies met the eligibility criteria."
        else:
            content = minimal_paragraph
        result.append(content)
    return result


def validate_writing_persistence_invariant(
    required_sections: list[str],
    persisted_sections: set[str],
    failed_sections: list[str],
) -> tuple[bool, list[str]]:
    """Return (violated, missing_sections) for writing completion invariant."""
    missing_sections = sorted(set(required_sections) - persisted_sections)
    unrecovered_failed = sorted(set(failed_sections) - persisted_sections)
    violated = bool(unrecovered_failed or missing_sections)
    return violated, missing_sections


async def refresh_manuscript_export_artifacts(
    state,
    *,
    strict_export: bool,
    persist_assembly: bool = False,
) -> str | None:
    """Render current markdown manuscript into fresh TeX/Bib artifacts."""
    manuscript_md_path = state.artifacts.get("manuscript_md", "")
    if not manuscript_md_path or not os.path.isfile(manuscript_md_path):
        return None

    from src.export.bibtex_builder import _sanitize_citekey as _sanitize_bib_citekey
    from src.export.bibtex_builder import build_bibtex as _build_bibtex
    from src.export.bibtex_builder import build_citekey_alias_map as _build_citekey_alias_map
    from src.export.ieee_latex import markdown_to_latex as _md_to_latex
    from src.export.markdown_refs import extract_inline_figure_artifact_keys, get_latex_figure_paths
    from src.export.submission_packager import (
        _build_number_to_citekey,
        llm_resolve_unmatched_citations,
    )

    manuscript_path = Path(manuscript_md_path)
    tex_path = manuscript_path.parent / "doc_manuscript.tex"
    bib_path = manuscript_path.parent / "references.bib"

    async with get_db(state.db_path) as db:
        citations = await CitationRepository(db).get_all_citations_for_export()

    used_keys: set[str] = set()
    key_map: dict[str, str] = {}
    normalized_citations: list[tuple] = []
    for idx, row in enumerate(citations):
        cid, citekey, doi, title, authors_json, year, journal, bibtex = row[:8]
        url = row[8] if len(row) > 8 else None
        safe_key = _sanitize_bib_citekey(citekey, title, authors_json, year, idx)
        unique_key = safe_key
        suffix = 2
        while unique_key in used_keys:
            unique_key = f"{safe_key}_{suffix}"
            suffix += 1
        used_keys.add(unique_key)
        key_map[str(citekey)] = unique_key
        normalized_citations.append((cid, unique_key, doi, title, authors_json, year, journal, bibtex, url))

    md_text = manuscript_path.read_text(encoding="utf-8")
    citekeys = {c[1] for c in normalized_citations}
    citekey_aliases = _build_citekey_alias_map(normalized_citations)
    num_map = _build_number_to_citekey(md_text, normalized_citations)
    if not strict_export:
        num_map = await llm_resolve_unmatched_citations(
            md_text,
            normalized_citations,
            num_map,
            db_path=state.db_path,
            workflow_id=state.workflow_id,
        )
    cited_citekeys = set(num_map.values())
    for old_key, new_key in key_map.items():
        num_map.setdefault(old_key, new_key)

    author_name = str(getattr(getattr(state, "review", None), "author_name", "") or "")
    inline_artifact_keys = extract_inline_figure_artifact_keys(md_text, state.artifacts)
    figure_paths = get_latex_figure_paths(
        manuscript_path,
        state.artifacts,
        exclude_artifact_keys=inline_artifact_keys,
    )
    tex_content = _md_to_latex(
        md_text,
        citekeys=citekeys,
        figure_paths=figure_paths,
        num_to_citekey=num_map,
        citekey_aliases=citekey_aliases,
        author_name=author_name,
    )
    has_md_figures = bool(re.search(r"!\[[^\]]*\]\([^)]+\)", md_text))
    has_tex_figures = "\\includegraphics" in tex_content
    if has_md_figures and not has_tex_figures:
        raise RuntimeError(
            "LaTeX conversion emitted zero figures despite markdown figure references. "
            "Check figure artifact paths and markdown_to_latex figure_paths handling."
        )
    if strict_export:
        unresolved_alpha = extract_used_citekeys(tex_content)
        unresolved_numeric = extract_numeric_citation_refs(tex_content)
        if unresolved_alpha or unresolved_numeric:
            unresolved_tokens = unresolved_alpha[:10] + unresolved_numeric[:10]
            raise RuntimeError(
                "strict export blocked: unresolved citations remain after deterministic conversion: "
                + ", ".join(unresolved_tokens[:10])
            )

    tex_path.write_text(tex_content, encoding="utf-8")
    bib_path.write_text(
        _build_bibtex(normalized_citations, cited_citekeys=cited_citekeys),
        encoding="utf-8",
    )
    state.artifacts["manuscript_tex"] = str(tex_path)
    state.artifacts["references_bib"] = str(bib_path)

    if persist_assembly:
        try:
            async with get_db(state.db_path) as asm_db:
                asm_repo = WorkflowRepository(asm_db)
                latest_sections = await asm_repo.load_latest_manuscript_sections(state.workflow_id)
                manifest = {
                    "sections": [
                        {
                            "section_key": section.section_key,
                            "version": section.version,
                            "order": section.section_order,
                        }
                        for section in latest_sections
                    ]
                }
                await asm_repo.save_manuscript_assembly(
                    ManuscriptAssembly(
                        workflow_id=state.workflow_id,
                        assembly_id="latest",
                        target_format="tex",
                        content=tex_content,
                        manifest_json=json.dumps(manifest, ensure_ascii=True),
                    )
                )
        except Exception as asm_err:
            logger.debug("Failed to persist tex assembly (non-fatal): %s", asm_err)
    return str(tex_path)
