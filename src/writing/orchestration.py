"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import (
    CandidatePaper,
    ClaimRecord,
    EvidenceLinkRecord,
    ReviewConfig,
    SectionOutline,
    SectionQualityScore,
    SectionWriteResult,
    SettingsConfig,
    StructuredSectionDraft,
)

# ---------------------------------------------------------------------------
# Re-exports from decomposed modules (backward compatibility)
# ---------------------------------------------------------------------------
from src.writing.abstract_utils import (  # noqa: F401
    _ABSTRACT_FIELDS,
    _abstract_body_word_count,
    _append_abstract_field_sentence,
    _ensure_structured_abstract,
    _normalize_structured_abstract_fields,
    _replace_or_append_abstract_field,
    _strip_abstract_citation_markup,
    canonicalize_structured_abstract_markdown,
    parse_structured_abstract_markdown,
    validate_structured_abstract_markdown_band,
)
from src.writing.citation_catalog import (  # noqa: F401
    _GENERIC_AUTHOR_TOKENS,
    _GENERIC_TITLE_WORDS,
    _METHODOLOGY_REFS,
    _citation_coverage_issues,
    _citation_entries_from_papers,
    _clean_author_token,
    _compute_section_citation_budget,
    _extract_included_study_citekeys,
    _extract_valid_citekeys,
    _make_citekey_base,
    _sanitize_citekey_token,
    build_background_sr_catalog,
    build_citation_catalog_from_papers,
    build_methodology_catalog,
    register_background_sr_citations,
    register_citations_from_papers,
    register_methodology_citations,
)
from src.writing.evidence_assembler import (
    build_results_evidence_pack,
    normalize_results_section_draft,
    render_results_evidence_context,
)
from src.writing.grounding_patches import (  # noqa: F401
    _append_or_inject_subsection,
    _apply_markdown_transform_to_structured,
    _apply_structured_grounding_patches,
    _patch_abstract_grounding,
    _patch_conclusion_grounding,
    _patch_discussion_grounding,
    _patch_introduction_grounding,
    _patch_methods_grounding,
    _patch_results_grounding,
    _replace_or_append_subsection,
    _replace_phrase_variants_case_insensitive,
    _structured_from_markdown,
)
from src.writing.humanizer_guardrails import apply_deterministic_guardrails
from src.writing.renderers import render_section_markdown
from src.writing.section_fallbacks import (  # noqa: F401
    _build_deterministic_section_fallback,
    _build_minimum_compliant_abstract,
    _expand_abstract_to_minimum_words,
    _format_abstract_design_summary,
)
from src.writing.section_validation import (  # noqa: F401
    _BEST_EFFORT_ISSUE_PREFIXES,
    _best_effort_accept,
    _draft_substantive_paragraph_count,
    _draft_word_count,
    _extract_count,
    _grounding_integrity_issues,
    _is_best_effort_issue,
    _is_low_volume_review,
    _is_minimally_substantive_paragraph,
    _is_substantive_paragraph,
    _outline_coverage_issues,
    _outline_terms,
    _post_render_completeness_issues,
    _rendered_citation_integrity_issues,
    _sanitize_ir_block_text,
    _section_completeness_issues,
    _topic_anchor_issues,
    _validate_structured_section_draft,
    compute_section_quality_score,
    format_quality_feedback,
)
from src.writing.section_writer import SectionWriter

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_CITEKEY_RE = re.compile(r"\[([A-Za-z0-9_:-]+)\]")
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b")
_SECTION_NAMES = frozenset({"introduction", "methods", "results", "discussion", "conclusion", "abstract"})


def _sanitize_prose(content: str) -> str:
    """Normalize whitespace and enforce ASCII-safe manuscript prose."""
    sanitized = content
    sanitized = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", sanitized)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    sanitized = _SNAKE_CASE_RE.sub(lambda m: m.group(0).replace("_", " "), sanitized)
    if sanitized != content:
        logger.debug("prose sanitizer normalized non-ASCII and spacing in section draft")
    return sanitized


