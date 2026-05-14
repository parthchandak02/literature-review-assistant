"""Build grounded custom-diagram briefs from included studies and file manifests."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm.pydantic_client import PydanticAIClient
from src.models.diagrams import (
    DiagramBriefPack,
    DiagramEvidenceClaim,
    ResearchDiagramBrief,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_STUDIES_IN_PROMPT = 24


def _clip_text(value: str | None, max_chars: int) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _format_manifest_samples(
    manifest_entries: dict[str, dict[str, Any]] | list[dict[str, Any]],
    *,
    max_items: int = 48,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(manifest_entries, dict):
        iter_rows = []
        for paper_id, entry in manifest_entries.items():
            e = entry if isinstance(entry, dict) else {}
            iter_rows.append({"paper_id": paper_id, **e})
    else:
        iter_rows = [r for r in manifest_entries if isinstance(r, dict)]

    for row in iter_rows[:max_items]:
        rows.append(
            {
                "paper_id": str(row.get("paper_id", "")),
                "title": _clip_text(str(row.get("title", "")), 180),
                "source": _clip_text(str(row.get("source", "")), 40),
                "file_type": _clip_text(str(row.get("file_type", "")), 12),
            }
        )
    return rows


def _format_included_study_samples(
    included_studies: list[dict[str, Any]],
    extraction_summaries: list[dict[str, Any]] | None,
    *,
    max_items: int = _DEFAULT_MAX_STUDIES_IN_PROMPT,
) -> list[dict[str, Any]]:
    extraction_by_paper: dict[str, dict[str, Any]] = {}
    for row in extraction_summaries or []:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        if paper_id:
            extraction_by_paper[paper_id] = row

    rows: list[dict[str, Any]] = []
    for study in included_studies[:max_items]:
        paper_id = str(study.get("paper_id", "")).strip()
        ex = extraction_by_paper.get(paper_id, {})
        rows.append(
            {
                "paper_id": paper_id,
                "title": _clip_text(str(study.get("title", "")), 180),
                "year": study.get("year"),
                "study_design": _clip_text(str(ex.get("study_design", "")), 80),
                "primary_outcome": _clip_text(str(ex.get("primary_outcome", "")), 220),
                "intervention": _clip_text(str(ex.get("intervention", "")), 220),
                "population": _clip_text(str(ex.get("population", "")), 180),
                "summary": _clip_text(str(ex.get("summary", "")), 260),
            }
        )
    return rows


def _fallback_brief_pack(
    *,
    workflow_id: str,
    review_topic: str,
    included_paper_ids: list[str],
    source_included_count: int,
    source_file_count: int,
) -> DiagramBriefPack:
    common_ids = included_paper_ids[: min(8, len(included_paper_ids))]
    return DiagramBriefPack(
        workflow_id=workflow_id,
        source_included_count=max(1, source_included_count),
        source_file_count=max(0, source_file_count),
        diagrams=[
            ResearchDiagramBrief(
                diagram_id="custom_01_layered_architecture",
                diagram_type="layered_architecture",
                title="Research Synthesis System Architecture",
                objective="Show how selected-study evidence is transformed into synthesis insights.",
                required_labels=["Input Studies", "Extraction Layer", "Synthesis Layer", "Output Insights"],
                key_entities=["studies", "extraction", "quality assessment", "synthesis"],
                relationships=[
                    "Input Studies -> Extraction Layer",
                    "Extraction Layer -> Synthesis Layer",
                    "Synthesis Layer -> Output Insights",
                ],
                evidence_claims=[
                    DiagramEvidenceClaim(
                        claim="Architecture summarizes evidence-processing stages grounded in included studies.",
                        supporting_paper_ids=common_ids,
                    )
                ],
                target_paper_ids=common_ids,
            ),
            ResearchDiagramBrief(
                diagram_id="custom_02_method_flow",
                diagram_type="method_flow",
                title="Included-Study Processing Flow",
                objective="Illustrate the end-to-end methodological flow from final PDFs to conclusions.",
                required_labels=["Included PDFs", "Screening Outcome", "Extraction", "Quality", "Findings"],
                key_entities=["pdfs", "screening", "extraction", "quality", "findings"],
                relationships=[
                    "Included PDFs -> Extraction",
                    "Extraction -> Quality",
                    "Quality -> Findings",
                ],
                evidence_claims=[
                    DiagramEvidenceClaim(
                        claim="Flow emphasizes steps used to produce final claims from included papers.",
                        supporting_paper_ids=common_ids,
                    )
                ],
                target_paper_ids=common_ids,
                composition_notes=f"Topic anchor: {review_topic}",
            ),
        ],
    )


def _build_preparer_prompt(
    *,
    workflow_id: str,
    review_topic: str,
    research_question: str,
    included_study_samples: list[dict[str, Any]],
    manifest_samples: list[dict[str, str]],
    source_included_count: int,
    source_file_count: int,
) -> str:
    studies_json = json.dumps(included_study_samples, ensure_ascii=True, indent=2)
    manifest_json = json.dumps(manifest_samples, ensure_ascii=True, indent=2)
    return (
        "You are a Diagram Preparer Agent for systematic review manuscripts.\n"
        "Generate exactly 2 or 3 grounded custom diagram briefs.\n"
        "Each diagram must be original, simple, and suitable for academic black-and-white visuals.\n"
        "Do not invent unsupported findings; use only provided studies.\n\n"
        f"Workflow ID: {workflow_id}\n"
        f"Review Topic: {review_topic}\n"
        f"Research Question: {research_question}\n"
        f"Total included studies: {source_included_count}\n"
        f"Total downloadable files: {source_file_count}\n\n"
        "Included study samples:\n"
        f"{studies_json}\n\n"
        "Manifest file samples:\n"
        f"{manifest_json}\n\n"
        "Output requirements:\n"
        "- Return valid JSON only.\n"
        "- workflow_id must match input exactly.\n"
        "- source_included_count and source_file_count must match input counts.\n"
        "- diagrams length must be 2 or 3.\n"
        "- diagram_type must be one of: layered_architecture, method_flow, evidence_map, theme_relationship.\n"
        "- Every diagram must include at least 3 required_labels.\n"
        "- Every diagram must include at least one evidence_claim with supporting_paper_ids drawn from sampled papers.\n"
    )


async def prepare_research_diagram_briefs(
    *,
    workflow_id: str,
    review_topic: str,
    research_question: str,
    included_studies: list[dict[str, Any]],
    extraction_summaries: list[dict[str, Any]] | None,
    manifest_entries: dict[str, dict[str, Any]] | list[dict[str, Any]],
    model: str,
    temperature: float = 0.2,
    max_validation_retries: int = 2,
) -> tuple[DiagramBriefPack, dict[str, int]]:
    """Return grounded diagram briefs and token usage metadata."""
    included_ids = [str(row.get("paper_id", "")).strip() for row in included_studies if row.get("paper_id")]
    source_included_count = len(included_ids)
    source_file_count = (
        len(manifest_entries) if isinstance(manifest_entries, dict) else len([x for x in manifest_entries if x])
    )

    included_samples = _format_included_study_samples(included_studies, extraction_summaries)
    manifest_samples = _format_manifest_samples(manifest_entries)
    prompt = _build_preparer_prompt(
        workflow_id=workflow_id,
        review_topic=review_topic,
        research_question=research_question,
        included_study_samples=included_samples,
        manifest_samples=manifest_samples,
        source_included_count=source_included_count,
        source_file_count=source_file_count,
    )

    usage = {
        "tokens_in": 0,
        "tokens_out": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "validation_retries": 0,
    }
    client = PydanticAIClient()
    try:
        parsed, tok_in, tok_out, cache_write, cache_read, retries_used = await client.complete_validated(
            prompt,
            model=model,
            temperature=temperature,
            response_model=DiagramBriefPack,
            max_validation_retries=max_validation_retries,
        )
        usage.update(
            {
                "tokens_in": tok_in,
                "tokens_out": tok_out,
                "cache_write_tokens": cache_write,
                "cache_read_tokens": cache_read,
                "validation_retries": retries_used,
            }
        )
        diagrams = parsed.diagrams[:3]
        if len(diagrams) < 2:
            raise ValueError("Diagram preparer returned fewer than 2 diagram briefs")
        normalized = parsed.model_copy(
            update={
                "workflow_id": workflow_id,
                "source_included_count": max(1, source_included_count),
                "source_file_count": max(0, source_file_count),
                "diagrams": diagrams,
            }
        )
        return normalized, usage
    except Exception as exc:  # noqa: BLE001
        logger.warning("Diagram preparer failed for %s, using fallback briefs: %s", workflow_id, exc)
        return (
            _fallback_brief_pack(
                workflow_id=workflow_id,
                review_topic=review_topic,
                included_paper_ids=included_ids,
                source_included_count=source_included_count,
                source_file_count=source_file_count,
            ),
            usage,
        )
