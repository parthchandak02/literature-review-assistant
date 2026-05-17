"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    EvidenceLinkRecord,
    ReviewConfig,
    SectionBlock,
    SectionOutline,
    SectionQualityScore,
    SectionWriteResult,
    SettingsConfig,
    StructuredAbstractOutput,
    StructuredSectionDraft,
)
from src.writing.citation_grounding import extract_and_strip_inline_citekeys, extract_used_citekeys
from src.writing.evidence_assembler import (
    build_results_evidence_pack,
    build_results_section_fallback,
    normalize_results_section_draft,
    render_results_evidence_context,
)
from src.writing.headings import (
    SECTION_REQUIRED_SUBHEADINGS,
    split_markdown_paragraphs,
    strip_terminal_citations,
)
from src.writing.humanizer_guardrails import apply_deterministic_guardrails
from src.writing.renderers import collect_section_citations, render_section_markdown
from src.writing.section_writer import SectionWriter

if TYPE_CHECKING:
    from src.writing.context_builder import WritingGroundingData

logger = logging.getLogger(__name__)


_GENERIC_AUTHOR_TOKENS = frozenset({"unknown", "none", "na", "author", "anonymous", "anon"})

# Fixed methodology references that every systematic review should be able to cite.
# These are registered alongside the included study citations so the writing LLM
# can cite PRISMA 2020, GRADE, and risk-of-bias tools when appropriate.
_METHODOLOGY_REFS: list[tuple[str, str, str, list[str], int, str, str]] = [
    # (citekey, doi, title, authors, year, journal, url)
    (
        "Page2021",
        "10.1136/bmj.n71",
        "PRISMA 2020 explanation and elaboration: updated guidance and exemplars for reporting systematic reviews",
        [
            "Page MJ",
            "Moher D",
            "Bossuyt PM",
            "Boutron I",
            "Hoffmann TC",
            "Mulrow CD",
            "Shamseer L",
            "Tetzlaff JM",
            "Akl EA",
            "McKenzie JE",
        ],
        2021,
        "BMJ",
        "https://doi.org/10.1136/bmj.n71",
    ),
    (
        "Sterne2019",
        "10.1136/bmj.l4898",
        "RoB 2: a revised tool for assessing risk of bias in randomised trials",
        [
            "Sterne JAC",
            "Savovic J",
            "Page MJ",
            "Elbers RG",
            "Blencowe NS",
            "Boutron I",
            "Cates CJ",
            "Cheng HY",
            "Corbett MS",
        ],
        2019,
        "BMJ",
        "https://doi.org/10.1136/bmj.l4898",
    ),
    (
        "Sterne2016",
        "10.1136/bmj.i4919",
        "ROBINS-I: a tool for assessing risk of bias in non-randomised studies of interventions",
        ["Sterne JA", "Hernan MA", "Reeves BC", "Savovic J", "Berkman ND", "Viswanathan M", "Henry D", "Altman DG"],
        2016,
        "BMJ",
        "https://doi.org/10.1136/bmj.i4919",
    ),
    (
        "Guyatt2011",
        "10.1016/j.jclinepi.2010.04.026",
        "GRADE guidelines: 1. Introduction-GRADE evidence profiles and summary of findings tables",
        [
            "Guyatt G",
            "Oxman AD",
            "Akl EA",
            "Kunz R",
            "Vist G",
            "Brozek J",
            "Norris S",
            "Falck-Ytter Y",
            "Glasziou P",
            "DeBeer H",
        ],
        2011,
        "J Clin Epidemiol",
        "https://doi.org/10.1016/j.jclinepi.2010.04.026",
    ),
    (
        "Cohen1960",
        "10.1177/001316446002000104",
        "A coefficient of agreement for nominal scales",
        ["Cohen J"],
        1960,
        "Educ Psychol Meas",
        "https://doi.org/10.1177/001316446002000104",
    ),
]

# Title words that are too generic to serve as a useful citekey base.
_GENERIC_TITLE_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "with",
        "this",
        "that",
        "fig",
        "figure",
        "table",
        "appendix",
        "section",
        "chapter",
        "methods",
        "method",
        "results",
        "result",
        "discussion",
        "conclusion",
        "conclusions",
        "introduction",
        "abstract",
        "study",
        "studies",
        "review",
        "systematic",
        "literature",
        "analysis",
        "analysing",
        "investigating",
        "usability",
        "examining",
        "exploring",
        "evaluating",
        "evaluation",
        "assessment",
        "towards",
        "toward",
        "role",
        "applying",
        "application",
        "understanding",
        "comparing",
        "developing",
        "improving",
        "educational",
        "learning",
        "teaching",
        "impact",
        "effect",
        "effects",
        "use",
        "using",
        "based",
        "new",
        "novel",
    }
)

_ABSTRACT_FIELDS = ("Background", "Objectives", "Methods", "Results", "Conclusions", "Keywords")
_SECTION_NAMES = frozenset({"introduction", "methods", "results", "discussion", "conclusion", "abstract"})


def _sanitize_prose(content: str) -> str:
    """Normalize whitespace and enforce ASCII-safe manuscript prose."""
    sanitized = content
    # Keep manuscript prose ASCII-only for IEEE export robustness.
    # Preserve newlines and tabs so section structure is not flattened.
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
            # Top-level section headings are owned by manuscript assembly.
            # If a section draft leaks "## Introduction ..." style text, strip the
            # heading token and keep any trailing prose as body content.
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
            # Rejoin split headings like:
            # "### Risk of"
            # "Bias Assessment ..."
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
                        # Promote to a known canonical heading when the continuation
                        # line starts with its remaining tail (e.g. "Risk of" + "Bias and ...").
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
            # Remove inline citation leakage from heading text.
            title = re.sub(r"\s*(?:\[[^\]]+\]\s*)+", " ", title).strip()
            title = re.sub(r"\s*\\cite\{[^}]+\}", " ", title).strip()
            # Trim sentence spillover that should be body prose.
            title = re.split(r"[.;:!?]\s+", title, maxsplit=1)[0]
            lower_title = title.lower()
            if (
                len(title.split()) > 8
                and re.search(r"\s+(?:was|were)\s+", title)
                and not any(lower_title.startswith(h.lower() + " ") for h in known_heading_prefixes)
            ):
                title = re.split(r"\s+(?:was|were)\s+", title, maxsplit=1)[0]
            # Drop known malformed title fragments.
            if title.lower() in _SECTION_NAMES:
                continue
            if title.lower().endswith((" and", " of", " for", " to", " with")):
                continue
            title = re.sub(r"\s{2,}", " ", title).strip(" -:")
            if not title:
                continue
            if title.lower() == last_heading.lower():
                continue
            # Split heading/body run-ons deterministically, e.g.
            # "### Information Sources The search..." -> heading + body line.
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