def _sanitize_section_headings(section: str, content: str) -> str:
    """Normalize malformed heading lines before section persistence."""
    out_lines: list[str] = []
    last_heading = ""
    _spill_start_re = re.compile(
        r"\b(The|This|These|We|Our|In|Across|To|A|An|Evidence|Findings|Overall|One|Studies|Demographic|Meta-analysis|Also)\b"
    )
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("## "):
            m_h2 = re.match(r"^##\s+([A-Za-z]+)\b(.*)$", stripped)
            if m_h2 and m_h2.group(1).lower() in _SECTION_NAMES:
                tail = m_h2.group(2).strip()
                if tail:
                    out_lines.append(tail)
                i += 1
                continue
        if stripped.startswith("### ") or stripped.startswith("#### "):
            prefix = "####" if stripped.startswith("#### ") else "###"
            title = stripped[len(prefix) + 1 :].strip()
            known_heading_prefixes = (
                "Eligibility Criteria",
                "Information Sources",
                "Search Strategy",
                "Selection Process",
                "Data Collection Process",
                "Data Items",
                "Risk of Bias",
                "Risk of Bias Assessment",
                "Risk of Bias and Critical Appraisal",
                "Synthesis Methods",
                "Protocol Registration",
                "Study Selection",
                "Study Characteristics",
                "Synthesis of Findings",
                "Comparison with Prior Work",
            )
            if title.lower().endswith((" and", " or", " of", " for", " to", " with")):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    nxt = lines[j].strip()
                    if nxt and not nxt.startswith("#"):
                        if title.lower() == "risk of" and nxt.lower().startswith("bias and critical appraisal"):
                            title = "Risk of Bias and Critical Appraisal"
                            remainder = nxt[len("Bias and Critical Appraisal") :].strip()
                            lines[j] = remainder if remainder else ""
                            nxt = lines[j].strip()
                        title_low = title.lower()
                        matched_known = None
                        for known in sorted(known_heading_prefixes, key=len, reverse=True):
                            known_low = known.lower()
                            if known_low.startswith(title_low + " "):
                                remainder_tail = known[len(title) :].strip()
                                if nxt.lower().startswith(remainder_tail.lower()):
                                    matched_known = (known, remainder_tail)
                                    break
                        if matched_known is not None:
                            known_title, tail = matched_known
                            title = known_title
                            remainder = nxt[len(tail) :].strip()
                            lines[j] = remainder if remainder else ""
                            nxt = lines[j].strip()
                        words = nxt.split()
                        consumed = 0
                        for w in words:
                            w_clean = w.strip(".,;:!?")
                            if not w_clean:
                                break
                            if w_clean.lower() in {"and", "or", "of", "for", "to", "with"}:
                                consumed += 1
                                continue
                            if not w_clean[:1].isupper():
                                break
                            consumed += 1
                            if consumed >= 6:
                                break
                        if consumed > 0:
                            title = (title + " " + " ".join(words[:consumed])).strip()
                            remainder = " ".join(words[consumed:]).strip()
                            if remainder:
                                lines[j] = remainder
                            else:
                                lines[j] = ""
            title = re.sub(r"\s*(?:\[[^\]]+\]\s*)+", " ", title).strip()
            title = re.sub(r"\s*\\cite\{[^}]+\}", " ", title).strip()
            title = re.split(r"[.;:!?]\s+", title, maxsplit=1)[0]
            lower_title = title.lower()
            if (
                len(title.split()) > 8
                and re.search(r"\s+(?:was|were)\s+", title)
                and not any(lower_title.startswith(h.lower() + " ") for h in known_heading_prefixes)
            ):
                title = re.split(r"\s+(?:was|were)\s+", title, maxsplit=1)[0]
            if title.lower() in _SECTION_NAMES:
                continue
            if title.lower().endswith((" and", " of", " for", " to", " with")):
                continue
            title = re.sub(r"\s{2,}", " ", title).strip(" -:")
            if not title:
                continue
            if title.lower() == last_heading.lower():
                continue
            spill_match = _spill_start_re.search(title)
            if spill_match and spill_match.start() > 8:
                heading_text = title[: spill_match.start()].strip(" -:")
                body_text = title[spill_match.start() :].strip()
                if heading_text:
                    out_lines.append(f"{prefix} {heading_text}")
                    out_lines.append("")
                    if body_text:
                        out_lines.append(body_text)
                    last_heading = heading_text
                    i += 1
                    continue
            split_applied = False
            for known in known_heading_prefixes:
                lower_known = known.lower()
                if lower_title.startswith(lower_known + " "):
                    heading_text = known
                    body_text = title[len(known) :].strip()
                    out_lines.append(f"{prefix} {heading_text}")
                    out_lines.append("")
                    if body_text:
                        out_lines.append(body_text)
                    last_heading = heading_text
                    i += 1
                    split_applied = True
                    break
            if split_applied:
                continue
            words = title.split()
            if len(words) > 14:
                title = " ".join(words[:14]).strip()
            line = f"{prefix} {title}"
            last_heading = title
        out_lines.append(line)
        i += 1
    return "\n".join(out_lines).strip()


