"""Deterministic evidence assembly for the Results section."""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from src.models import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import StudySummary, WritingGroundingData

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_title(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", str(text or "").lower()).strip()


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
        f"was {grounding.synthesis_direction.replace('_', ' ')}."
    ]
    if grounding.narrative_text:
        synthesis_parts.append(str(grounding.narrative_text).strip())
    synthesis_summary = " ".join(part for part in synthesis_parts if part).strip()

    theme_sentences = [
        f"Theme {idx + 1}: {theme}."
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
                text=f"{study.title} reported the following key finding: {study.key_finding}",
                citations=[study.citekey] if study.citekey else fallback_citations,
            )
        )

    return StructuredSectionDraft(
        section_key="results",
        cited_keys=sorted(set(cited_keys or fallback_citations)),
        required_subsections=required_subsections,
        blocks=blocks,
    )