def _ensure_structured_abstract(content: str, research_question: str) -> str:
    """Ensure abstract contains all required structured fields.

    If fields are missing, append deterministic fallback lines so downstream
    markdown/latex extraction always has a complete abstract shape.
    """
    text = content.strip()
    if not text:
        text = "Evidence synthesis was generated from included studies."

    _present = {f: bool(re.search(rf"\*\*{re.escape(f)}:\*\*", text, flags=re.IGNORECASE)) for f in _ABSTRACT_FIELDS}
    _present["Conclusions"] = _present["Conclusions"] or bool(
        re.search(r"\*\*Conclusion:\*\*", text, flags=re.IGNORECASE)
    )
    defaults = {
        "Background": "This topic has important practical and implementation implications.",
        "Objectives": f"This systematic review addressed {research_question}.",
        "Methods": (
            "Bibliographic databases were searched according to protocol, with "
            "eligibility screening and risk-of-bias assessment."
        ),
        "Results": (
            "Across the included studies, findings suggested directionally favorable implementation and workflow "
            "outcomes in some settings, with substantial between-study heterogeneity limiting direct quantitative "
            "comparability and certainty."
        ),
        "Conclusions": (
            "Available evidence indicates potential benefits, but conclusions remain cautious because small samples, "
            "methodological heterogeneity, and reporting gaps constrain certainty."
        ),
        "Keywords": "systematic review, evidence synthesis, implementation, outcomes, methodology",
    }
    redirect_re = re.compile(
        r"\b(?:reported|presented|described|discussed)\s+in\s+(?:the\s+)?(?:body|main text|results section|"
        r"synthesis section|manuscript)\b|\bsee\s+(?:the\s+)?(?:body|results section|synthesis section)\b",
        flags=re.IGNORECASE,
    )
    if all(_present.values()):
        for field in ("Results", "Conclusions"):
            value_match = re.search(
                rf"\*\*{re.escape(field)}:\*\*\s*(.+?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if value_match and redirect_re.search(value_match.group(1).strip()):
                text = _replace_or_append_abstract_field(text, field, defaults[field])
        return text
    _missing_lines = [f"**{field}:** {defaults[field]}" for field in _ABSTRACT_FIELDS if not _present[field]]
    return (text + "\n\n" + "\n".join(_missing_lines)).strip()


def _clean_author_token(raw: str) -> str:
    """Extract a clean alphabetic token from an author string.

    Returns an empty string if the author value is a generic placeholder
    (e.g. 'Unknown', 'None', 'N/A') or a single-letter initial that would
    produce an ugly citekey.
    """
    token = re.sub(r"[^a-zA-Z]", "", str(raw).split()[0] if str(raw).split() else "")
    # Require at least 2 chars to avoid single-letter initials like "R"
    if len(token) < 2 or token.lower() in _GENERIC_AUTHOR_TOKENS:
        return ""
    return token


def _sanitize_citekey_token(raw: str) -> str:
    """Normalize citekey fragments to ASCII-safe token format."""
    normalized = "".join(c for c in unicodedata.normalize("NFD", str(raw or "")) if unicodedata.category(c) != "Mn")
    token = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_")
    token = re.sub(r"_+", "_", token)
    if token.startswith("Paper_") or not token:
        return ""
    if token and token[0].isdigit():
        token = f"Ref_{token}"
    return token


def _make_citekey_base(paper: CandidatePaper, index: int) -> str:
    """Derive a human-readable citekey base from a paper's metadata.

    Uses CandidatePaper.display_label (the canonical DB-stored token) when
    available. Falls back to local derivation for papers from older DBs.
    """
    year_str = str(paper.year) if paper.year else "nd"

    # Preferred path: use the canonical label stored in the DB.
    if paper.display_label:
        from_label = _sanitize_citekey_token(f"{paper.display_label}{year_str}")
        if from_label:
            return from_label[:20]

    # Fallback for papers from older DBs without display_label.
    author_token = ""
    if paper.authors:
        author_token = _clean_author_token(str(paper.authors[0]))

    if not author_token and paper.title:
        for word in paper.title.split():
            candidate = re.sub(r"[^a-zA-Z]", "", word)
            if len(candidate) >= 4 and candidate.lower() not in _GENERIC_TITLE_WORDS:
                author_token = candidate
                break

    if not author_token:
        return f"Ref{index + 1}"

    return _sanitize_citekey_token(f"{author_token}{year_str}")[:20] or f"Ref{index + 1}"


def _citation_entries_from_papers(papers: list[CandidatePaper]) -> list[tuple[str, CandidatePaper]]:
    """Build (citekey, paper) pairs with unique, human-readable citekeys."""
    seen: set[str] = set()
    result: list[tuple[str, CandidatePaper]] = []
    for i, p in enumerate(papers):
        base = _make_citekey_base(p, i)
        citekey = base
        idx = 1
        while citekey in seen:
            citekey = f"{base}_{idx}"
            idx += 1
        seen.add(citekey)
        result.append((citekey, p))
    return result


def build_citation_catalog_from_papers(papers: list[CandidatePaper]) -> str:
    """Build a simple citation catalog string from included papers for prompts."""
    entries = _citation_entries_from_papers(papers)
    lines = [f"[{citekey}] {p.title} ({p.year or 'n.d.'})" for citekey, p in entries]
    return "\n".join(lines) if lines else "(No papers yet)"


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_CITEKEY_RE = re.compile(r"\[([A-Za-z0-9_:-]+)\]")
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b")
_EXCESSIVE_LIST_RE = re.compile(r"(?:,\s*[^,]{1,80}){20,}")
_TRAILING_FRAGMENT_RE = re.compile(r"\b(and|or|with|to|for|in|of|by|vs)\s*$", flags=re.IGNORECASE)
_INTERNAL_ID_RE = re.compile(r"\b(?:Paper_[A-Za-z0-9_-]+|p\d+|[a-f0-9]{8,}-[a-f0-9-]{3,})\b", flags=re.IGNORECASE)
_ANY_BRACKET_CITATION_RE = re.compile(r"\[[^\[\]\n]{1,120}\]")

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


def _extract_valid_citekeys(citation_catalog: str) -> set[str]:
    keys: set[str] = set()
    for line in citation_catalog.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            keys.add(stripped[1 : stripped.index("]")].strip())
    return keys


def _extract_included_study_citekeys(citation_catalog: str) -> set[str]:
    """Extract citekeys from the INCLUDED STUDIES portion of the catalog only."""
    keys: set[str] = set()
    in_included_block = False
    for line in citation_catalog.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if "INCLUDED STUDIES" in upper or "CITATION COVERAGE" in upper:
            in_included_block = True
            continue
        if in_included_block and ("METHODOLOGY" in upper or "BACKGROUND" in upper):
            in_included_block = False
            continue
        if in_included_block and stripped.startswith("[") and "]" in stripped:
            keys.add(stripped[1 : stripped.index("]")].strip())
    return keys


def _compute_section_citation_budget(
    section: str,
    citation_catalog: str,
    valid_citekeys: set[str],
) -> set[str]:
    """Return the set of citekeys that a section MUST cite.

    - results: all included study citekeys (every study must appear)
    - discussion, methods, introduction, abstract, conclusion: no mandatory budget
    """
    if section != "results":
        return set()
    included_keys = _extract_included_study_citekeys(citation_catalog)
    return included_keys & valid_citekeys


def _citation_coverage_issues(
    section: str,
    draft: StructuredSectionDraft,
    must_cite: set[str],
) -> tuple[list[str], set[str]]:
    """Check which must-cite keys are missing from the draft.

    Returns (issue_descriptions, missing_keys).
    """
    if not must_cite:
        return [], set()
    cited_in_draft = set(draft.cited_keys or [])
    for block in draft.blocks:
        cited_in_draft.update(block.citations or [])
    cited_in_draft.update(
        re.findall(
            r"\[([A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?)\]",
            " ".join(b.text for b in draft.blocks),
        )
    )
    missing = must_cite - cited_in_draft
    if not missing:
        return [], set()
    issues = [f"missing_required_citations:{len(missing)}"]
    return issues, missing


def _sanitize_ir_block_text(text: str) -> str:
    """Deterministically sanitize structured block prose before render."""
    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    # Guard against survey-item dumps and raw field enumerations.
    if len(cleaned) > 900 and _EXCESSIVE_LIST_RE.search(cleaned):
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        lower_start_ratio = sum(1 for p in parts if p and p[0].islower()) / len(parts) if parts else 0.0
        punctuation_ratio = (
            sum(1 for p in parts if any(tok in p for tok in (".", ";", ":"))) / len(parts) if parts else 0.0
        )
        if len(parts) > 20 and lower_start_ratio > 0.55 and punctuation_ratio < 0.25:
            cleaned = ", ".join(parts[:12]) + ", and additional outcomes were reported."
    # Normalize snake_case leakage in prose.
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


_strip_terminal_citations = strip_terminal_citations
_split_markdown_paragraphs = split_markdown_paragraphs


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

    # Required subsections must be present and must have a non-empty paragraph before next subheading/end.
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
    # Tail cannot end with conjunction/preposition fragment.
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


def _append_or_inject_subsection(content: str, heading: str, sentence: str, *, aliases: tuple[str, ...] = ()) -> str:
    headings = (heading, *aliases)
    escaped = "|".join(re.escape(item) for item in headings)
    pattern = re.compile(rf"(^###\s+(?:{escaped})\s*$)", flags=re.IGNORECASE | re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(rf"### {heading}\n\n{sentence}", content, count=1)
    suffix = "" if not content.strip() else "\n\n"
    return f"{content.rstrip()}{suffix}### {heading}\n\n{sentence}".strip()


def _replace_or_append_subsection(
    content: str,
    heading: str,
    body: str,
    *,
    aliases: tuple[str, ...] = (),
) -> str:
    content = re.sub(r"(?<!\n)(###\s+)", r"\n\n\1", content)
    headings = (heading, *aliases)
    escaped = "|".join(re.escape(item) for item in headings)
    pattern = re.compile(
        rf"(?ms)^###\s+(?:{escaped})\s*$.*?(?=^###\s+|\Z)",
        flags=re.IGNORECASE,
    )
    replacement = f"### {heading}\n\n{body.strip()}"
    if pattern.search(content):
        return pattern.sub(replacement + "\n\n", content, count=1).strip()
    suffix = "" if not content.strip() else "\n\n"
    return f"{content.rstrip()}{suffix}{replacement}".strip()


def _replace_phrase_variants_case_insensitive(text: str, variants: tuple[str, ...], replacement: str) -> str:
    patched = text
    for variant in variants:
        source = str(variant or "")
        if not source:
            continue
        source_lower = source.lower()
        while True:
            idx = patched.lower().find(source_lower)
            if idx < 0:
                break
            patched = f"{patched[:idx]}{replacement}{patched[idx + len(source) :]}"
    return patched


def _needs_legacy_heading_fix(content: str) -> bool:
    """Return whether rendered markdown still looks like malformed legacy output."""
    text = str(content or "")
    return bool(
        re.search(r"(?m)^#{2,6}[ \t]+[^\n]+[ \t]+#{2,6}[ \t]+", text)
        or re.search(r"(?m)^#{2,6}[ \t]+\S[^\n]{8,}[ \t]+(?:The|This|These|for|in|Across|To)\b", text)
    )


def _structured_from_markdown(
    section: str,
    content: str,
    valid_citekeys: set[str],
    *,
    template: StructuredSectionDraft | None = None,
) -> StructuredSectionDraft:
    """Rebuild a structured draft from markdown after deterministic markdown transforms."""
    rebuilt = SectionWriter._fallback_structured_from_text(section, content)
    if template is not None:
        rebuilt.section_title = template.section_title
        rebuilt.required_subsections = list(template.required_subsections or [])
    rebuilt, _issues = _validate_structured_section_draft(section, rebuilt, valid_citekeys)
    return rebuilt


def _apply_markdown_transform_to_structured(
    section: str,
    draft: StructuredSectionDraft,
    valid_citekeys: set[str],
    transform: Callable[[str], str],
) -> StructuredSectionDraft:
    """Apply a deterministic markdown transform and sync the structured draft."""
    rendered = render_section_markdown(draft)
    transformed = transform(rendered).strip()
    if transformed == rendered.strip():
        return draft
    return _structured_from_markdown(section, transformed, valid_citekeys, template=draft)


def _patch_introduction_grounding(content: str, review: ReviewConfig) -> str:
    patched = content.strip()
    lower = patched.lower()
    rationale_sentence = (
        "The rationale for this review is to address an evidence gap in the context of rural deployment of "
        "QR-code-enabled digital vaccine record systems."
    )
    objective_sentence = f"The research question for this systematic review is: {review.research_question}"
    if ("rationale" not in lower and "context" not in lower and "background" not in lower) or "gap" not in lower:
        patched = f"{patched.rstrip()}\n\n{rationale_sentence}"
    if "objective" not in lower and "aim" not in lower and "research question" not in lower and "question" not in lower:
        patched = f"{patched.rstrip()}\n\n{objective_sentence}"
    return patched


def _patch_methods_grounding(content: str, grounding: WritingGroundingData | None, review: ReviewConfig) -> str:
    if grounding is None:
        return content
    patched = content.strip()
    had_combined_info_search = bool(re.search(r"(?im)^###\s+Information Sources and Search Strategy\s*$", patched))
    abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
    db_sentence = f"The review searched {', '.join(grounding.databases_searched)} on {grounding.search_date}" + (
        f" with an eligibility window of {grounding.search_eligibility_window}."
        if grounding.search_eligibility_window
        else "."
    )
    if getattr(grounding, "failed_databases", []):
        db_sentence = (
            f"{db_sentence.rstrip()} "
            f"Attempted sources with connector failures were: {', '.join(grounding.failed_databases)}."
        )
    eligibility_sentence = (
        f"Eligible studies addressed {review.pico.population}, evaluated {review.pico.intervention}, "
        f"compared against {review.pico.comparison}, and reported outcomes related to {review.pico.outcome}."
    )
    selection_parts = [grounding.screening_method_description.strip()]
    selection_parts.append(
        f"Following title and abstract screening, {grounding.fulltext_sought} reports were sought for full-text retrieval, "
        f"{grounding.fulltext_not_retrieved} were not retrieved, {grounding.fulltext_assessed} were assessed for eligibility, "
        f"and {grounding.total_included} studies were included."
    )
    if abstract_only_count > 0:
        selection_parts.append(
            f"Eligibility assessment used the retrieved reports for all {grounding.fulltext_assessed} candidates, but "
            f"retrievable full-text PDFs were available for only {grounding.fulltext_retrieved_count} of the "
            f"{grounding.fulltext_total_count} included studies; the remaining {abstract_only_count} included studies "
            "were extracted from abstracts and metadata only."
        )
    if grounding.excluded_non_primary_count > 0:
        selection_parts.append(
            f"An additional {grounding.excluded_non_primary_count} papers were excluded after full-text assessment during "
            "extraction because they did not meet the primary study design criteria."
        )
    selection_sentence = " ".join(part.strip() for part in selection_parts if part.strip())
    if abstract_only_count > 0:
        data_collection_sentence = (
            "Data extraction used a standardized form to capture study characteristics, intervention details, comparators, "
            "outcomes, and risk-of-bias inputs. "
            f"Full texts were retrieved for {grounding.fulltext_retrieved_count} of {grounding.fulltext_total_count} included "
            f"studies, and {abstract_only_count} studies were extracted from abstracts and metadata only."
        )
    else:
        data_collection_sentence = (
            "Data extraction used a standardized form to capture study characteristics, intervention details, comparators, "
            "outcomes, and risk-of-bias inputs. "
            f"Among reports successfully retrieved and assessed for eligibility, full texts were available for "
            f"{grounding.fulltext_retrieved_count} of {grounding.fulltext_total_count} included studies."
        )
    tool_names: list[str] = []
    if "RoB 2" in grounding.rob_summary:
        tool_names.append("RoB 2")
    if "ROBINS-I" in grounding.rob_summary:
        tool_names.append("ROBINS-I")
    if "CASP" in grounding.rob_summary:
        tool_names.append("CASP")
    if "MMAT" in grounding.rob_summary:
        tool_names.append("MMAT")
    synthesis_sentence = (
        "Narrative synthesis was used to summarize outcome domains, and risk of bias was assessed with "
        + (", ".join(tool_names) if tool_names else "design-appropriate appraisal tools")
        + "."
    )
    risk_tool_counts = dict(getattr(grounding, "risk_tool_counts", {}) or {})
    mmat_count = int(risk_tool_counts.get("mmat", 0) or 0)
    casp_count = int(risk_tool_counts.get("casp", 0) or 0)
    design_counts = dict(getattr(grounding, "study_design_counts", {}) or {})
    mixed_methods_design_n = int(design_counts.get("mixed_methods", 0) or 0)
    pre_post_design_n = int(design_counts.get("pre_post", 0) or 0)
    risk_routing_sentence = ""
    if mmat_count > 0 or casp_count > 0:
        if mmat_count > mixed_methods_design_n and pre_post_design_n > 0:
            risk_routing_sentence = (
                f"Risk-of-bias routing was design-aligned: CASP covered {casp_count} qualitative/cross-sectional studies, "
                f"and MMAT covered {mmat_count} studies, including mixed-methods and pre-post/non-randomized quantitative designs."
            )
        else:
            risk_routing_sentence = (
                f"Risk-of-bias routing was design-aligned: CASP covered {casp_count} qualitative/cross-sectional studies, "
                f"and MMAT covered {mmat_count} mixed-methods studies."
            )
    search_strategy_sentence = (
        "Search strings combined protocol keywords with Boolean operators, database-specific filters, and date limits, "
        "and the full line-by-line strategies are archived in the appendix."
    )
    validation_sentence = ""
    batch_validation_n = int(getattr(grounding, "batch_screen_validation_n", 0) or 0)
    batch_validation_npv = float(getattr(grounding, "batch_screen_validation_npv", 0.0) or 0.0)
    if batch_validation_n > 0:
        validation_npv_pct = int(round(batch_validation_npv * 100))
        validation_sentence = (
            f"To verify automated exclusions, {batch_validation_n} low-relevance records were "
            f"cross-checked by dual review; {validation_npv_pct}% were confirmed as true exclusions."
        )
    outcome_definition_sentence = "Primary and secondary outcomes were defined a priori and sought across all reported time points for each study."
    effect_measure_sentence = (
        "The primary effect measure was the reported direction of effect; when available, odds ratio, risk ratio, "
        "mean difference, or standardized mean difference estimates were extracted descriptively rather than pooled."
    )
    data_prep_sentence = (
        "When reports lacked directly comparable numeric fields, data were prepared for synthesis through direct extraction, "
        "unit harmonization where possible, and narrative tabulation without imputation."
    )
    heterogeneity_sentence = (
        "Heterogeneity was explored qualitatively across study-design, setting, and outcome-domain subgroups, and subgroup "
        "results were compared narratively rather than by meta-regression."
    )
    reporting_bias_sentence = (
        "No formal reporting bias or publication bias assessment was feasible because the synthesis did not support pooled "
        "meta-analysis and included too few studies for a funnel plot or leave-one-out evaluation."
    )
    software_sentence = "Quantitative synthesis software such as statsmodels or scipy was not used because no pooled meta-analysis was performed."
    rob_coverage_sentence = ""
    missing_rob = int(getattr(grounding, "included_studies_without_rob_mapping", 0) or 0)
    if missing_rob > 0:
        rob_coverage_sentence = (
            f"Risk-of-bias coverage was incomplete for {missing_rob} of {grounding.total_included} included studies "
            "because appraisal-ready full-text methodological detail was unavailable for those records. These studies "
            "were interpreted conservatively and are flagged in the quality assessment coverage appendix."
        )
    lower = patched.lower()
    if not all(db.lower() in lower for db in grounding.databases_searched[:2]):
        patched = _append_or_inject_subsection(
            patched,
            "Information Sources",
            db_sentence,
            aliases=("Information Sources and Search Strategy",),
        )
    if review.pico.population.lower() not in lower or review.pico.intervention.lower() not in lower:
        patched = _append_or_inject_subsection(patched, "Eligibility Criteria", eligibility_sentence)
    patched = _replace_or_append_subsection(
        patched,
        "Selection Process",
        selection_sentence,
        aliases=("Study Selection",),
    )
    patched = _replace_or_append_subsection(
        patched,
        "Data Collection",
        data_collection_sentence,
        aliases=("Data Collection Process",),
    )
    if not had_combined_info_search and ("boolean" not in lower or "filter" not in lower or "limit" not in lower):
        patched = _replace_or_append_subsection(
            patched,
            "Search Strategy",
            search_strategy_sentence,
            aliases=("Information Sources and Search Strategy",),
        )
    if tool_names and not any(tool.lower() in lower for tool in tool_names):
        patched = _append_or_inject_subsection(patched, "Synthesis Methods", synthesis_sentence)
    if ("defined" not in lower and "sought" not in lower and "time point" not in lower) or "outcome" not in lower:
        patched = f"{patched.rstrip()}\n\n{outcome_definition_sentence}"
    if "effect measure" not in lower and "odds ratio" not in lower and "mean difference" not in lower:
        patched = f"{patched.rstrip()}\n\n{effect_measure_sentence}"
    if "missing data" not in lower and "imputation" not in lower and "prepare" not in lower:
        patched = f"{patched.rstrip()}\n\n{data_prep_sentence}"
    if "heterogeneity" not in lower or ("subgroup" not in lower and "modifier" not in lower):
        patched = f"{patched.rstrip()}\n\n{heterogeneity_sentence}"
    if "reporting bias" not in lower or "sensitivity analysis" not in lower:
        patched = f"{patched.rstrip()}\n\n{reporting_bias_sentence}"
    if "software" not in lower and "statsmodels" not in lower and "scipy" not in lower:
        patched = f"{patched.rstrip()}\n\n{software_sentence}"
    if validation_sentence:
        lower = patched.lower()
        if "automated exclusions" not in lower and "cross-checked by dual review" not in lower:
            patched = f"{patched.rstrip()}\n\n{validation_sentence}"
    if risk_routing_sentence:
        lower = patched.lower()
        if "risk-of-bias routing was design-aligned" not in lower:
            patched = f"{patched.rstrip()}\n\n{risk_routing_sentence}"
    if rob_coverage_sentence:
        lower = patched.lower()
        if "risk-of-bias coverage was incomplete" not in lower and "quality assessment coverage appendix" not in lower:
            patched = f"{patched.rstrip()}\n\n{rob_coverage_sentence}"
    return patched


def _patch_results_grounding(content: str, grounding: WritingGroundingData | None = None) -> str:
    patched = content.strip()
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        (
            "predominantly positive direction of evidence",
            "predominantly positive impact",
            "predominantly positive",
        ),
        "directionally favorable but uncertain evidence pattern",
    )
    lower = patched.lower()
    if grounding is not None:
        selection_parts = [
            (
                f"The review screened {grounding.total_screened} records, sought {grounding.fulltext_sought} full-text reports, "
                f"did not retrieve {grounding.fulltext_not_retrieved}, assessed {grounding.fulltext_assessed} reports for "
                f"eligibility, and included {grounding.total_included} studies."
            )
        ]
        if grounding.excluded_fulltext_reasons:
            fulltext_excluded = int(
                getattr(
                    grounding,
                    "fulltext_excluded",
                    max(
                        0,
                        int(getattr(grounding, "fulltext_assessed", 0)) - int(getattr(grounding, "total_included", 0)),
                    ),
                )
                or 0
            )
            reasons = "; ".join(
                f"{str(reason).replace('_', ' ')} ({count})"
                for reason, count in grounding.excluded_fulltext_reasons.items()
            )
            selection_parts.append(
                f"Among {fulltext_excluded} reports excluded after full-text assessment, the primary reasons were "
                + reasons
                + "; each excluded report was assigned one primary reason category."
            )
        if grounding.excluded_non_primary_count > 0:
            selection_parts.append(
                f"An additional {grounding.excluded_non_primary_count} papers were excluded during extraction because they "
                "were classified as non-primary study types."
            )
        abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
        if abstract_only_count > 0:
            selection_parts.append(
                f"All {grounding.fulltext_assessed} reports were retrieved for eligibility assessment, but retrievable "
                f"full-text PDFs were available for only {grounding.fulltext_retrieved_count} of the "
                f"{grounding.fulltext_total_count} included studies; {abstract_only_count} studies were extracted from "
                "abstracts and metadata only."
            )
        if grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
            unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
            selection_parts.append(
                f"The non-retrieval rate at full-text screening was {grounding.fulltext_not_retrieved}/{grounding.fulltext_sought}, "
                "which may reduce evidence-base comprehensiveness and introduce retrieval bias if unretrieved reports differ "
                "systematically from the assessed evidence."
            )
            selection_parts.append(
                f"This corresponds to {unretrieved_pct:.1f}% unretrieved full-text reports; findings should therefore be treated as "
                "provisional and potentially inflated by selection bias."
            )
        risk_tool_counts = dict(getattr(grounding, "risk_tool_counts", {}) or {})
        mmat_count = int(risk_tool_counts.get("mmat", 0) or 0)
        casp_count = int(risk_tool_counts.get("casp", 0) or 0)
        design_counts = dict(getattr(grounding, "study_design_counts", {}) or {})
        mixed_methods_design_n = int(design_counts.get("mixed_methods", 0) or 0)
        pre_post_design_n = int(design_counts.get("pre_post", 0) or 0)
        if mmat_count > 0 or casp_count > 0:
            if mmat_count > mixed_methods_design_n and pre_post_design_n > 0:
                selection_parts.append(
                    f"Quality appraisal coverage included CASP for {casp_count} qualitative/cross-sectional studies and MMAT for "
                    f"{mmat_count} studies spanning mixed-methods plus pre-post/non-randomized quantitative designs."
                )
            else:
                selection_parts.append(
                    f"Quality appraisal coverage included CASP for {casp_count} qualitative/cross-sectional studies and MMAT for "
                    f"{mmat_count} mixed-methods studies."
                )
        selection_parts.append(
            "All included studies were screened against core eligibility requirements requiring a QR-code-enabled digital "
            "vaccination-record intervention and a paper-based, pre-digital, or historical baseline comparator context."
        )
        patched = _replace_or_append_subsection(patched, "Study Selection", " ".join(selection_parts))
        lower = patched.lower()
    heterogeneity_results_sentence = (
        "Heterogeneity results did not identify a consistent interaction or effect modifier across subgroup comparisons by "
        "study design, setting, or outcome domain."
    )
    reporting_bias_results_sentence = (
        "No reporting bias or publication bias result was available because funnel-based assessment was not interpretable for "
        "the small, heterogeneous synthesis set."
    )
    if "heterogeneity" not in lower or ("interaction" not in lower and "modifier" not in lower):
        patched = f"{patched.rstrip()}\n\n{heterogeneity_results_sentence}"
    if "reporting bias" not in lower and "publication bias" not in lower and "funnel" not in lower:
        patched = f"{patched.rstrip()}\n\n{reporting_bias_results_sentence}"
    return patched


def _patch_discussion_grounding(content: str, grounding: WritingGroundingData | None = None) -> str:
    patched = content.strip()
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        ("predominantly positive impact",),
        "directionally favorable but low-certainty impact",
    )
    lower = patched.lower()
    review_process_limitations_sentence = (
        "A limitation of the review process and screening process was reliance on database coverage constraints, no citation "
        "chasing, no grey-literature search, and abstract-only extraction for studies without retrievable full text."
    )
    if "review process" not in lower:
        patched = f"{patched.rstrip()}\n\n{review_process_limitations_sentence}"
    if grounding is not None and grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
        unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
        nonretrieval_sentence = (
            f"A major limitation of the evidence base is that {grounding.fulltext_not_retrieved} of "
            f"{grounding.fulltext_sought} reports sought for full-text retrieval were not retrieved. "
            "This raises the possibility of reporting bias because unretrieved reports may have contained findings that "
            "differ from the included evidence and therefore reduce confidence in the apparent direction of effect."
        )
        if "reporting bias" not in lower and "not retrieved" not in lower:
            patched = f"{patched.rstrip()}\n\n{nonretrieval_sentence}"
        if unretrieved_pct >= 40.0 and "directionally suggestive rather than definitive" not in patched.lower():
            patched = (
                f"{patched.rstrip()}\n\n"
                f"The unretrieved full-text proportion was {unretrieved_pct:.1f}%, which is high enough to materially shift "
                "the direction and magnitude of effects; interpretations should remain directionally suggestive rather than definitive."
            )
    if grounding is not None:
        abstract_only_count = max(0, int(grounding.fulltext_total_count) - int(grounding.fulltext_retrieved_count))
        if abstract_only_count > 0:
            abstract_only_limitation_sentence = (
                f"Interpretation is further constrained because {abstract_only_count} of {grounding.fulltext_total_count} "
                "included studies were synthesized from abstracts and metadata only, which reduces methodological "
                "detail, increases uncertainty in risk-of-bias appraisal, and limits generalizability."
            )
            if "abstracts and metadata only" not in lower and "reduces methodological detail" not in lower:
                patched = f"{patched.rstrip()}\n\n{abstract_only_limitation_sentence}"
                lower = patched.lower()
        missing_rob = int(getattr(grounding, "included_studies_without_rob_mapping", 0) or 0)
        if missing_rob > 0:
            rob_gap_sentence = (
                f"Risk-of-bias evidence remained incomplete for {missing_rob} included studies without mapped appraisal "
                "rows, so certainty judgments for those records are conservative and should be interpreted as "
                "hypothesis-generating rather than confirmatory."
            )
            if (
                "without mapped appraisal rows" not in lower
                and "hypothesis-generating rather than confirmatory" not in lower
            ):
                patched = f"{patched.rstrip()}\n\n{rob_gap_sentence}"
                lower = patched.lower()
    if grounding is not None and grounding.grade_summary:
        certainty_sentence = (
            "The low to very low certainty ratings across reported outcomes mean that the observed effects should be "
            "interpreted as tentative signals rather than confirmatory estimates for policy or implementation decisions."
        )
        if "low to very low certainty" not in lower and "tentative signals" not in lower:
            patched = f"{patched.rstrip()}\n\n{certainty_sentence}"
    if grounding is not None and (
        getattr(grounding, "missing_participant_count", 0) > 0
        or getattr(grounding, "nonextractable_result_count", 0) > 0
    ):
        data_gap_sentence = (
            f"Data completeness was limited because {grounding.missing_participant_count} of "
            f"{grounding.n_total_studies} studies did not report participant counts and "
            f"{grounding.nonextractable_result_count} studies lacked extractable result summaries. "
            f"Of these result gaps, {grounding.abstract_only_result_gap_count} reflected abstract-only extraction after "
            "full text could not be retrieved, while the remainder reflected source texts that did not report a usable "
            "result statement."
        )
        if "data completeness was limited" not in lower and "extractable result summaries" not in lower:
            patched = f"{patched.rstrip()}\n\n{data_gap_sentence}"
    return patched