def _needs_legacy_heading_fix(content: str) -> bool:
    """Return whether rendered markdown still looks like malformed legacy output."""
    text = str(content or "")
    return bool(
        re.search(r"(?m)^#{2,6}[ \t]+[^\n]+[ \t]+#{2,6}[ \t]+", text)
        or re.search(r"(?m)^#{2,6}[ \t]+\S[^\n]{8,}[ \t]+(?:The|This|These|for|in|Across|To)\b", text)
    )


def _render_and_sanitize(
    section: str,
    structured: StructuredSectionDraft,
    *,
    grounding: WritingGroundingData | None,
    review: ReviewConfig,
    settings: SettingsConfig,
    valid_citekeys: set[str],
) -> tuple[StructuredSectionDraft, str, bool]:
    """Apply grounding patches then render/sanitize markdown once."""
    patched = _apply_structured_grounding_patches(
        section,
        structured,
        grounding=grounding,
        review=review,
        settings=settings,
        valid_citekeys=valid_citekeys,
    )
    content = render_section_markdown(patched)
    content = _sanitize_prose(content)
    if section != "abstract" and _needs_legacy_heading_fix(content):
        content = _sanitize_section_headings(section, content)
    content = apply_deterministic_guardrails(content)

    floor_forced = False
    if section == "abstract" and grounding is not None:
        minimum_words = int(getattr(getattr(settings, "writing", None), "abstract_trim_floor_words", 210))
        if _abstract_body_word_count(content) < minimum_words:
            logger.warning(
                "Section '%s' remained below the minimum abstract floor after guardrails; "
                "forcing deterministic compliant abstract.",
                section,
            )
            content = _build_minimum_compliant_abstract(review, grounding, minimum_words)
            floor_forced = True

    if content.strip() != render_section_markdown(patched).strip():
        patched = _structured_from_markdown(section, content, valid_citekeys, template=patched)
    return patched, content, floor_forced


