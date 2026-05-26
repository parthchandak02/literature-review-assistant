"""Section validation, quality scoring, and completeness checks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.models import (
    SectionBlock,
    SectionOutline,
    SectionQualityScore,
    SettingsConfig,
    StructuredSectionDraft,
)
from src.writing.abstract_utils import _abstract_body_word_count, _strip_abstract_citation_markup
from src.writing.citation_grounding import extract_and_strip_inline_citekeys, extract_used_citekeys
from src.writing.headings import (
    SECTION_REQUIRED_SUBHEADINGS,
    split_markdown_paragraphs,
    strip_terminal_citations,
)
from src.writing.renderers import collect_section_citations

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

import logging

logger = logging.getLogger(__name__)

_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b")
_EXCESSIVE_LIST_RE = re.compile(r"(?:,\s*[^,]{1,80}){20,}")
_TRAILING_FRAGMENT_RE = re.compile(r"\b(and|or|with|to|for|in|of|by|vs)\s*$", flags=re.IGNORECASE)
_INTERNAL_ID_RE = re.compile(r"\b(?:Paper_[A-Za-z0-9_-]+|p\d+|[a-f0-9]{8,}-[a-f0-9-]{3,})\b", flags=re.IGNORECASE)

_LOW_VOLUME_REVIEW_MAX_INCLUDED = 15
_SECTION_REQUIRED_SUBHEADINGS = SECTION_REQUIRED_SUBHEADINGS
_BEST_EFFORT_ISSUE_PREFIXES = (
    "insufficient_substantive_paragraphs",
    "missing_required_subheadings",
    "missing_subheading:",
    "empty_subsection_body:",
    "thin_subsection_body:",
    "trailing_fragment_word",
    "trailing_fragment_punctuation",
    "missing_required_citations:",
    "post_insufficient_substantive_paragraphs:",
    "post_missing_subheading:",
    "post_thin_subheading_body:",
    "post_trailing_fragment_word",
    "post_trailing_fragment_punctuation",
    "topic_anchor_terms_missing",
)

_OUTLINE_STOPWORDS = frozenset(
    {
        "about",
        "across",
        "after",
        "alongside",
        "analysis",
        "and",
        "from",
        "into",
        "must",
        "only",
        "section",
        "should",
        "that",
        "the",
        "their",
        "this",
        "using",
        "with",
    }
)

_strip_terminal_citations = strip_terminal_citations
_split_markdown_paragraphs = split_markdown_paragraphs


def _sanitize_ir_block_text(text: str) -> str:
    """Deterministically sanitize structured block prose before render."""
    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    if len(cleaned) > 900 and _EXCESSIVE_LIST_RE.search(cleaned):
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        lower_start_ratio = sum(1 for p in parts if p and p[0].islower()) / len(parts) if parts else 0.0
        punctuation_ratio = (
            sum(1 for p in parts if any(tok in p for tok in (".", ";", ":"))) / len(parts) if parts else 0.0
        )
        if len(parts) > 20 and lower_start_ratio > 0.55 and punctuation_ratio < 0.25:
            cleaned = ", ".join(parts[:12]) + ", and additional outcomes were reported."
    cleaned = _SNAKE_CASE_RE.sub(lambda m: m.group(0).replace("_", " "), cleaned)
    return cleaned


def _validate_structured_section_draft(
    section: str,
    draft: StructuredSectionDraft,
    valid_citekeys: set[str],
) -> tuple[StructuredSectionDraft, list[str]]:
    """Run IR-level checks before markdown rendering."""
    contract_issues: list[str] = []
    normalized_key = (draft.section_key or "").strip().lower()
    if normalized_key != section:
        draft.section_key = section

    required = _SECTION_REQUIRED_SUBHEADINGS.get(section, ())
    if required and not draft.required_subsections:
        draft.required_subsections = list(required)

    seen_subheadings: list[str] = []
    sanitized_blocks: list[SectionBlock] = []
    invalid_structured_keys: set[str] = set()
    invalid_inline_keys: set[str] = set()
    for block in draft.blocks:
        text = _sanitize_ir_block_text(block.text)
        text, inline_citekeys = extract_and_strip_inline_citekeys(text)
        if section == "abstract":
            text = _strip_abstract_citation_markup(text)
        block.text = text
        merged_citations: list[str] = []
        merged_seen: set[str] = set()
        for raw_key in [] if section == "abstract" else list(block.citations or []):
            key = str(raw_key or "").strip()
            if not key:
                continue
            if key not in valid_citekeys:
                invalid_structured_keys.add(key)
                continue
            if key in merged_seen:
                continue
            merged_seen.add(key)
            merged_citations.append(key)
        for raw_key in inline_citekeys:
            key = str(raw_key or "").strip()
            if not key:
                continue
            if section == "abstract":
                continue
            if key not in valid_citekeys:
                invalid_inline_keys.add(key)
                continue
            if key in merged_seen:
                continue
            merged_seen.add(key)
            merged_citations.append(key)
        block.citations = merged_citations
        if block.block_type == "subheading" and text:
            seen_subheadings.append(text.strip().lower())
        sanitized_blocks.append(block)
    draft.blocks = sanitized_blocks
    draft.cited_keys = collect_section_citations(draft)

    if invalid_structured_keys:
        contract_issues.append(f"invalid_structured_citations:{len(invalid_structured_keys)}")
        logger.warning(
            "Section '%s' emitted invalid structured citekeys: %s",
            section,
            sorted(invalid_structured_keys)[:10],
        )
    if invalid_inline_keys:
        contract_issues.append(f"invalid_inline_citations:{len(invalid_inline_keys)}")
        logger.warning(
            "Section '%s' emitted inline citekeys instead of structured citations: %s",
            section,
            sorted(invalid_inline_keys)[:10],
        )

    if not draft.blocks:
        draft.blocks = [SectionBlock(block_type="paragraph", text="No section content generated.")]
    return draft, contract_issues


def _is_low_volume_review(included_study_count: int) -> bool:
    return 0 < included_study_count <= _LOW_VOLUME_REVIEW_MAX_INCLUDED


def _is_best_effort_issue(issue: str) -> bool:
    return any(issue.startswith(prefix) for prefix in _BEST_EFFORT_ISSUE_PREFIXES)


def _rendered_citation_integrity_issues(content: str, valid_citekeys: set[str]) -> list[str]:
    invalid = sorted({key for key in extract_used_citekeys(content) if key not in valid_citekeys})
    if not invalid:
        return []
    return [f"invalid_rendered_citations:{len(invalid)}"]


def _extract_count(pattern: str, content: str) -> int | None:
    match = re.search(pattern, content, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _grounding_integrity_issues(
    section: str,
    content: str,
    grounding: WritingGroundingData | None,
) -> list[str]:
    if grounding is None:
        return []
    issues: list[str] = []
    if _INTERNAL_ID_RE.search(content):
        issues.append("internal_identifier_leakage")

    expected_screened = int(getattr(grounding, "total_screened", 0) or 0)
    expected_included = int(getattr(grounding, "total_included", 0) or 0)
    expected_assessed = int(getattr(grounding, "fulltext_assessed", 0) or 0)
    expected_not_retrieved = int(getattr(grounding, "fulltext_not_retrieved", 0) or 0)
    expected_retrieved = int(getattr(grounding, "fulltext_retrieved_count", 0) or 0)
    expected_fulltext_total = int(getattr(grounding, "fulltext_total_count", expected_included) or expected_included)

    observed_screened = _extract_count(r"\bscreened\s+(\d+)\s+records\b", content)
    if observed_screened is not None and observed_screened != expected_screened:
        issues.append("grounding_count_mismatch:screened")

    observed_included = _extract_count(r"\bincluded\s+(\d+)\s+stud(?:y|ies)\b", content)
    if observed_included is None:
        observed_included = _extract_count(r"\b(\d+)\s+stud(?:y|ies)\s+were included\b", content)
    if observed_included is not None and observed_included != expected_included:
        issues.append("grounding_count_mismatch:included")

    observed_assessed = _extract_count(r"\b(\d+)\s+reports\s+were assessed\b", content)
    if observed_assessed is not None and observed_assessed != expected_assessed:
        issues.append("grounding_count_mismatch:assessed")

    observed_not_retrieved = _extract_count(r"\b(\d+)\s+(?:full-text\s+)?reports\s+were not retrieved\b", content)
    if observed_not_retrieved is not None and observed_not_retrieved != expected_not_retrieved:
        issues.append("grounding_count_mismatch:not_retrieved")

    if section == "methods" and expected_fulltext_total > expected_retrieved:
        if re.search(
            r"\ball\s+\d+\s+included studies had (?:their )?full text retrieved\b", content, flags=re.IGNORECASE
        ):
            issues.append("grounding_fulltext_retrieval_contradiction")
    if section in {"results", "discussion"} and expected_fulltext_total > expected_retrieved:
        if re.search(
            r"\ball\s+\d+\s+included studies (?:had|with)\s+(?:their\s+)?full[- ]text\b",
            content,
            flags=re.IGNORECASE,
        ):
            issues.append("grounding_fulltext_retrieval_contradiction")
    expected_rob_gap = int(getattr(grounding, "included_studies_without_rob_mapping", 0) or 0)
    if section in {"methods", "results", "discussion"} and expected_rob_gap > 0:
        if re.search(
            r"\brisk[- ]of[- ]bias\b.{0,80}\b(?:assessed|completed)\b.{0,40}\ball\s+\d+\s+stud",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            issues.append("grounding_rob_coverage_contradiction")
    return sorted(set(issues))


def _is_substantive_paragraph(text: str, included_study_count: int = 0) -> bool:
    t = str(text or "").strip()
    if _is_low_volume_review(included_study_count):
        return len(t) >= 60 and len(t.split()) >= 10
    return len(t) >= 90 and len(t.split()) >= 14


def _is_minimally_substantive_paragraph(text: str) -> bool:
    t = str(text or "").strip()
    return len(t) >= 60 and len(t.split()) >= 10


def _section_completeness_issues(
    section: str,
    draft: StructuredSectionDraft,
    included_study_count: int = 0,
) -> list[str]:
    """Return deterministic completeness issues for one structured section."""
    issues: list[str] = []
    paragraph_count = sum(
        1
        for b in draft.blocks
        if b.block_type == "paragraph" and _is_substantive_paragraph(b.text, included_study_count)
    )
    min_required = 2 if section in {"results", "discussion"} and included_study_count > 1 else 1
    if paragraph_count < min_required:
        issues.append(f"insufficient_substantive_paragraphs:{paragraph_count}")

    headings = [b for b in draft.blocks if b.block_type == "subheading"]
    if section in _SECTION_REQUIRED_SUBHEADINGS:
        required_lower = {h.lower() for h in _SECTION_REQUIRED_SUBHEADINGS.get(section, ())}
        seen_lower = {h.text.strip().lower() for h in headings if h.text.strip()}
        missing_required = sorted(required_lower - seen_lower)
        if missing_required:
            issues.append("missing_required_subheadings")
            for miss in missing_required:
                issues.append(f"missing_subheading:{miss}")
    if section in _SECTION_REQUIRED_SUBHEADINGS and headings:
        for idx, block in enumerate(draft.blocks):
            if block.block_type != "subheading":
                continue
            j = idx + 1
            has_body = False
            has_substantive_body = False
            while j < len(draft.blocks):
                nxt = draft.blocks[j]
                if nxt.block_type == "subheading":
                    break
                if nxt.block_type == "paragraph" and nxt.text.strip():
                    has_body = True
                    if _is_minimally_substantive_paragraph(nxt.text):
                        has_substantive_body = True
                    break
                j += 1
            if not has_body:
                issues.append(f"empty_subsection_body:{block.text.strip().lower()}")
            elif section in {"results", "discussion"} and not has_substantive_body:
                issues.append(f"thin_subsection_body:{block.text.strip().lower()}")
    tail = ""
    for b in reversed(draft.blocks):
        if b.block_type == "paragraph" and b.text.strip():
            tail = b.text.strip()
            break
    if tail:
        tail = _strip_terminal_citations(tail)
        if _TRAILING_FRAGMENT_RE.search(tail):
            issues.append("trailing_fragment_word")
        elif section != "abstract" and tail and tail[-1] not in ".!?":
            issues.append("trailing_fragment_punctuation")
    return issues


def _post_render_completeness_issues(
    section: str,
    content: str,
    included_study_count: int = 0,
) -> list[str]:
    """Rendered-output sanity checks after canonical IR validation."""
    issues: list[str] = []
    lines = [ln.rstrip() for ln in str(content or "").splitlines()]
    paragraphs = _split_markdown_paragraphs(lines)

    substantive = [p for p in paragraphs if _is_substantive_paragraph(p, included_study_count)]
    min_required = 2 if section in {"results", "discussion"} and included_study_count > 1 else 1
    if len(substantive) < min_required:
        issues.append(f"post_insufficient_substantive_paragraphs:{len(substantive)}")

    tail = ""
    for p in reversed(paragraphs):
        if p:
            tail = p.strip()
            break
    if tail:
        tail = _strip_terminal_citations(tail)
        if _TRAILING_FRAGMENT_RE.search(tail):
            issues.append("post_trailing_fragment_word")
        elif tail and tail[-1] not in ".!?":
            issues.append("post_trailing_fragment_punctuation")
    return issues


def _topic_anchor_issues(
    section: str,
    content: str,
    grounding: WritingGroundingData | None,
) -> list[str]:
    """Return deterministic topic-consistency issues for grounded narrative sections."""
    if grounding is None or section not in {"results", "discussion", "conclusion"}:
        return []
    issues: list[str] = []
    topic_terms = [
        str(t).strip().lower() for t in (getattr(grounding, "topic_anchor_terms", []) or []) if str(t).strip()
    ]
    low = str(content or "").lower()
    if topic_terms:
        matched = [t for t in topic_terms[:6] if re.search(rf"\b{re.escape(t)}\b", low)]
        min_matches = 1 if section == "results" else 2
        if len(matched) < min_matches:
            issues.append("topic_anchor_terms_missing")
    research_scope = (
        str(getattr(grounding, "research_question", "") or getattr(grounding, "review_topic", "")).strip().lower()
    )
    bleed_phrase = "generative conversational ai tutoring"
    if bleed_phrase in low and bleed_phrase not in research_scope:
        issues.append("cross_run_topic_bleed_phrase")
    return issues


def _draft_word_count(draft: StructuredSectionDraft) -> int:
    return sum(len(str(block.text or "").split()) for block in draft.blocks)


def _draft_substantive_paragraph_count(draft: StructuredSectionDraft, included_study_count: int) -> int:
    return sum(
        1
        for block in draft.blocks
        if block.block_type == "paragraph" and _is_substantive_paragraph(block.text, included_study_count)
    )


def _best_effort_accept(
    section: str,
    generated: StructuredSectionDraft,
    fallback: StructuredSectionDraft,
    issues: list[str],
    included_study_count: int,
) -> bool:
    """Keep generated content when it is materially better than fallback text."""
    if not issues or any(not _is_best_effort_issue(issue) for issue in issues):
        return False
    generated_words = _draft_word_count(generated)
    fallback_words = max(_draft_word_count(fallback), 1)
    generated_substantive = _draft_substantive_paragraph_count(generated, included_study_count)
    fallback_substantive = _draft_substantive_paragraph_count(fallback, included_study_count)
    min_words = 80 if section in {"methods", "results", "discussion", "conclusion"} else 40
    return generated_words >= max(min_words, fallback_words * 2) and generated_substantive >= max(
        1, fallback_substantive
    )


def _outline_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) >= 4 and token not in _OUTLINE_STOPWORDS
    }


def _outline_coverage_issues(
    draft: StructuredSectionDraft,
    rendered: str,
    outline: SectionOutline | None,
) -> list[str]:
    if outline is None:
        return []
    heading_inventory = {
        re.sub(r"\s+", " ", str(block.text or "").strip().lower())
        for block in draft.blocks
        if block.block_type == "subheading" and str(block.text or "").strip()
    }
    rendered_text = str(rendered or "").lower()
    issues: list[str] = []
    for node in outline.nodes:
        normalized_heading = re.sub(r"\s+", " ", str(node.heading or "").strip().lower())
        if normalized_heading and normalized_heading in heading_inventory:
            continue
        keywords = _outline_terms(f"{node.heading} {node.intent}")
        if not keywords:
            continue
        matched = sum(1 for term in keywords if term in rendered_text)
        threshold = 1 if len(keywords) <= 2 else 2
        if matched < threshold:
            issues.append(f"outline_coverage:{node.node_id}")
        missing_citekeys = [
            citekey for citekey in node.required_citekeys if citekey and citekey not in set(draft.cited_keys or [])
        ]
        for citekey in missing_citekeys:
            issues.append(f"outline_citekey_missing:{node.node_id}:{citekey}")
    return issues


def format_quality_feedback(issues: list[str], score: SectionQualityScore) -> str:
    """Return a bounded feedback block for a ratchet rewrite."""
    if not issues:
        return ""
    lines = [
        "",
        "RATCHET FEEDBACK: Improve the next draft without introducing any new defects.",
        (
            "Current score counts -> "
            f"hard={score.hard_issue_count}, "
            f"completeness={score.completeness_issue_count}, "
            f"citation={score.citation_gap_count}, "
            f"outline={score.outline_coverage_gaps}, "
            f"abstract_floor_gap={score.abstract_floor_gap}, "
            f"soft={score.soft_issue_count}"
        ),
        "Resolve these issues first:",
    ]
    lines.extend(f"- {issue}" for issue in issues[:20])
    lines.append("Do not remove valid citations or grounded facts while fixing these issues.")
    return "\n".join(lines)


def compute_section_quality_score(
    *,
    section: str,
    draft: StructuredSectionDraft,
    rendered: str,
    outline: SectionOutline | None,
    grounding: WritingGroundingData | None,
    valid_citekeys: set[str],
    must_cite: set[str],
    settings: SettingsConfig,
    included_study_count: int,
) -> tuple[SectionQualityScore, list[str]]:
    """Compute the lexicographic ratchet score for one section draft."""
    from src.writing.citation_catalog import _citation_coverage_issues

    completeness_issues = _section_completeness_issues(section, draft, included_study_count)
    cite_issues, _missing_keys = _citation_coverage_issues(section, draft, must_cite)
    rendered_citation_issues = _rendered_citation_integrity_issues(rendered, valid_citekeys)
    grounding_issues = _grounding_integrity_issues(section, rendered, grounding)
    post_issues = _post_render_completeness_issues(section, rendered, included_study_count)
    outline_issues = _outline_coverage_issues(draft, rendered, outline)
    topic_issues = _topic_anchor_issues(section, rendered, grounding)
    abstract_floor_gap = 0
    if section == "abstract":
        minimum_words = int(getattr(getattr(settings, "writing", None), "abstract_trim_floor_words", 210))
        abstract_floor_gap = max(0, minimum_words - _abstract_body_word_count(rendered))
    score = SectionQualityScore(
        hard_issue_count=len(rendered_citation_issues) + len(grounding_issues),
        completeness_issue_count=len(completeness_issues) + len(post_issues),
        citation_gap_count=len(cite_issues),
        outline_coverage_gaps=len(outline_issues),
        abstract_floor_gap=abstract_floor_gap,
        soft_issue_count=len(topic_issues),
    )
    ordered_issues = [
        *rendered_citation_issues,
        *grounding_issues,
        *completeness_issues,
        *post_issues,
        *cite_issues,
        *outline_issues,
        *topic_issues,
    ]
    deduped_issues: list[str] = []
    seen: set[str] = set()
    for issue in ordered_issues:
        if issue in seen:
            continue
        seen.add(issue)
        deduped_issues.append(issue)
    return score, deduped_issues