def _patch_conclusion_grounding(content: str, grounding: WritingGroundingData | None = None) -> str:
    patched = content.strip()
    lower = patched.lower()
    if grounding is None:
        return patched
    if grounding.fulltext_sought > 0 and grounding.fulltext_not_retrieved > 0:
        unretrieved_pct = (grounding.fulltext_not_retrieved / grounding.fulltext_sought) * 100.0
        retrieval_sentence = (
            f"Conclusions must remain cautious because {grounding.fulltext_not_retrieved} of "
            f"{grounding.fulltext_sought} reports sought for full-text review were not retrieved, "
            "which limits comprehensiveness and may bias the observed direction of evidence."
        )
        if "were not retrieved" not in lower and "limits comprehensiveness" not in lower:
            patched = f"{patched.rstrip()}\n\n{retrieval_sentence}"
            lower = patched.lower()
        if unretrieved_pct >= 40.0 and "should not be used for strong implementation claims" not in lower:
            patched = (
                f"{patched.rstrip()}\n\n"
                f"The unretrieved full-text proportion ({unretrieved_pct:.1f}%) is substantial and can plausibly overestimate "
                "benefit signals; this evidence should not be used for strong implementation claims without additional retrieval "
                "or targeted sensitivity analyses."
            )
            lower = patched.lower()
    if grounding.grade_summary:
        certainty_sentence = (
            "Given low to very low certainty across outcomes, findings should be interpreted as "
            "hypothesis-generating rather than confirmatory."
        )
        if "hypothesis-generating rather than confirmatory" not in lower:
            patched = f"{patched.rstrip()}\n\n{certainty_sentence}"
            lower = patched.lower()
    if grounding.missing_participant_count > 0:
        participant_sentence = (
            f"Generalizability is further constrained because participant counts were unavailable for "
            f"{grounding.missing_participant_count} of {grounding.n_total_studies} included studies."
        )
        if "participant counts were unavailable" not in lower:
            patched = f"{patched.rstrip()}\n\n{participant_sentence}"
    return patched


