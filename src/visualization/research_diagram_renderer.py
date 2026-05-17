"""Gemini-driven custom diagram rendering with iterative critique loops."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from time import monotonic
from typing import Any

import aiohttp
from pydantic import BaseModel
from pydantic_ai.messages import BinaryContent

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import CostRecord
from src.models.diagrams import (
    DiagramBriefPack,
    DiagramCritiqueResult,
    DiagramGenerationReport,
    DiagramGenerationResult,
    DiagramGenerationRound,
    DiagramStyleGuide,
    ResearchDiagramBrief,
)

logger = logging.getLogger(__name__)

_GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class _CritiqueEnvelope(BaseModel):
    critique: DiagramCritiqueResult


def _strip_provider_prefix(model: str) -> str:
    if ":" in model:
        return model.split(":", 1)[1]
    return model


def _extract_inline_image_b64(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates", [])
    for candidate in candidates:
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            inline_data = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline_data, dict) and inline_data.get("data"):
                return str(inline_data["data"])
    return None


def _extract_usage_tokens(payload: dict[str, Any]) -> dict[str, int]:
    """Best-effort usage token extraction from Gemini payloads."""
    usage = payload.get("usageMetadata") or payload.get("usage_metadata") or {}
    if not isinstance(usage, dict):
        return {"tokens_in": 0, "tokens_out": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}

    prompt = int(usage.get("promptTokenCount") or usage.get("prompt_token_count") or 0)
    candidates = int(usage.get("candidatesTokenCount") or usage.get("candidates_token_count") or 0)
    total = int(usage.get("totalTokenCount") or usage.get("total_token_count") or 0)
    cache_read = int(
        usage.get("cachedContentTokenCount")
        or usage.get("cached_content_token_count")
        or usage.get("cacheReadTokenCount")
        or 0
    )
    cache_write = int(usage.get("cacheWriteTokenCount") or usage.get("cache_write_token_count") or 0)
    if candidates <= 0 and total > 0:
        candidates = max(0, total - prompt)
    return {
        "tokens_in": max(0, prompt),
        "tokens_out": max(0, candidates),
        "cache_read_tokens": max(0, cache_read),
        "cache_write_tokens": max(0, cache_write),
    }


def _compose_style_block(style: DiagramStyleGuide) -> str:
    accent_clause = (
        f"Optional single muted accent color {style.accent_hex} is allowed only for one category."
        if style.allow_accent
        else "Use pure monochrome only; do not use accent colors."
    )
    return (
        "Visual style constraints:\n"
        f"- Background {style.white_hex}; primary stroke/text color {style.black_hex}.\n"
        f"- {accent_clause}\n"
        f"- Layered framing: {style.layered_framing}.\n"
        f"- Sparse iconography: {style.sparse_iconography}; max icons {style.max_icons_per_diagram}.\n"
        f"- Max words per label: {style.max_words_per_label}.\n"
        f"- Minimum whitespace ratio: {style.min_whitespace_ratio:.2f}.\n"
        f"- Uniform line weight ~{style.line_weight_px:.1f}px and arrow weight ~{style.arrow_weight_px:.1f}px.\n"
        "- Keep a clean, publication-ready academic style.\n"
    )


def _build_generation_prompt(
    *,
    brief: ResearchDiagramBrief,
    style: DiagramStyleGuide,
    round_index: int,
    revision_prompt: str | None,
) -> str:
    claims_text = []
    for claim in brief.evidence_claims:
        ids = ", ".join(claim.supporting_paper_ids[:6]) or "n/a"
        claims_text.append(f"- {claim.claim} (papers: {ids})")
    claims_block = "\n".join(claims_text) if claims_text else "- No explicit claims."
    required_labels = ", ".join(brief.required_labels)
    relationships = "\n".join(f"- {r}" for r in brief.relationships) if brief.relationships else "- infer concise flow"
    notes = brief.composition_notes or "No extra notes."

    revision_block = (
        f"Revision instructions from critic (must apply):\n{revision_prompt}\n"
        if revision_prompt
        else "No prior critique; produce the best first draft.\n"
    )
    return (
        "Generate a publication-style scientific diagram as an image.\n"
        f"Diagram ID: {brief.diagram_id}\n"
        f"Type: {brief.diagram_type}\n"
        f"Title text in image: {brief.title}\n"
        f"Objective: {brief.objective}\n"
        f"Required labels (must appear exactly or nearly exactly): {required_labels}\n"
        f"Core entities: {', '.join(brief.key_entities)}\n"
        "Relationships to depict:\n"
        f"{relationships}\n"
        "Grounded claims:\n"
        f"{claims_block}\n"
        f"Composition notes: {notes}\n"
        f"Round: {round_index}\n"
        f"{_compose_style_block(style)}"
        f"{revision_block}"
        "Output constraints:\n"
        "- Keep text legible and large enough for manuscript figures.\n"
        "- Avoid decorative textures and gradients.\n"
        "- Ensure clear arrows and logical left-to-right or top-to-bottom flow.\n"
    )


def _read_reference_parts(reference_paths: list[str]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    supported_mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    for path in reference_paths:
        p = Path(path)
        if not p.exists():
            continue
        mime = supported_mime_types.get(p.suffix.lower())
        if mime is None:
            logger.warning("Skipping unsupported diagram reference image type: %s", p.suffix.lower() or "(none)")
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
    return parts


async def _generate_image_via_gemini(
    *,
    model: str,
    prompt: str,
    reference_image_paths: list[str],
    aspect_ratio: str,
    image_size: str,
    timeout_seconds: int = 90,
) -> tuple[bytes, dict[str, int]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; cannot generate custom diagrams.")

    model_ref = _strip_provider_prefix(model)
    url = _GEMINI_GENERATE_CONTENT_URL.format(model=model_ref)
    parts: list[dict[str, Any]] = [{"text": prompt}]
    parts.extend(_read_reference_parts(reference_image_paths))
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
        },
    }
    params = {"key": api_key}
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, params=params, json=body) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Gemini image generation failed {resp.status}: {text[:320]}")
            payload = json.loads(text)
    image_b64 = _extract_inline_image_b64(payload)
    if not image_b64:
        raise RuntimeError("Gemini image response did not contain image bytes.")
    return base64.b64decode(image_b64), _extract_usage_tokens(payload)


async def _critique_image(
    *,
    image_path: Path,
    brief: ResearchDiagramBrief,
    style: DiagramStyleGuide,
    model: str,
    temperature: float = 0.1,
) -> tuple[DiagramCritiqueResult, dict[str, int]]:
    prompt = (
        "You are a strict diagram quality critic for academic figures.\n"
        f"Diagram objective: {brief.objective}\n"
        f"Required labels: {', '.join(brief.required_labels)}\n"
        f"Expected style profile: {style.profile_name} with monochrome/academic tone.\n"
        "Evaluate this image and return JSON with one `critique` object.\n"
        "Scoring guidance:\n"
        "- style_score: adherence to requested monochrome layered style.\n"
        "- legibility_score: text readability and visual clarity.\n"
        "- faithfulness_score: whether flow/claims seem aligned to objective and labels.\n"
        "- approve=true only if all three scores >= 0.72 and no major issues.\n"
        "- issues should list concrete deficiencies.\n"
        "- revision_prompt should be actionable edit instructions.\n"
    )
    media_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    image_part = BinaryContent(data=image_path.read_bytes(), media_type=media_type)
    client = PydanticAIClient()
    parsed, tok_in, tok_out, cache_write, cache_read, retries = await client.complete_validated_parts(
        [image_part, prompt],
        model=model,
        temperature=temperature,
        response_model=_CritiqueEnvelope,
    )
    usage = {
        "tokens_in": tok_in,
        "tokens_out": tok_out,
        "cache_write_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "validation_retries": retries,
    }
    return parsed.critique, usage


async def _log_usage_cost(
    *,
    repository: Any | None,
    workflow_id: str,
    model: str,
    phase: str,
    usage: dict[str, int],
    latency_ms: int,
) -> None:
    if repository is None or not workflow_id:
        return
    tokens_in = int(usage.get("tokens_in", 0))
    tokens_out = int(usage.get("tokens_out", 0))
    cache_write = int(usage.get("cache_write_tokens", 0))
    cache_read = int(usage.get("cache_read_tokens", 0))
    cost = LLMProvider.estimate_cost_usd(
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_write=cache_write,
        cache_read=cache_read,
    )
    await repository.save_cost_record(
        CostRecord(
            workflow_id=workflow_id,
            model=model,
            phase=phase,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
    )


async def render_custom_research_diagrams(
    *,
    brief_pack: DiagramBriefPack,
    out_dir: Path,
    drawing_model: str,
    critic_model: str,
    style_guide: DiagramStyleGuide,
    max_rounds: int = 1,
    image_size: str = "2K",
    aspect_ratio: str = "16:9",
    repository: Any | None = None,
) -> DiagramGenerationReport:
    """Generate custom figures; optional multi-round draw->critic refinement (default: one round)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report = DiagramGenerationReport(
        workflow_id=brief_pack.workflow_id,
        style_profile=style_guide.profile_name,
    )

    for idx, brief in enumerate(brief_pack.diagrams, start=1):
        artifact_key = f"custom_diagram_{idx:02d}"
        latest_revision: str | None = None
        round_records: list[DiagramGenerationRound] = []
        best_result: DiagramGenerationResult | None = None
        reference_paths = list(style_guide.style_reference_paths)

        for round_index in range(1, max(1, max_rounds) + 1):
            output_path = out_dir / f"fig_custom_{idx:02d}_r{round_index:02d}.png"
            prompt = _build_generation_prompt(
                brief=brief,
                style=style_guide,
                round_index=round_index,
                revision_prompt=latest_revision,
            )
            started = monotonic()
            try:
                image_bytes, drawing_usage = await _generate_image_via_gemini(
                    model=drawing_model,
                    prompt=prompt,
                    reference_image_paths=reference_paths,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                )
                output_path.write_bytes(image_bytes)
                await _log_usage_cost(
                    repository=repository,
                    workflow_id=brief_pack.workflow_id,
                    model=drawing_model,
                    phase="phase_6f_custom_diagram_drawing",
                    usage=drawing_usage,
                    latency_ms=int((monotonic() - started) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Custom diagram generation failed (%s round %d): %s", brief.diagram_id, round_index, exc)
                round_records.append(
                    DiagramGenerationRound(
                        round_index=round_index,
                        generation_prompt=prompt,
                        output_path=None,
                        critique=DiagramCritiqueResult(
                            style_score=0.0,
                            legibility_score=0.0,
                            faithfulness_score=0.0,
                            issues=[f"generation failure: {exc}"],
                            revision_prompt="Retry with simpler structure and fewer elements.",
                            approve=False,
                        ),
                    )
                )
                latest_revision = "Simplify layout, reduce density, and preserve required labels."
                continue

            generation_round = DiagramGenerationRound(
                round_index=round_index,
                generation_prompt=prompt,
                output_path=str(output_path),
            )
            try:
                critique_started = monotonic()
                critique, critique_usage = await _critique_image(
                    image_path=output_path,
                    brief=brief,
                    style=style_guide,
                    model=critic_model,
                )
                generation_round.critique = critique
                await _log_usage_cost(
                    repository=repository,
                    workflow_id=brief_pack.workflow_id,
                    model=critic_model,
                    phase="phase_6f_custom_diagram_critic",
                    usage=critique_usage,
                    latency_ms=int((monotonic() - critique_started) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Diagram critic failed (%s round %d): %s", brief.diagram_id, round_index, exc)
                generation_round.critique = DiagramCritiqueResult(
                    style_score=0.55,
                    legibility_score=0.55,
                    faithfulness_score=0.55,
                    issues=[f"critic failure: {exc}"],
                    revision_prompt="Increase legibility and simplify labels.",
                    approve=False,
                )
            round_records.append(generation_round)
            reference_paths.append(str(output_path))
            if len(reference_paths) > 14:
                reference_paths = reference_paths[-14:]

            critique = generation_round.critique
            assert critique is not None
            candidate = DiagramGenerationResult(
                diagram_id=brief.diagram_id,
                artifact_key=artifact_key,
                output_path=str(output_path),
                chosen_round=round_index,
                rounds=list(round_records),
                evidence_paper_ids=brief.target_paper_ids[:],
                required_labels_passed=critique.faithfulness_score >= 0.72 and bool(brief.required_labels),
                grayscale_check_passed=critique.style_score >= 0.72,
                legibility_check_passed=critique.legibility_score >= 0.72,
                warnings=list(critique.issues),
            )
            best_result = candidate
            if critique.approve:
                break
            latest_revision = critique.revision_prompt or "Improve style consistency and label readability."
            await asyncio.sleep(0)

        if best_result is None:
            report.warnings.append(f"{brief.diagram_id}: no usable output was produced.")
            continue

        final_path = out_dir / f"fig_custom_{idx:02d}.png"
        try:
            Path(best_result.output_path).replace(final_path)
            best_result = best_result.model_copy(update={"output_path": str(final_path)})
        except Exception:  # noqa: BLE001
            logger.debug("Could not normalize final filename for %s", brief.diagram_id, exc_info=True)

        if not (
            best_result.required_labels_passed
            and best_result.grayscale_check_passed
            and best_result.legibility_check_passed
        ):
            best_result.warnings.append("quality checks below threshold; accepted as best-effort output")
        report.results.append(best_result)

    return report