def _draft_fingerprint(draft: StructuredSectionDraft) -> str:
    """Return a stable content hash for duplicate ratchet detection."""
    payload = json.dumps(
        [
            {"block_type": b.block_type, "text": b.text, "level": b.level, "citations": list(b.citations or [])}
            for b in draft.blocks
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def extract_and_register_claims(
    section: str,
    content: str,
    citation_repo: CitationRepository,
) -> int:
    """Extract cited sentences and register claim->evidence links."""
    citekey_to_id = await citation_repo.get_citation_map()
    if not citekey_to_id:
        return 0
    sentences = _SENTENCE_SPLIT_RE.split(content)
    if len(sentences) <= 1:
        sentences = [line.strip() for line in content.splitlines() if line.strip()]
    claims_registered = 0
    for sentence in sentences:
        keys = _CITEKEY_RE.findall(sentence)
        if not keys:
            continue
        resolved_keys = [(k, citekey_to_id[k]) for k in keys if k in citekey_to_id]
        if not resolved_keys:
            continue
        claim = ClaimRecord(claim_text=sentence[:2000], section=section, confidence=1.0)
        try:
            await citation_repo.register_claim(claim)
        except Exception as exc:
            logger.debug("Skipping duplicate or invalid claim for section '%s': %s", section, exc)
            continue
        for citekey, citation_id in resolved_keys:
            link = EvidenceLinkRecord(
                claim_id=claim.claim_id,
                citation_id=citation_id,
                evidence_span=citekey,
                evidence_score=1.0,
            )
            try:
                await citation_repo.link_evidence(link)
            except Exception as exc:
                logger.debug("Failed to link evidence %s -> %s: %s", claim.claim_id, citation_id, exc)
        claims_registered += 1
    return claims_registered


async def write_section_with_validation(
    section: str,
    context: str,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    citation_repo: CitationRepository,
    citation_catalog: str = "",
    word_limit: int | None = None,
    on_llm_call: Callable[..., None] | None = None,
    provider=None,
    grounding: WritingGroundingData | None = None,
    rag_context: str = "",
    prior_sections_context: str = "",
    outline: SectionOutline | None = None,
) -> SectionWriteResult:
    """Write a section, validate with citation ledger, return content."""
    from src.writing.prompts.sections import get_section_context

    effective_context = get_section_context(section, grounding=grounding) if grounding is not None else context
    if prior_sections_context:
        effective_context = effective_context + "\n\n" + prior_sections_context
    if rag_context:
        effective_context = (
            effective_context
            + "\n\nRAG PRIORITY RULE: For section-specific factual claims, prioritize the retrieved evidence chunks below. "
            + "When a retrieved chunk conflicts with the FACTUAL DATA BLOCK, the FACTUAL DATA BLOCK takes precedence.\n"
            + "\n## Relevant Evidence Chunks (retrieved by semantic search)\n"
            + rag_context
        )
    if section == "results" and grounding is not None:
        effective_context = (
            effective_context + "\n\n" + render_results_evidence_context(build_results_evidence_pack(grounding))
        )

    writer = SectionWriter(review=review, settings=settings, citation_catalog=citation_catalog)
    valid_citekeys = _extract_valid_citekeys(citation_catalog)
    included_study_count = int(getattr(grounding, "total_included", 0) or 0) if grounding is not None else 0
    results_pack = build_results_evidence_pack(grounding) if section == "results" else None

    async def _generate_structured_once(ctx: str) -> tuple[StructuredSectionDraft, object, list[str]]:
        if provider is not None:
            await provider.reserve_call_slot("writing")
        _structured, _metadata = await writer.write_section_structured_async(
            section=section,
            context=ctx,
            word_limit=word_limit,
        )
        _structured, _contract_issues = _validate_structured_section_draft(section, _structured, valid_citekeys)
        if section == "results" and results_pack is not None:
            _structured = normalize_results_section_draft(
                _structured,
                results_pack,
                fallback_citations=sorted(valid_citekeys)[:1],
            )
        if provider and _metadata.cost_usd is not None:
            try:
                await provider.log_cost(
                    model=_metadata.model,
                    tokens_in=_metadata.tokens_in,
                    tokens_out=_metadata.tokens_out,
                    cost_usd=_metadata.cost_usd,
                    latency_ms=_metadata.latency_ms,
                    phase="phase_6_writing",
                    cache_read_tokens=_metadata.cache_read_tokens,
                    cache_write_tokens=_metadata.cache_write_tokens,
                )
            except Exception as _log_exc:
                logger.warning("Failed to persist writing cost for section '%s': %s", section, _log_exc)
        return _structured, _metadata, _contract_issues

    must_cite = _compute_section_citation_budget(section, citation_catalog, valid_citekeys)

    async def _materialize_candidate(
        candidate_context: str,
    ) -> tuple[StructuredSectionDraft, str, int, list[str], bool, object]:
        validation_retries = 0
        used_deterministic_fallback = False
        validation_issues: list[str] = []
        candidate_cost_usd = 0.0
        structured, metadata, contract_issues = await _generate_structured_once(candidate_context)
        candidate_cost_usd += float(getattr(metadata, "cost_usd", 0.0) or 0.0)
        issues = _section_completeness_issues(section, structured, included_study_count)
        issues.extend(contract_issues)
        cite_issues, missing_keys = _citation_coverage_issues(section, structured, must_cite)
        issues.extend(cite_issues)
        if issues:
            validation_retries += 1
            retry_parts = [
                "\n\nRETRY RULE: Your previous output failed completeness checks: "
                + ", ".join(issues)
                + ". Regenerate this section with complete subsection bodies and a fully closed final sentence.",
            ]
            if missing_keys:
                sorted_missing = sorted(missing_keys)[:30]
                retry_parts.append(
                    "\n\nCRITICAL CITATION COVERAGE: You MUST cite the following studies that were "
                    "omitted from your previous output. Add each study to the relevant block.citations "
                    "array and include it in cited_keys. Do NOT place [AuthorYear] tokens in block.text:\n"
                    + "\n".join(f"  - [{k}]" for k in sorted_missing)
                )
            retry_context = candidate_context + "".join(retry_parts)
            logger.warning(
                "Section '%s' failed IR completeness checks (%s); retrying once.", section, ", ".join(issues)
            )
            structured, metadata, contract_issues = await _generate_structured_once(retry_context)
            candidate_cost_usd += float(getattr(metadata, "cost_usd", 0.0) or 0.0)
            issues = _section_completeness_issues(section, structured, included_study_count)
            issues.extend(contract_issues)
            if issues:
                validation_issues = sorted(set(issues))
                fallback_structured = _build_deterministic_section_fallback(section, grounding, valid_citekeys)
                if _best_effort_accept(
                    section, structured, fallback_structured, validation_issues, included_study_count
                ):
                    logger.warning(
                        "Section '%s' still failed completeness checks after retry (%s); keeping best-effort content.",
                        section,
                        ", ".join(validation_issues),
                    )
                else:
                    logger.warning(
                        "Section '%s' still failed completeness checks after retry (%s); using deterministic fallback.",
                        section,
                        ", ".join(validation_issues),
                    )
                    structured = fallback_structured
                    used_deterministic_fallback = True
        structured, content, floor_forced = _render_and_sanitize(
            section,
            structured,
            grounding=grounding,
            review=review,
            settings=settings,
            valid_citekeys=valid_citekeys,
        )
        if floor_forced:
            used_deterministic_fallback = True
        rendered_citation_issues = _rendered_citation_integrity_issues(content, valid_citekeys)
        if rendered_citation_issues:
            validation_issues = sorted(set(validation_issues + rendered_citation_issues))
        grounding_issues = _grounding_integrity_issues(section, content, grounding)
        if grounding_issues:
            validation_issues = sorted(set(validation_issues + grounding_issues))
        hard_render_issues = rendered_citation_issues + grounding_issues
        if hard_render_issues and section in {"abstract", "methods", "results", "discussion", "conclusion"}:
            fallback_structured = _build_deterministic_section_fallback(section, grounding, valid_citekeys)
            if _best_effort_accept(section, structured, fallback_structured, validation_issues, included_study_count):
                logger.warning(
                    "Section '%s' hit rendered-content integrity issues (%s); keeping best-effort content.",
                    section,
                    ", ".join(sorted(set(hard_render_issues))),
                )
            else:
                logger.warning(
                    "Section '%s' hit rendered-content integrity issues (%s); forcing deterministic fallback.",
                    section,
                    ", ".join(sorted(set(hard_render_issues))),
                )
                structured = fallback_structured
                used_deterministic_fallback = True
                structured, content, floor_forced = _render_and_sanitize(
                    section,
                    structured,
                    grounding=grounding,
                    review=review,
                    settings=settings,
                    valid_citekeys=valid_citekeys,
                )
                if floor_forced:
                    used_deterministic_fallback = True
        post_issues = _post_render_completeness_issues(section, content, included_study_count)
        topic_issues = _topic_anchor_issues(section, content, grounding)
        if topic_issues:
            validation_issues = sorted(set(validation_issues + topic_issues))
            logger.warning(
                "Section '%s' hit soft topic-anchor issues (%s); keeping generated content.",
                section,
                ", ".join(topic_issues),
            )
        if post_issues and section in {"methods", "results", "discussion", "conclusion"}:
            validation_issues = sorted(set(validation_issues + post_issues))
            fallback_structured = _build_deterministic_section_fallback(section, grounding, valid_citekeys)
            if _best_effort_accept(section, structured, fallback_structured, validation_issues, included_study_count):
                logger.warning(
                    "Section '%s' failed post-render completeness checks (%s); keeping best-effort content.",
                    section,
                    ", ".join(validation_issues),
                )
            else:
                logger.warning(
                    "Section '%s' failed post-render completeness checks (%s); forcing deterministic fallback.",
                    section,
                    ", ".join(validation_issues),
                )
                structured = fallback_structured
                used_deterministic_fallback = True
                structured, content, floor_forced = _render_and_sanitize(
                    section,
                    structured,
                    grounding=grounding,
                    review=review,
                    settings=settings,
                    valid_citekeys=valid_citekeys,
                )
                if floor_forced:
                    used_deterministic_fallback = True
        if hasattr(metadata, "cost_usd"):
            metadata.cost_usd = candidate_cost_usd
        return (structured, content, validation_retries, validation_issues, used_deterministic_fallback, metadata)

    workflow_repo = WorkflowRepository(citation_repo.db)
    ratchet_max = max(1, int(getattr(getattr(settings, "writing", None), "ratchet_max_iterations", 1)))
    cost_cap = float(getattr(getattr(settings, "writing", None), "ratchet_cost_cap_per_section", 0.15))
    best_candidate: tuple[StructuredSectionDraft, str, int, list[str], bool, object] | None = None
    best_score = SectionQualityScore.worst()
    best_issues: list[str] = []
    best_iteration_index = 0
    prev_fingerprint: str | None = None
    cumulative_cost_usd = 0.0
    ratchet_trace: list[dict[str, object]] = []

    for iteration in range(ratchet_max):
        if iteration > 0:
            if provider is not None:
                total_run_cost = await workflow_repo.get_total_cost(workflow_id)
                if total_run_cost >= float(getattr(getattr(settings, "gates", None), "cost_budget_max", 0.0)):
                    logger.warning(
                        "Section '%s' ratchet stopped before iteration %d because run cost budget was exhausted.",
                        section,
                        iteration + 1,
                    )
                    break
            if cumulative_cost_usd >= cost_cap:
                logger.warning(
                    "Section '%s' ratchet stopped before iteration %d because per-section cost cap %.2f USD was reached.",
                    section,
                    iteration + 1,
                    cost_cap,
                )
                break

        iter_context = effective_context
        if iteration > 0 and best_issues:
            iter_context = effective_context + format_quality_feedback(best_issues, best_score)

        candidate = await _materialize_candidate(iter_context)
        structured, content, validation_retries, validation_issues, used_deterministic_fallback, metadata = candidate
        cumulative_cost_usd += float(getattr(metadata, "cost_usd", 0.0) or 0.0)
        fingerprint = _draft_fingerprint(structured)

        score, scored_issues = compute_section_quality_score(
            section=section,
            draft=structured,
            rendered=content,
            outline=outline,
            grounding=grounding,
            valid_citekeys=valid_citekeys,
            must_cite=must_cite,
            settings=settings,
            included_study_count=included_study_count,
        )
        if validation_issues:
            scored_issues = list(dict.fromkeys([*scored_issues, *validation_issues]))
        ratchet_trace.append(
            {
                "iteration": iteration + 1,
                "score": score.model_dump(),
                "issue_count": len(scored_issues),
                "issues": scored_issues[:20],
                "cost_usd": float(getattr(metadata, "cost_usd", 0.0) or 0.0),
                "fallback_used": bool(used_deterministic_fallback),
                "validation_retries": int(validation_retries),
            }
        )

        improved = best_candidate is None or score > best_score
        if improved:
            best_candidate = candidate
            best_score = score
            best_issues = scored_issues
            best_iteration_index = iteration + 1

        if iteration > 0 and fingerprint == prev_fingerprint:
            logger.warning(
                "Section '%s' ratchet stopped at iteration %d because the draft fingerprint repeated.",
                section,
                iteration + 1,
            )
            break
        prev_fingerprint = fingerprint

        if iteration > 0 and not improved:
            logger.warning(
                "Section '%s' ratchet stopped at iteration %d because quality plateaued.", section, iteration + 1
            )
            break
        if iteration == 0 and used_deterministic_fallback:
            logger.warning(
                "Section '%s' used deterministic fallback on the first iteration; skipping further ratchet rewrites.",
                section,
            )
            break

    assert best_candidate is not None
    structured, content, validation_retries, validation_issues, used_deterministic_fallback, metadata = best_candidate
    validation_issues = best_issues

    try:
        n_claims = await extract_and_register_claims(section, content, citation_repo)
        if n_claims:
            logger.debug("Registered %d claim-evidence links for section '%s'", n_claims, section)
    except Exception as exc:
        logger.warning("Claim extraction failed for section '%s': %s", section, exc)

    ledger = CitationLedger(citation_repo)
    result = await ledger.validate_section(section, content)
    if result.unresolved_citations:
        logger.warning(
            "Section '%s' contains %d unresolved citation key(s): %s",
            section,
            len(result.unresolved_citations),
            ", ".join(result.unresolved_citations[:10]),
        )
    if result.unresolved_claims:
        logger.warning("Section '%s' has %d claim(s) without linked evidence.", section, len(result.unresolved_claims))
    ratchet_meta_json = json.dumps(
        {
            "ratchet_iterations": len(ratchet_trace),
            "ratchet_scores": [entry["score"] for entry in ratchet_trace],
            "ratchet_trace": ratchet_trace,
            "ratchet_winner": best_iteration_index,
            "ratchet_cost_usd": round(cumulative_cost_usd, 6),
        },
        sort_keys=True,
    )
    if on_llm_call:
        word_count = len(content.split())
        on_llm_call(
            source="writing",
            status="success",
            details=section,
            records=None,
            call_type="llm_writing",
            raw_response=content,
            latency_ms=metadata.latency_ms,
            model=metadata.model,
            paper_id=None,
            phase="phase_6_writing",
            tokens_in=metadata.tokens_in,
            tokens_out=metadata.tokens_out,
            cost_usd=metadata.cost_usd,
            section_name=section,
            word_count=word_count,
        )
    return SectionWriteResult(
        section_key=section,
        content_markdown=content,
        structured_draft=structured,
        cited_keys=sorted(structured.cited_keys or []),
        word_count=len(content.split()),
        validation_retries=validation_retries,
        validation_issues=validation_issues,
        fallback_used=used_deterministic_fallback,
        used_deterministic_fallback=used_deterministic_fallback,
        ratchet_meta_json=ratchet_meta_json,
    )


def prepare_writing_context(
    included_papers: list[CandidatePaper],
    settings: SettingsConfig,
    background_sr_rows: list[tuple[str, str, int | None]] | None = None,
) -> str:
    """Build the citation catalog for the writing phase."""
    _ = settings
    included_catalog = build_citation_catalog_from_papers(included_papers)
    methodology_catalog = build_methodology_catalog()
    background_sr_catalog = build_background_sr_catalog(background_sr_rows or [])
    catalog_parts = [included_catalog]
    if background_sr_catalog:
        catalog_parts.append("# Background systematic reviews (for Discussion comparison):")
        catalog_parts.append(background_sr_catalog)
    if methodology_catalog:
        catalog_parts.append("# Methodology references (cite when describing study design, PRISMA, GRADE, RoB):")
        catalog_parts.append(methodology_catalog)
    return "\n".join(catalog_parts)