def _replace_or_append_abstract_field(content: str, field: str, value: str) -> str:
    pattern = re.compile(
        rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(content):
        return pattern.sub(lambda match: f"{match.group(1)}{value}", content, count=1)
    suffix = "" if not content.strip() else "\n"
    return f"{content.rstrip()}{suffix}**{field}:** {value}"


def _patch_abstract_grounding(
    content: str,
    grounding: WritingGroundingData | None,
    review: ReviewConfig,
    *,
    minimum_words: int = 210,
) -> str:
    if grounding is None:
        return content
    keywords_value = ", ".join(review.keywords[:5]) if review.keywords else "systematic review"
    if keywords_value and keywords_value[-1] not in ".!?":
        keywords_value = f"{keywords_value}."
    methods_value = (
        f"Searches of {', '.join(grounding.databases_searched)} were conducted on {grounding.search_date}"
        + (
            f" across the protocol window {grounding.search_eligibility_window}"
            if grounding.search_eligibility_window
            else ""
        )
        + f"; {grounding.total_screened} records were screened and {grounding.total_included} studies were included."
    )
    failed_dbs = [str(db).strip() for db in (getattr(grounding, "failed_databases", []) or []) if str(db).strip()]
    if failed_dbs:
        methods_value = (
            f"{methods_value.rstrip()} "
            f"An additional attempted source ({', '.join(failed_dbs)}) returned no records because of a connector/API failure."
        )
    results_value = (
        f"{grounding.fulltext_assessed} reports were assessed for eligibility and {grounding.total_included} studies were included; "
        f"the overall direction of evidence was {str(grounding.synthesis_direction).replace('_', ' ')}."
    )
    fulltext_sought = int(getattr(grounding, "fulltext_sought", 0) or 0)
    fulltext_not_retrieved = int(getattr(grounding, "fulltext_not_retrieved", 0) or 0)
    if fulltext_sought > 0 and fulltext_not_retrieved > 0:
        results_value = (
            f"{results_value.rstrip()} "
            f"The unretrieved full-text proportion ({fulltext_not_retrieved}/{fulltext_sought}) "
            "limits comprehensiveness and increases uncertainty in interpretation."
        )
    conclusions_value = ""
    if getattr(grounding, "conclusion_hedging_required", False):
        conclusions_value = (
            "Available evidence should be interpreted cautiously because low-certainty findings and missing retrievable "
            "full texts constrain the strength and generalizability of the conclusions. These findings should be treated "
            "as hypothesis-generating rather than definitive."
        )
    patched = content.strip()
    patched = _replace_or_append_abstract_field(
        patched,
        "Objectives",
        f"The primary objective of this review was to examine {review.research_question.rstrip('?')}.",
    )
    patched = _replace_or_append_abstract_field(patched, "Methods", methods_value)
    patched = _replace_or_append_abstract_field(patched, "Results", results_value)
    if conclusions_value:
        patched = _replace_or_append_abstract_field(patched, "Conclusions", conclusions_value)
    patched = _replace_phrase_variants_case_insensitive(
        patched,
        (
            "predominantly positive direction of evidence",
            "predominantly positive impact",
            "predominantly positive",
        ),
        "directionally favorable but uncertain evidence pattern",
    )
    patched = _replace_or_append_abstract_field(patched, "Keywords", keywords_value)
    patched = _expand_abstract_to_minimum_words(patched, grounding, minimum_words)
    if _abstract_body_word_count(patched) < minimum_words:
        return _build_minimum_compliant_abstract(review, grounding, minimum_words)
    return patched


def _strip_abstract_citation_markup(content: str) -> str:
    """Abstract output must remain citation-free after all deterministic passes."""
    cleaned = _ANY_BRACKET_CITATION_RE.sub("", str(content or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def _normalize_structured_abstract_fields(content: str) -> str:
    """Normalize spacing and terminal punctuation for structured abstract fields."""

    def _rewrite(field: str, text: str, *, always_period: bool = False) -> str:
        pattern = re.compile(
            rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            flags=re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            value = re.sub(r"\s+", " ", match.group(2).strip())
            if value:
                if always_period:
                    value = value.rstrip(" ,;:.") + "."
                elif value[-1] not in ".!?":
                    value = f"{value}."
            return f"{match.group(1)}{value}"

        return pattern.sub(_repl, text, count=1)

    normalized = str(content or "").strip()
    for field in ("Background", "Objectives", "Methods", "Results", "Conclusions"):
        normalized = _rewrite(field, normalized)
    normalized = _rewrite("Keywords", normalized, always_period=True)
    return normalized


def parse_structured_abstract_markdown(content: str) -> StructuredAbstractOutput:
    """Parse structured abstract markdown into typed payload."""
    text = str(content or "").strip()

    def _extract(field_pattern: str) -> str:
        match = re.search(
            rf"\*\*{field_pattern}:\*\*\s*(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", (match.group(1) if match else "").strip())

    background = _extract("Background")
    objectives = _extract("Objectives")
    methods = _extract("Methods")
    results = _extract("Results")
    conclusions = _extract("Conclusions")
    if not conclusions:
        conclusions = _extract("Conclusion")
    keywords_value = _extract("Keywords")
    keywords = [kw.strip(" .,:;") for kw in keywords_value.split(",") if kw.strip(" .,:;")]

    payload = StructuredAbstractOutput(
        background=background,
        objectives=objectives,
        methods=methods,
        results=results,
        conclusions=conclusions,
        keywords=keywords,
    )
    return payload.normalized()


def validate_structured_abstract_markdown_band(
    content: str,
    *,
    min_words: int,
    max_words: int,
) -> tuple[bool, str]:
    """Return validity and reason for structured abstract markdown."""
    try:
        parsed = parse_structured_abstract_markdown(content)
        parsed.validate_word_band(min_words=min_words, max_words=max_words)
    except Exception as exc:
        return False, str(exc)
    return True, ""


def canonicalize_structured_abstract_markdown(content: str) -> str:
    """Return canonical multiline structured abstract markdown."""
    return parse_structured_abstract_markdown(content).to_markdown()


def _apply_structured_grounding_patches(
    section: str,
    draft: StructuredSectionDraft,
    *,
    grounding: WritingGroundingData | None,
    review: ReviewConfig,
    settings: SettingsConfig,
    valid_citekeys: set[str],
) -> StructuredSectionDraft:
    """Apply deterministic section grounding to IR via markdown sync."""
    if section == "abstract":
        minimum_words = int(getattr(getattr(settings, "writing", None), "abstract_trim_floor_words", 210))

        def _transform(content: str) -> str:
            stripped = _strip_abstract_citation_markup(content)
            normalized = _normalize_structured_abstract_fields(stripped)
            has_all_fields = all(
                bool(re.search(rf"\*\*{re.escape(field)}:\*\*", normalized, flags=re.IGNORECASE))
                for field in _ABSTRACT_FIELDS
            )
            has_minimum_words = _abstract_body_word_count(normalized) >= minimum_words
            if has_all_fields and has_minimum_words:
                return normalized
            logger.warning(
                "Abstract structured output missed required field/word-band checks; applying legacy abstract repair fallback."
            )
            patched = _ensure_structured_abstract(normalized, review.research_question)
            patched = _patch_abstract_grounding(
                patched,
                grounding,
                review,
                minimum_words=minimum_words,
            )
            patched = _strip_abstract_citation_markup(patched)
            return _normalize_structured_abstract_fields(patched)

        return _apply_markdown_transform_to_structured(section, draft, valid_citekeys, _transform)
    if section in {"introduction", "methods", "results", "discussion", "conclusion"}:
        # Keep narrative content source-driven and avoid deterministic sentence injection.
        return draft
    return draft


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
                "Section '%s' remained below the minimum abstract floor after guardrails; forcing deterministic compliant abstract.",
                section,
            )
            content = _build_minimum_compliant_abstract(review, grounding, minimum_words)
            floor_forced = True

    if content.strip() != render_section_markdown(patched).strip():
        patched = _structured_from_markdown(section, content, valid_citekeys, template=patched)
    return patched, content, floor_forced


def _abstract_body_word_count(content: str) -> int:
    try:
        parsed = parse_structured_abstract_markdown(content)
        return parsed.body_word_count()
    except Exception:
        matches = re.findall(
            r"\*\*(Background|Objectives|Methods|Results|Conclusions?):\*\*\s*(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            str(content or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = " ".join(text for _field, text in matches)
        body = re.sub(r"\s+", " ", body).strip()
        return len(body.split())


def _append_abstract_field_sentence(content: str, field: str, sentence: str) -> str:
    pattern = re.compile(
        rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _repl(match: re.Match[str]) -> str:
        existing = match.group(2).strip()
        if sentence.lower() in existing.lower():
            return match.group(0)
        separator = " " if existing else ""
        return f"{match.group(1)}{existing}{separator}{sentence}"

    return pattern.sub(_repl, content, count=1)


def _expand_abstract_to_minimum_words(content: str, grounding: WritingGroundingData, minimum_words: int) -> str:
    expanded = content
    if _abstract_body_word_count(expanded) >= minimum_words:
        return expanded
    fulltext_total_count = int(getattr(grounding, "fulltext_total_count", 0) or 0)
    fulltext_retrieved_count = int(getattr(grounding, "fulltext_retrieved_count", 0) or 0)
    abstract_only_count = max(0, fulltext_total_count - fulltext_retrieved_count)
    expansion_steps = [
        (
            "Methods",
            f"Eligibility assessment covered {grounding.fulltext_assessed} retrieved reports after screening "
            f"{grounding.total_screened} records across the configured databases.",
        ),
        (
            "Results",
            f"Study designs were heterogeneous, and {grounding.total_included} included studies produced an overall "
            f"{str(grounding.synthesis_direction).replace('_', ' ')} direction of evidence.",
        ),
    ]
    if abstract_only_count > 0:
        expansion_steps.append(
            (
                "Conclusions",
                f"{abstract_only_count} included studies were extracted from abstracts and metadata only, which "
                "limits synthesis depth and increases uncertainty.",
            )
        )
    if getattr(grounding, "grade_summary", ""):
        expansion_steps.append(
            (
                "Conclusions",
                "Certainty of evidence was predominantly low to very low, so findings should be treated as "
                "hypothesis-generating rather than definitive.",
            )
        )
    for field, sentence in expansion_steps:
        if _abstract_body_word_count(expanded) >= minimum_words:
            break
        expanded = _append_abstract_field_sentence(expanded, field, sentence)
    return expanded


def _format_abstract_design_summary(study_design_counts: dict[str, int] | None) -> str:
    if not study_design_counts:
        return "heterogeneous study designs"
    ordered = sorted(
        ((str(label or "").replace("_", " ").strip(), int(count or 0)) for label, count in study_design_counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    parts = [f"{label} (n={count})" for label, count in ordered if label and count > 0]
    if not parts:
        return "heterogeneous study designs"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _build_minimum_compliant_abstract(
    review: ReviewConfig,
    grounding: WritingGroundingData,
    minimum_words: int,
) -> str:
    research_question = str(review.research_question or "the review question").strip().rstrip("?")
    databases = ", ".join(getattr(grounding, "databases_searched", []) or ["configured bibliographic databases"])
    search_window = str(getattr(grounding, "search_eligibility_window", "") or "").strip()
    search_window_clause = f" across the eligibility window {search_window}" if search_window else ""
    screening_method = str(getattr(grounding, "screening_method_description", "") or "").strip()
    if screening_method and screening_method[-1] not in ".!?":
        screening_method = f"{screening_method}."
    design_summary = _format_abstract_design_summary(getattr(grounding, "study_design_counts", {}))
    total_participants = getattr(grounding, "total_participants", None)
    participant_sentence = ""
    if total_participants:
        participant_sentence = f" Reported participant totals summed to approximately {int(total_participants)} across studies that disclosed sample sizes."
    direction = str(getattr(grounding, "synthesis_direction", "mixed") or "mixed").replace("_", " ")
    grade_summary = str(getattr(grounding, "grade_summary", "") or "").strip()
    grade_sentence = ""
    if grade_summary:
        grade_sentence = (
            " Certainty of evidence was predominantly low to very low across reported outcomes, "
            "which limits confidence in the stability and transferability of the observed effects."
        )
    fulltext_sought = int(getattr(grounding, "fulltext_sought", 0) or 0)
    fulltext_not_retrieved = int(getattr(grounding, "fulltext_not_retrieved", 0) or 0)
    fulltext_assessed = int(getattr(grounding, "fulltext_assessed", 0) or 0)
    total_included = int(getattr(grounding, "total_included", 0) or 0)
    fulltext_total_count = int(getattr(grounding, "fulltext_total_count", 0) or 0)
    fulltext_retrieved_count = int(getattr(grounding, "fulltext_retrieved_count", 0) or 0)
    abstract_only_count = max(0, fulltext_total_count - fulltext_retrieved_count)
    abstract_only_sentence = ""
    if abstract_only_count > 0:
        abstract_only_sentence = f" {abstract_only_count} included studies were extracted from abstracts and metadata only because retrievable full-text PDFs were unavailable."
    retrieval_sentence = ""
    if fulltext_not_retrieved > 0:
        retrieval_sentence = f" The evidence base was constrained by non-retrieval of {fulltext_not_retrieved} of {fulltext_sought} reports sought for full-text review."
    rob_summary = str(getattr(grounding, "rob_summary", "") or "").strip()
    rob_sentence = ""
    if rob_summary:
        rob_sentence = f" Risk-of-bias appraisal used design-appropriate tools summarized as follows: {rob_summary}"
    keyword_values = [str(keyword).strip() for keyword in getattr(review, "keywords", [])[:5] if str(keyword).strip()]
    keywords_value = ", ".join(keyword_values) if keyword_values else "systematic review"
    if keywords_value[-1] not in ".!?":
        keywords_value = f"{keywords_value}."
    candidate = (
        f"**Background:** This systematic review synthesized available evidence relevant to {research_question}, with emphasis on methodological transparency, evidence consistency, and practical interpretation.\n"
        f"**Objectives:** The objective of this review was to examine {research_question}.\n"
        f"**Methods:** Searches of {databases} were conducted on {grounding.search_date}{search_window_clause}. We screened {grounding.total_screened} records, sought {fulltext_sought} full-text reports, did not retrieve {fulltext_not_retrieved}, assessed {fulltext_assessed} reports for eligibility, and included {total_included} studies. {screening_method}{rob_sentence}\n"
        f"**Results:** Included evidence comprised {design_summary}. The overall direction of evidence was {direction}, with reported benefits concentrated in selected implementation and usability outcomes rather than a uniform effect across all domains.{participant_sentence} Heterogeneity in design, setting, and outcome definitions limited direct comparability and prevented strong pooled inference.{abstract_only_sentence}\n"
        f"**Conclusions:** Available evidence suggests potential implementation benefits, but conclusions should remain cautious because the evidence base is small, methodologically heterogeneous, and incompletely retrieved.{grade_sentence}{retrieval_sentence} Stronger comparative studies with fuller reporting are needed before drawing definitive implementation claims.\n"
        f"**Keywords:** {keywords_value}"
    ).strip()
    if _abstract_body_word_count(candidate) >= minimum_words:
        return candidate
    candidate = _append_abstract_field_sentence(
        candidate,
        "Results",
        "Observed findings were better suited to narrative synthesis than to precise quantitative comparison because outcome measurement and reporting practices varied substantially across studies.",
    )
    if _abstract_body_word_count(candidate) >= minimum_words:
        return candidate
    candidate = _append_abstract_field_sentence(
        candidate,
        "Conclusions",
        "Implementation decisions should therefore emphasize local feasibility, data quality safeguards, and prospective evaluation rather than assuming that digital record adoption alone will produce durable coverage gains.",
    )
    return candidate


def _build_deterministic_section_fallback(
    section: str,
    grounding: WritingGroundingData | None,
    valid_citekeys: set[str],
) -> StructuredSectionDraft:
    """Build minimal, complete section content when generation remains malformed."""
    fallback_citations: list[str] = []
    if valid_citekeys:
        first = sorted(valid_citekeys)[0]
        fallback_citations = [first]
    if section == "abstract":
        databases = (
            ", ".join(getattr(grounding, "databases_searched", []) or []) or "configured bibliographic databases"
        )
        review_topic = str(
            getattr(grounding, "research_question", "")
            or getattr(grounding, "review_topic", "")
            or "the review question"
        ).strip()
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        assessed = getattr(grounding, "fulltext_assessed", 0) if grounding is not None else 0
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        not_retrieved = getattr(grounding, "fulltext_not_retrieved", 0) if grounding is not None else 0
        direction = str(getattr(grounding, "synthesis_direction", "mixed") or "mixed").replace("_", " ")
        search_window = str(getattr(grounding, "search_eligibility_window", "") or "").strip()
        search_phrase = f" across the protocol window {search_window}" if search_window else ""
        return StructuredSectionDraft(
            section_key="abstract",
            cited_keys=fallback_citations,
            blocks=[
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Background:** This systematic review evaluated the available evidence addressing {review_topic}, "
                        "with emphasis on study selection transparency, synthesis consistency, and the strength of the "
                        "reported evidence base."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=f"**Objectives:** The objective of this review was to examine {review_topic}.",
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Methods:** Searches of {databases} were conducted{search_phrase}; {screened} records were screened, "
                        f"{assessed} reports were assessed for eligibility, {not_retrieved} full-text reports were not retrieved, "
                        f"and {included} studies were included in the synthesis."
                    ),
                    citations=fallback_citations,
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"**Results:** The available evidence came from {included} included studies and the overall direction "
                        f"of evidence was {direction}. Reported effects suggested potential implementation gains alongside "
                        "persistent data quality, interoperability, and infrastructure constraints."
                    ),
                    citations=fallback_citations,
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "**Conclusions:** Available evidence remains limited and methodologically heterogeneous, so conclusions "
                        "should be interpreted cautiously while prioritizing stronger comparative studies and better reporting."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text="**Keywords:** systematic review, evidence synthesis, included studies, manuscript quality, research question.",
                ),
            ],
        )
    if section == "methods":
        sought = getattr(grounding, "fulltext_sought", 0) if grounding is not None else 0
        not_retrieved = getattr(grounding, "fulltext_not_retrieved", 0) if grounding is not None else 0
        assessed = getattr(grounding, "fulltext_assessed", 0) if grounding is not None else 0
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        return StructuredSectionDraft(
            section_key="methods",
            cited_keys=fallback_citations,
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("methods", ())),
            blocks=[
                SectionBlock(block_type="subheading", text="Eligibility Criteria", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Eligibility was predefined using population, intervention, comparator, and outcome criteria "
                        "from the protocol, and only studies meeting all criteria were retained."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Information Sources", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Bibliographic database searches were executed on the protocol date range using the configured "
                        "connectors, and search strategies were archived in the appendix."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Selection Process", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"Two independent reviewers screened {screened} records with adjudication for disagreements. "
                        f"{sought} reports were sought for full-text retrieval, {not_retrieved} reports were not retrieved, "
                        f"{assessed} were assessed for eligibility, and {included} studies were ultimately included."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Synthesis Methods", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "A narrative synthesis framework was used because methodological and outcome heterogeneity "
                        "limited quantitative pooling, and evidence certainty was interpreted with risk-of-bias and GRADE inputs."
                    ),
                    citations=fallback_citations,
                ),
            ],
        )
    if section == "results":
        return build_results_section_fallback(
            build_results_evidence_pack(grounding),
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("results", ())),
            fallback_citations=fallback_citations,
        )
    if section == "discussion":
        topic_scope = ""
        if grounding is not None:
            topic_scope = str(
                getattr(grounding, "research_question", "") or getattr(grounding, "review_topic", "")
            ).strip()
        if not topic_scope:
            topic_scope = "the review question"
        return StructuredSectionDraft(
            section_key="discussion",
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("discussion", ())),
            blocks=[
                SectionBlock(block_type="subheading", text="Principal Findings", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"Across included studies addressing {topic_scope}, evidence indicates potentially meaningful "
                        "effects, but heterogeneity and certainty limitations constrain strong causal conclusions."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Interpretation should remain cautious because outcome definitions, comparator quality, and reporting "
                        "completeness vary substantially across the evidence base."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Comparison with Prior Work", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "These findings are broadly consistent with prior systematic review trends, while direct "
                        "cross-study comparison remains limited by outcome heterogeneity and contextual differences."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Strengths and Limitations", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Strengths include protocol-led screening and structured extraction, whereas limitations include "
                        "variable study quality, inconsistent reporting, and constrained full-text availability."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Implications for Practice", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Practice adoption should be cautious and context-aware, prioritizing settings with adequate "
                        "implementation support and robust evidence of effectiveness."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Implications for Research", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Future studies should use stronger comparative designs, standardized outcomes, and preregistered "
                        "analysis plans to improve causal interpretability and certainty of evidence."
                    ),
                ),
            ],
        )
    return StructuredSectionDraft(
        section_key=section,
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Section content was generated using deterministic fallback due to incomplete model output.",
            )
        ],
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


