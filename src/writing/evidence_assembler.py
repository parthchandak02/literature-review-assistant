"""Deterministic evidence assembly for the Results section."""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from src.models import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import StudySummary, WritingGroundingData

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TERMINAL_PUNCTUATION = ".!?"
_RESULTS_REQUIRED_SUBHEADINGS = ("Study Selection", "Study Characteristics", "Synthesis of Findings")


def _normalize_title(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", str(text or "").lower()).strip()


def _naturalize_label(text: str) -> str:
    return str(text or "").replace("_", " ").strip()


def _normalize_heading_key(text: str) -> str:
    return _normalize_title(_naturalize_label(text))


def _ensure_terminal_punctuation(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    if value[-1] in _TERMINAL_PUNCTUATION:
        return value
    return f"{value}."


def _canonical_results_heading(text: str) -> str:
    normalized = _normalize_heading_key(text)
    if normalized in {"study selection", "selection", "included studies"}:
        return "Study Selection"
    if normalized in {"study characteristics", "characteristics", "study profile"}:
        return "Study Characteristics"
    if normalized in {
        "synthesis of findings",
        "synthesis findings",
        "main findings",
        "findings",
        "results synthesis",
        "synthesis",
    }:
        return "Synthesis of Findings"
    return ""


def _append_unique_block(blocks: list[SectionBlock], block: SectionBlock, seen_texts: set[str]) -> None:
    text = _ensure_terminal_punctuation(block.text)
    if not text:
        return
    dedupe_key = _normalize_title(text)
    if dedupe_key and dedupe_key in seen_texts:
        return
    if dedupe_key:
        seen_texts.add(dedupe_key)
    blocks.append(
        block.model_copy(
            update={
                "text": text,
                "citations": list(dict.fromkeys(block.citations or [])),
            }
        )
    )


def _append_unique_paragraph(
    blocks: list[SectionBlock],
    text: str,
    seen_texts: set[str],
    citations: list[str] | None = None,
) -> None:
    _append_unique_block(
        blocks,
        SectionBlock(
            block_type="paragraph",
            text=text,
            citations=list(dict.fromkeys(citations or [])),
        ),
        seen_texts,
    )


def _study_result_sentence(study: ResultsEvidenceStudy) -> str:
    title = str(study.title or "Included study").strip().rstrip(".")
    design = _naturalize_label(study.study_design or "included study").lower()
    key_finding = str(study.key_finding or "").strip()
    if key_finding and key_finding != "Not reported" and key_finding[-1] in _TERMINAL_PUNCTUATION:
        return f"{title} reported the following key finding: {key_finding}"
    if key_finding == "Not reported":
        return f"{title}: No quantitative outcomes were reported."
    if study.participant_count is not None and study.participant_count > 0:
        return f"{title} was a {design} study with {study.participant_count} participants and contributed evidence to this review."
    article = "an" if design[:1] in "aeiou" else "a"
    return f"{title} was {article} {design} that contributed evidence to this review."


class ResultsEvidenceStudy(BaseModel):
    citekey: str | None = None
    title: str
    study_design: str
    participant_count: int | None = None
    key_finding: str


class ResultsEvidencePack(BaseModel):
    study_selection_sentence: str
    characteristics_summary: str
    synthesis_summary: str
    theme_sentences: list[str] = Field(default_factory=list)
    studies: list[ResultsEvidenceStudy] = Field(default_factory=list)


def _resolve_citekey(summary: StudySummary, grounding: WritingGroundingData) -> str | None:
    summary_title = _normalize_title(summary.title)
    if not summary_title:
        return None
    for citekey, title in (grounding.citekey_title_map or {}).items():
        title_norm = _normalize_title(title)
        if not title_norm:
            continue
        if summary_title == title_norm or summary_title.startswith(title_norm) or title_norm.startswith(summary_title):
            return str(citekey)
    return None


def build_results_evidence_pack(grounding: WritingGroundingData | None) -> ResultsEvidencePack:
    if grounding is None:
        return ResultsEvidencePack(
            study_selection_sentence="No deterministic results evidence was available.",
            characteristics_summary="Study characteristics could not be summarized deterministically.",
            synthesis_summary="Synthesis findings could not be summarized deterministically.",
        )

    selection_sentence = (
        f"The review screened {grounding.total_screened} records, sought {grounding.fulltext_sought} full-text reports, "
        f"did not retrieve {grounding.fulltext_not_retrieved}, assessed {grounding.fulltext_assessed} reports for "
        f"eligibility, and included {grounding.total_included} studies."
    )

    design_bits = [
        f"{label.replace('_', ' ')} (n={count})"
        for label, count in sorted((grounding.study_design_counts or {}).items(), key=lambda item: (-item[1], item[0]))
        if count > 0
    ]
    characteristics_parts: list[str] = []
    if design_bits:
        characteristics_parts.append("Study designs included " + ", ".join(design_bits) + ".")
    if grounding.year_range:
        characteristics_parts.append(f"Publication years ranged from {grounding.year_range}.")
    if grounding.total_participants is not None:
        characteristics_parts.append(f"Reported participant totals summed to {grounding.total_participants}.")
    elif grounding.n_studies_reporting_count > 0:
        characteristics_parts.append(
            f"Participant counts were explicitly reported in {grounding.n_studies_reporting_count} of "
            f"{grounding.n_total_studies} studies."
        )
    characteristics_summary = " ".join(characteristics_parts) or (
        "Included studies varied in design, publication year, and reporting detail."
    )

    synthesis_parts = [
        f"Narrative synthesis covered {grounding.n_studies_synthesized} studies and the overall direction of evidence "
        f"was {_naturalize_label(grounding.synthesis_direction)}."
    ]
    if grounding.narrative_text:
        synthesis_parts.append(str(grounding.narrative_text).strip())
    synthesis_summary = " ".join(part for part in synthesis_parts if part).strip()

    theme_sentences = [
        f"Theme {idx + 1}: {_naturalize_label(theme)}."
        for idx, theme in enumerate((grounding.key_themes or [])[:3])
        if str(theme).strip()
    ]

    studies: list[ResultsEvidenceStudy] = []
    for summary in grounding.study_summaries or []:
        studies.append(
            ResultsEvidenceStudy(
                citekey=_resolve_citekey(summary, grounding),
                title=summary.title,
                study_design=summary.study_design,
                participant_count=summary.participant_count,
                key_finding=summary.key_finding,
            )
        )

    return ResultsEvidencePack(
        study_selection_sentence=selection_sentence,
        characteristics_summary=characteristics_summary,
        synthesis_summary=synthesis_summary,
        theme_sentences=theme_sentences,
        studies=studies,
    )


def render_results_evidence_context(pack: ResultsEvidencePack) -> str:
    lines = [
        "## RESULTS EVIDENCE PLAN (deterministic)",
        f"- Study selection: {pack.study_selection_sentence}",
        f"- Study characteristics: {pack.characteristics_summary}",
        f"- Synthesis summary: {pack.synthesis_summary}",
    ]
    for sentence in pack.theme_sentences:
        lines.append(f"- {sentence}")
    if pack.studies:
        lines.append("- Study-level evidence roster:")
        for study in pack.studies:
            participant_text = f"; participants={study.participant_count}" if study.participant_count is not None else ""
            cite_text = f"[{study.citekey}] " if study.citekey else ""
            lines.append(
                f"  - {cite_text}{study.title} | design={study.study_design}{participant_text} | "
                f"finding={study.key_finding}"
            )
    return "\n".join(lines)


def build_results_section_fallback(
    pack: ResultsEvidencePack,
    *,
    required_subsections: list[str],
    fallback_citations: list[str],
) -> StructuredSectionDraft:
    cited_keys = [study.citekey for study in pack.studies if study.citekey]
    grouped_citations: dict[str, list[str]] = defaultdict(list)
    for study in pack.studies:
        if study.citekey:
            grouped_citations[study.study_design].append(study.citekey)

    blocks: list[SectionBlock] = [
        SectionBlock(block_type="subheading", text="Study Selection", level=3),
        SectionBlock(block_type="paragraph", text=pack.study_selection_sentence),
        SectionBlock(block_type="subheading", text="Study Characteristics", level=3),
        SectionBlock(
            block_type="paragraph",
            text=pack.characteristics_summary,
            citations=fallback_citations or cited_keys[:1],
        ),
    ]

    for design, citekeys in sorted(grouped_citations.items()):
        blocks.append(
            SectionBlock(
                block_type="paragraph",
                text=f"{design} studies contributed to the evidence base summarized in this review.",
                citations=citekeys,
            )
        )

    blocks.append(SectionBlock(block_type="subheading", text="Synthesis of Findings", level=3))
    blocks.append(
        SectionBlock(
            block_type="paragraph",
            text=pack.synthesis_summary,
            citations=fallback_citations or cited_keys[:1],
        )
    )
    for sentence in pack.theme_sentences:
        blocks.append(SectionBlock(block_type="paragraph", text=sentence))
    for study in pack.studies[:6]:
        blocks.append(
            SectionBlock(
                block_type="paragraph",
                text=_study_result_sentence(study),
                citations=[study.citekey] if study.citekey else fallback_citations,
            )
        )

    return StructuredSectionDraft(
        section_key="results",
        cited_keys=sorted(set(cited_keys or fallback_citations)),
        required_subsections=required_subsections,
        blocks=blocks,
    )


def normalize_results_section_draft(
    draft: StructuredSectionDraft,
    pack: ResultsEvidencePack,
    *,
    fallback_citations: list[str],
) -> StructuredSectionDraft:
    """Materialize a complete Results section from evidence plus any useful draft text."""
    section_map: dict[str, list[SectionBlock]] = {heading: [] for heading in _RESULTS_REQUIRED_SUBHEADINGS}
    synthesis_extras: list[SectionBlock] = []
    current_heading = "Synthesis of Findings"

    for block in draft.blocks:
        if block.block_type == "subheading":
            current_heading = _canonical_results_heading(block.text) or "Synthesis of Findings"
            continue
        if block.block_type != "paragraph":
            continue
        target = section_map if current_heading in section_map else None
        if target is not None:
            target[current_heading].append(block)
        else:
            synthesis_extras.append(block)

    grouped_citations: dict[str, list[str]] = defaultdict(list)
    for study in pack.studies:
        if study.citekey:
            grouped_citations[study.study_design].append(study.citekey)

    blocks: list[SectionBlock] = []
    seen_texts: set[str] = set()
    cited_keys: set[str] = set(fallback_citations)

    def _start_subheading(heading: str) -> None:
        blocks.append(SectionBlock(block_type="subheading", text=heading, level=3))

    _start_subheading("Study Selection")
    _append_unique_paragraph(blocks, pack.study_selection_sentence, seen_texts)
    for block in section_map["Study Selection"]:
        _append_unique_block(blocks, block, seen_texts)

    _start_subheading("Study Characteristics")
    _append_unique_paragraph(
        blocks,
        pack.characteristics_summary,
        seen_texts,
        fallback_citations or [study.citekey for study in pack.studies if study.citekey][:1],
    )
    for design, citekeys in sorted(grouped_citations.items()):
        _append_unique_paragraph(
            blocks,
            f"{design} studies contributed to the evidence base summarized in this review.",
            seen_texts,
            citekeys,
        )
    for block in section_map["Study Characteristics"]:
        _append_unique_block(blocks, block, seen_texts)

    _start_subheading("Synthesis of Findings")
    _append_unique_paragraph(
        blocks,
        pack.synthesis_summary,
        seen_texts,
        fallback_citations or [study.citekey for study in pack.studies if study.citekey][:1],
    )
    for sentence in pack.theme_sentences:
        _append_unique_paragraph(blocks, sentence, seen_texts)
    for block in section_map["Synthesis of Findings"] + synthesis_extras:
        _append_unique_block(blocks, block, seen_texts)
    for study in pack.studies[:6]:
        _append_unique_paragraph(
            blocks,
            _study_result_sentence(study),
            seen_texts,
            [study.citekey] if study.citekey else fallback_citations,
        )

    for block in blocks:
        if block.block_type == "paragraph":
            cited_keys.update(block.citations or [])

    return StructuredSectionDraft(
        section_key="results",
        cited_keys=sorted(cited_keys),
        required_subsections=list(_RESULTS_REQUIRED_SUBHEADINGS),
        blocks=blocks,
    )
