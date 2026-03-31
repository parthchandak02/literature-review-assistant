"""Orchestration helpers for writing phase: style extraction + citation ledger wiring."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.citation.ledger import CitationLedger
from src.db.repositories import CitationRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    ClaimRecord,
    EvidenceLinkRecord,
    ReviewConfig,
    SectionBlock,
    SettingsConfig,
    StructuredSectionDraft,
)
from src.writing.humanizer_guardrails import apply_deterministic_guardrails
from src.writing.renderers import render_section_markdown
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
    sanitized = re.sub(r"[^\x20-\x7E]", " ", sanitized)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
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
                        words = nxt.split()
                        consumed = 0
                        for w in words:
                            w_clean = w.strip(".,;:!?")
                            if not w_clean:
                                break
                            if not w_clean[:1].isupper():
                                break
                            consumed += 1
                            if consumed >= 3:
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
            if len(title.split()) > 8 and re.search(r"\s+(?:was|were)\s+", title):
                title = re.split(r"\s+(?:was|were)\s+", title, maxsplit=1)[0]
            # Drop known malformed title fragments.
            if title.lower() in _SECTION_NAMES:
                continue
            if title.lower().endswith((" and", " of", " for", " to", " with")):
                continue
            title = re.sub(r"\s{2,}", " ", title).strip(" -:")
            words = title.split()
            if len(words) > 14:
                title = " ".join(words[:14]).strip()
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
    if all(_present.values()):
        return text

    defaults = {
        "Background": "This topic has important clinical and implementation implications.",
        "Objectives": f"This systematic review addressed {research_question}.",
        "Methods": (
            "Bibliographic databases were searched according to protocol, with "
            "eligibility screening and risk-of-bias assessment."
        ),
        "Results": "Key findings are reported in the manuscript body and synthesis sections.",
        "Conclusions": "The available evidence is synthesized with certainty and limitations considered.",
        "Keywords": "systematic review, evidence synthesis, implementation, outcomes, methodology",
    }
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

_SECTION_REQUIRED_SUBHEADINGS: dict[str, tuple[str, ...]] = {
    "methods": (
        "Eligibility Criteria",
        "Information Sources",
        "Selection Process",
        "Synthesis Methods",
    ),
    "results": (
        "Study Selection",
        "Study Characteristics",
        "Synthesis of Findings",
    ),
}


def _extract_valid_citekeys(citation_catalog: str) -> set[str]:
    keys: set[str] = set()
    for line in citation_catalog.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            keys.add(stripped[1 : stripped.index("]")].strip())
    return keys


def _sanitize_ir_block_text(text: str) -> str:
    """Deterministically sanitize structured block prose before render."""
    cleaned = re.sub(r"[^\x20-\x7E]", " ", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    # Guard against survey-item dumps and raw field enumerations.
    if len(cleaned) > 900 and _EXCESSIVE_LIST_RE.search(cleaned):
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        lower_start_ratio = (
            sum(1 for p in parts if p and p[0].islower()) / len(parts)
            if parts
            else 0.0
        )
        punctuation_ratio = (
            sum(1 for p in parts if any(tok in p for tok in (".", ";", ":"))) / len(parts)
            if parts
            else 0.0
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
) -> StructuredSectionDraft:
    """Run IR-level checks before markdown rendering."""
    normalized_key = (draft.section_key or "").strip().lower()
    if normalized_key != section:
        draft.section_key = section

    required = _SECTION_REQUIRED_SUBHEADINGS.get(section, ())
    if required and not draft.required_subsections:
        draft.required_subsections = list(required)

    seen_subheadings: list[str] = []
    sanitized_blocks: list[SectionBlock] = []
    cited_keys: set[str] = set(draft.cited_keys or [])
    for block in draft.blocks:
        text = _sanitize_ir_block_text(block.text)
        block.text = text
        # Enforce citation key contract at IR level.
        filtered = [k for k in block.citations if k in valid_citekeys]
        block.citations = filtered
        cited_keys.update(filtered)
        if block.block_type == "subheading" and text:
            seen_subheadings.append(text.strip().lower())
        sanitized_blocks.append(block)
    draft.blocks = sanitized_blocks
    draft.cited_keys = sorted(k for k in cited_keys if k in valid_citekeys)

    if required:
        lowered_required = [r.lower() for r in required]
        missing = [r for r in lowered_required if r not in seen_subheadings]
        if missing:
            for title in missing:
                draft.blocks.append(SectionBlock(block_type="subheading", text=title.title(), level=3))
                draft.blocks.append(
                    SectionBlock(
                        block_type="paragraph",
                        text="This subsection is grounded in the factual data block and included-study evidence.",
                    )
                )
    if not draft.blocks:
        draft.blocks = [SectionBlock(block_type="paragraph", text="No section content generated.")]
    return draft


def _is_substantive_paragraph(text: str) -> bool:
    t = str(text or "").strip()
    return len(t) >= 90 and len(t.split()) >= 14


def _section_completeness_issues(section: str, draft: StructuredSectionDraft) -> list[str]:
    """Return deterministic completeness issues for one structured section."""
    issues: list[str] = []
    paragraph_count = sum(1 for b in draft.blocks if b.block_type == "paragraph" and _is_substantive_paragraph(b.text))
    min_required = 2 if section in {"results", "discussion"} else 1
    if paragraph_count < min_required:
        issues.append(f"insufficient_substantive_paragraphs:{paragraph_count}")

    # Required subsections must have a non-empty paragraph before next subheading/end.
    headings = [b for b in draft.blocks if b.block_type == "subheading"]
    if section in _SECTION_REQUIRED_SUBHEADINGS and headings:
        for idx, block in enumerate(draft.blocks):
            if block.block_type != "subheading":
                continue
            j = idx + 1
            has_body = False
            while j < len(draft.blocks):
                nxt = draft.blocks[j]
                if nxt.block_type == "subheading":
                    break
                if nxt.block_type == "paragraph" and nxt.text.strip():
                    has_body = True
                    break
                j += 1
            if not has_body:
                issues.append(f"empty_subsection_body:{block.text.strip().lower()}")

    # Tail cannot end with conjunction/preposition fragment.
    tail = ""
    for b in reversed(draft.blocks):
        if b.block_type == "paragraph" and b.text.strip():
            tail = b.text.strip()
            break
    if tail:
        if _TRAILING_FRAGMENT_RE.search(tail):
            issues.append("trailing_fragment_word")
        elif tail[-1] not in ".!?":
            issues.append("trailing_fragment_punctuation")
    return issues


def _build_deterministic_section_fallback(
    section: str,
    grounding: WritingGroundingData | None,
    valid_citekeys: set[str],
) -> StructuredSectionDraft:
    """Build minimal, complete section content when generation remains malformed."""
    cite = ""
    if valid_citekeys:
        first = sorted(valid_citekeys)[0]
        cite = f" [{first}]"
    if section == "methods":
        sought = getattr(grounding, "fulltext_sought", 0) if grounding is not None else 0
        not_retrieved = getattr(grounding, "fulltext_not_retrieved", 0) if grounding is not None else 0
        assessed = getattr(grounding, "fulltext_assessed", 0) if grounding is not None else 0
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        return StructuredSectionDraft(
            section_key="methods",
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
                        "limited quantitative pooling, and evidence certainty was interpreted with risk-of-bias and GRADE inputs"
                        f"{cite}."
                    ),
                ),
            ],
        )
    if section == "results":
        included = getattr(grounding, "total_included", 0) if grounding is not None else 0
        screened = getattr(grounding, "total_screened", 0) if grounding is not None else 0
        return StructuredSectionDraft(
            section_key="results",
            required_subsections=list(_SECTION_REQUIRED_SUBHEADINGS.get("results", ())),
            blocks=[
                SectionBlock(block_type="subheading", text="Study Selection", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        f"Screening progressed from {screened} records to {included} included studies after full-text "
                        "eligibility decisions and documented exclusion reasons."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Study Characteristics", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Included studies varied by design, setting, and sample size, and are summarized in the in-body "
                        "characteristics table and appendix with extraction provenance"
                        f"{cite}."
                    ),
                ),
                SectionBlock(block_type="subheading", text="Synthesis of Findings", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Findings were synthesized narratively by outcome domain, with effect direction and certainty "
                        "reported conservatively where studies were heterogeneous."
                    ),
                ),
            ],
        )
    if section == "discussion":
        return StructuredSectionDraft(
            section_key="discussion",
            blocks=[
                SectionBlock(block_type="subheading", text="Principal Findings", level=3),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Across included studies, evidence suggests potential educational utility for generative conversational "
                        "AI tutoring tools, but heterogeneity and certainty limitations constrain strong causal conclusions."
                    ),
                ),
                SectionBlock(
                    block_type="paragraph",
                    text=(
                        "Interpretation should remain cautious because outcome definitions, comparator quality, and reporting "
                        "completeness vary substantially across the evidence base."
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

        def _is_topic_relevant(paper: dict) -> bool:
            title_lower = (paper.get("title") or "").lower()
            return any(tok in title_lower for tok in _topic_tokens)

        papers_relevant = [p for p in papers_raw if _is_topic_relevant(p)]
        # Fall back to unfiltered set if no papers survive the filter (very rare).
        if not papers_relevant:
            papers_relevant = papers_raw
            logger.debug("Background SR topic filter matched 0 papers; falling back to unfiltered set.")

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
) -> str:
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

    writer = SectionWriter(
        review=review,
        settings=settings,
        citation_catalog=citation_catalog,
    )
    valid_citekeys = _extract_valid_citekeys(citation_catalog)

    async def _generate_structured_once(ctx: str) -> tuple[StructuredSectionDraft, object]:
        if provider is not None:
            await provider.reserve_call_slot("writing")
        _structured, _metadata = await writer.write_section_structured_async(
            section=section,
            context=ctx,
            word_limit=word_limit,
        )
        _structured = _validate_structured_section_draft(section, _structured, valid_citekeys)
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
        return _structured, _metadata

    structured, metadata = await _generate_structured_once(effective_context)
    issues = _section_completeness_issues(section, structured)
    if issues:
        retry_context = (
            effective_context
            + "\n\nRETRY RULE: Your previous output failed completeness checks: "
            + ", ".join(issues)
            + ". Regenerate this section with complete subsection bodies and a fully closed final sentence."
        )
        logger.warning("Section '%s' failed IR completeness checks (%s); retrying once.", section, ", ".join(issues))
        structured, metadata = await _generate_structured_once(retry_context)
        issues = _section_completeness_issues(section, structured)
        if issues:
            logger.warning(
                "Section '%s' still failed completeness checks after retry (%s); using deterministic fallback.",
                section,
                ", ".join(issues),
            )
            structured = _build_deterministic_section_fallback(section, grounding, valid_citekeys)
    content = render_section_markdown(structured)
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
    # Safety-net: replace any leftover snake_case in prose before saving.
    content = _sanitize_prose(content)
    # Structured rendering already emits normalized headings. Keep legacy
    # heading repair only for obvious malformed patterns from fallback text.
    _needs_heading_repair = bool(
        re.search(r"(?m)^##\s+.+\s+##\s+", content)
        or re.search(r"(?m)^##\s+(Introduction|Methods|Results|Discussion|Conclusion|Abstract)\b", content)
        or re.search(r"(?m)^###\s+.{80,}$", content)
    )
    if _needs_heading_repair:
        content = _sanitize_section_headings(section, content)
    if section == "abstract":
        content = _ensure_structured_abstract(content, review.research_question)

    # Deterministic pre-humanizer guardrails remove repetitive boilerplate while
    # preserving citations and numeric tokens.
    content = apply_deterministic_guardrails(content)

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
    return content


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