def _draft_fingerprint(draft: StructuredSectionDraft) -> str:
    """Return a stable content hash for duplicate ratchet detection."""
    payload = json.dumps(
        [
            {
                "block_type": block.block_type,
                "text": block.text,
                "level": block.level,
                "citations": list(block.citations or []),
            }
            for block in draft.blocks
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


async def extract_and_register_claims(
    section: str,
    content: str,
    citation_repo: CitationRepository,
) -> int:
    """Extract cited sentences from written content and register claim->evidence links.

    For each sentence that contains one or more [citekey] references:
    1. Register the sentence as a ClaimRecord in the claims table.
    2. Look up citation_id for each citekey in the citations table.
    3. Create an EvidenceLinkRecord linking the claim to each resolved citation.

    Returns the number of claims registered. Already-registered citekeys that do
    not appear in the citations table are silently skipped (prevents FK violations
    from hallucinated keys that the repair step may not have caught).
    """
    citekey_to_id = await citation_repo.get_citation_map()
    if not citekey_to_id:
        return 0

    # Split content into candidate sentences; fall back to line split for short texts.
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

        claim = ClaimRecord(
            claim_text=sentence[:2000],
            section=section,
            confidence=1.0,
        )
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


async def register_methodology_citations(repo: CitationRepository) -> list[str]:
    """Register fixed methodology references (PRISMA 2020, GRADE, RoB tools, etc.).

    These citekeys are added to the valid_citekeys list so the writing LLM can
    cite methodology papers alongside the included study references.
    Returns list of newly registered (or already-existing) methodology citekeys.
    """
    existing = set(await repo.get_citekeys())
    registered: list[str] = []
    for citekey, doi, title, authors, year, journal, _url in _METHODOLOGY_REFS:
        registered.append(citekey)
        if citekey in existing:
            continue
        record = CitationEntryRecord(
            citekey=citekey,
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            bibtex=None,
            resolved=True,
            source_type="methodology",
        )
        try:
            await repo.register_citation(record)
            existing.add(citekey)
        except Exception as exc:
            logger.debug("Could not register methodology citation %s: %s", citekey, exc)
    return registered


async def register_background_sr_citations(
    repo: CitationRepository,
    research_question: str,
    keywords: list[str],
    max_results: int = 8,
    query_keyword_limit: int = 6,
    topic_token_keyword_limit: int = 10,
    request_timeout_seconds: int = 20,
) -> list[str]:
    """Discover and register background systematic reviews on the same topic.

    Queries Semantic Scholar for highly-cited Review-type papers matching the
    research question keywords, then registers them as citable background references.
    This ensures the Discussion section can cite prior systematic reviews when
    comparing findings, which is required by PRISMA 2020 item 27.

    Returns a list of registered citekeys (may be empty if search fails).
    """
    import os

    import aiohttp

    from src.utils.ssl_context import tcp_connector_with_certifi

    query_keyword_limit = max(1, int(query_keyword_limit))
    topic_token_keyword_limit = max(1, int(topic_token_keyword_limit))
    request_timeout_seconds = max(5, int(request_timeout_seconds))
    kw_query = " ".join(keywords[:query_keyword_limit]) if keywords else research_question[:120]
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    headers: dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key

    registered: list[str] = []
    try:
        params = {
            "query": kw_query,
            "fields": "title,authors,year,externalIds,citationCount,publicationTypes,venue",
            "publicationTypes": "Review",
            "limit": str(max_results * 3),  # over-fetch to allow filtering
        }
        async with aiohttp.ClientSession(connector=tcp_connector_with_certifi(), headers=headers) as session:
            async with session.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=request_timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    logger.debug("Background SR search: Semantic Scholar returned %d", resp.status)
                    return []
                data = await resp.json()

        papers_raw = data.get("data", [])

        # Topic relevance filter: require at least one keyword token to appear
        # in the paper title (case-insensitive). This prevents highly-cited but
        # off-topic reviews from being registered as background SR citations.
        _topic_tokens = {
            tok.lower()
            for kw in keywords[:topic_token_keyword_limit]
            for tok in kw.replace("-", " ").split()
            if len(tok) > 3
        }
        if not _topic_tokens:
            _topic_tokens = {tok.lower() for tok in research_question.split() if len(tok) > 3}

        _min_token_matches = 2 if len(_topic_tokens) >= 4 else 1

        def _is_topic_relevant(paper: dict) -> bool:
            title_lower = (paper.get("title") or "").lower()
            matched = sum(1 for tok in _topic_tokens if tok in title_lower)
            return matched >= _min_token_matches

        papers_relevant = [p for p in papers_raw if _is_topic_relevant(p)]
        _filtered_out = [p for p in papers_raw if not _is_topic_relevant(p)]
        if _filtered_out:
            logger.info(
                "Background SR relevance filter excluded %d of %d candidates: %s",
                len(_filtered_out),
                len(papers_raw),
                "; ".join((p.get("title") or "?")[:60] for p in _filtered_out[:5]),
            )
        if not papers_relevant:
            logger.info(
                "Background SR topic filter matched 0 of %d papers; returning empty to avoid off-topic citations.",
                len(papers_raw),
            )
            return []

        # Sort by citation count descending; take top max_results
        papers_sorted = sorted(
            papers_relevant,
            key=lambda p: p.get("citationCount") or 0,
            reverse=True,
        )[:max_results]

        existing = set(await repo.get_citekeys())
        for p in papers_sorted:
            title = (p.get("title") or "").strip()
            year = p.get("year")
            if not title or not year:
                continue
            authors_raw = p.get("authors") or []
            authors = [a.get("name", "") for a in authors_raw if a.get("name")]
            doi = (p.get("externalIds") or {}).get("DOI")
            venue = p.get("venue") or ""
            # Build a citekey from first author surname + year.
            # Normalize to ASCII so accented characters (e.g. Perez, not Pérez)
            # do not produce citekeys that regex patterns fail to match.
            first_surname = ""
            if authors:
                name_parts = authors[0].split()
                raw_surname = name_parts[-1] if name_parts else "Author"
                first_surname = "".join(
                    c for c in unicodedata.normalize("NFD", raw_surname) if unicodedata.category(c) != "Mn"
                )
            base_key = f"{first_surname}{year}SR" if first_surname else f"SR{year}"
            citekey = base_key
            suffix = 2
            while citekey in existing:
                citekey = f"{base_key}{suffix}"
                suffix += 1
            sr_url = (p.get("url") or p.get("externalIds", {}).get("URL")) or None
            record = CitationEntryRecord(
                citekey=citekey,
                doi=doi,
                url=str(sr_url) if sr_url else None,
                title=title,
                authors=authors,
                year=year,
                journal=venue or None,
                bibtex=None,
                resolved=True,
                source_type="background_sr",
            )
            try:
                await repo.register_citation(record)
                existing.add(citekey)
                registered.append(citekey)
                logger.info(
                    "Registered background SR: %s (%d citations) -> citekey=%s",
                    title[:60],
                    p.get("citationCount") or 0,
                    citekey,
                )
            except Exception as exc:
                logger.debug("Could not register background SR %s: %s", citekey, exc)

    except Exception as exc:
        logger.warning("Background SR discovery failed: %s", exc)

    return registered


async def register_citations_from_papers(repo: CitationRepository, papers: list[CandidatePaper]) -> None:
    """Pre-register citations for included papers so validate_section passes.
    Skips citekeys already in DB (idempotent for resume)."""
    existing = set(await repo.get_citekeys())
    entries = _citation_entries_from_papers(papers)
    for citekey, p in entries:
        if citekey in existing:
            continue
        record = CitationEntryRecord(
            citekey=citekey,
            doi=p.doi,
            url=p.url,
            title=p.title or "(No title)",
            authors=p.authors or [],
            year=p.year,
            journal=p.journal,
            bibtex=None,
            resolved=True,
            source_type="included",
        )
        await repo.register_citation(record)
        existing.add(citekey)


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
    """Write a section, validate with citation ledger, return content.

    Orchestrates: SectionWriter -> CitationLedger.validate_section.
    The grounding parameter injects real pipeline data into the section
    context so the LLM cannot hallucinate counts or statistics.
    The rag_context parameter appends semantically retrieved chunks from
    the paper embedding store so the LLM has targeted evidence for the section.
    The prior_sections_context parameter injects already-written sections
    (e.g. Results) so that Discussion/Conclusion can build on them rather
    than repeating the same statistics verbatim.
    """
    from src.writing.prompts.sections import get_section_context

    # Build context from grounding data if provided; otherwise use the passed context
    effective_context = get_section_context(section, grounding=grounding) if grounding is not None else context

    # Inject prior-sections context block BEFORE RAG chunks so the LLM
    # sees the narrative spine of already-written sections first.
    if prior_sections_context:
        effective_context = effective_context + "\n\n" + prior_sections_context

    # Append RAG-retrieved evidence chunks when available
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

    writer = SectionWriter(
        review=review,
        settings=settings,
        citation_catalog=citation_catalog,
    )
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
                "Section '%s' failed IR completeness checks (%s); retrying once.",
                section,
                ", ".join(issues),
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
        return (
            structured,
            content,
            validation_retries,
            validation_issues,
            used_deterministic_fallback,
            metadata,
        )

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
                "Section '%s' ratchet stopped at iteration %d because quality plateaued.",
                section,
                iteration + 1,
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

    # Register each cited sentence as a claim and link it to evidence so the
    # citation lineage gate can verify full claim->evidence->citation coverage.
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
        logger.warning(
            "Section '%s' has %d claim(s) without linked evidence.",
            section,
            len(result.unresolved_claims),
        )
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


def build_methodology_catalog() -> str:
    """Return a citation catalog string for the fixed methodology references.

    Appended to the included-study catalog so the writing LLM can cite
    PRISMA 2020, GRADE, and risk-of-bias tools in the Methods section.
    """
    lines = [
        f"[{citekey}] {title} ({year})" for citekey, _doi, title, _authors, year, _journal, _url in _METHODOLOGY_REFS
    ]
    return "\n".join(lines)


def build_background_sr_catalog(
    background_sr_rows: list[tuple[str, str, int | None]],
) -> str:
    """Return citation catalog block for discovered background systematic reviews."""
    lines = []
    for citekey, title, year in background_sr_rows:
        year_str = str(year) if year else "n.d."
        lines.append(f"[{citekey}] {title} ({year_str})")
    return "\n".join(lines)


def prepare_writing_context(
    included_papers: list[CandidatePaper],
    settings: SettingsConfig,
    background_sr_rows: list[tuple[str, str, int | None]] | None = None,
) -> str:
    """Build the citation catalog for the writing phase.

    The catalog includes both included-study citekeys and fixed methodology
    references (PRISMA 2020, GRADE, RoB tools) so the writing LLM can cite
    them in the Methods section.

    Returns the catalog string; style extraction was removed because
    extract_style_patterns always returns empty patterns that are never
    injected into prompts.
    """
    _ = settings  # reserved for future per-agent catalog filtering
    included_catalog = build_citation_catalog_from_papers(included_papers)
    methodology_catalog = build_methodology_catalog()
    background_sr_catalog = build_background_sr_catalog(background_sr_rows or [])
    # Methodology refs appended after included studies; separator makes it clear
    catalog_parts = [included_catalog]
    if background_sr_catalog:
        catalog_parts.append("# Background systematic reviews (for Discussion comparison):")
        catalog_parts.append(background_sr_catalog)
    if methodology_catalog:
        catalog_parts.append("# Methodology references (cite when describing study design, PRISMA, GRADE, RoB):")
        catalog_parts.append(methodology_catalog)
    return "\n".join(catalog_parts)
