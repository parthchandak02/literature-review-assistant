"""Cross-artifact manuscript integrity contracts.

Contracts are deterministic, fast checks that run during manuscript audit,
finalization, and export. They catch structural/integrity defects that should
feed gate decisions before release.

The manuscript auditor consumes contract summaries as bounded grounding so the
LLM focuses on methodology compliance, narrative quality, and benchmark
comparison rather than rediscovering deterministic defects.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from src.db.repositories import CitationRepository, WorkflowRepository
from src.export.markdown_refs import _normalize_subsection_heading_layout


class ContractViolation(BaseModel):
    """One contract violation emitted by manuscript integrity checks."""

    code: str
    severity: str
    message: str
    expected: str | None = None
    actual: str | None = None


class ManuscriptContractResult(BaseModel):
    """Aggregate integrity contract result."""

    passed: bool
    mode: str
    violations: list[ContractViolation] = Field(default_factory=list)


def _read_optional_utf8_text(path_str: str | None) -> str:
    """Return file contents for optional artifacts that may not exist yet."""
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except IsADirectoryError:
        return ""


def _extract_table_row_count(md_text: str) -> int | None:
    marker = "### Study Characteristics"
    pos = md_text.find(marker)
    if pos < 0:
        return None
    section = md_text[pos:]
    lines = section.splitlines()
    header_re = re.compile(r"^\|\s*Study \(Year\)\s*\|\s*Country\s*\|\s*Design\s*\|\s*N\s*\|\s*Key Finding\s*\|$")
    sep_re = re.compile(r"^\|\s*---")
    row_re = re.compile(r"^\|.*\|$")
    in_table = False
    saw_separator = False
    rows = 0
    for line in lines:
        s = line.strip()
        if not in_table and header_re.match(s):
            in_table = True
            continue
        if not in_table:
            continue
        if sep_re.match(s):
            saw_separator = True
            continue
        if s.startswith("_Table 1."):
            break
        if saw_separator and row_re.match(s):
            rows += 1
            continue
        if saw_separator and s.startswith("### "):
            break
    return rows if in_table and saw_separator else None


def _extract_markdown_figure_paths(md_text: str) -> list[str]:
    paths: list[str] = []
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", md_text):
        raw = m.group(1).strip()
        if raw:
            paths.append(raw)
    return paths


def _extract_markdown_figure_numbers(md_text: str) -> tuple[list[int], list[int]]:
    heading_nums = [int(m.group(1)) for m in re.finditer(r"(?m)^\*\*Fig\.\s*(\d+)\.\*\*", md_text)]
    embed_nums = [int(m.group(1)) for m in re.finditer(r"!\[Fig\.\s*(\d+)\s*:", md_text)]
    return heading_nums, embed_nums


def _extract_tex_figure_paths(tex_text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex_text)]


def _canonical_rel_path(raw: str) -> str:
    return str(Path(str(raw).strip()).as_posix()).lstrip("./")


def _canonical_figure_id(raw: str) -> str:
    norm = _canonical_rel_path(raw)
    return Path(norm).name.rsplit(".", 1)[0].lower()


def _db_phrase(connector_name: str) -> str:
    return str(connector_name or "").replace("_", " ").strip().lower()


def _find_failed_db_disclosure_issues(md_text: str, failed_connectors: list[str]) -> list[str]:
    issues: list[str] = []
    low = md_text.lower()
    for db in failed_connectors:
        phrase = _db_phrase(db)
        if not phrase:
            continue
        if phrase not in low:
            issues.append(f"missing_disclosure:{phrase}")
            continue
        bad_pattern = re.compile(
            rf"{re.escape(phrase)}[^.\n]{{0,180}}\b(?:yielded no relevant records|no relevant records)\b",
            flags=re.IGNORECASE,
        )
        if bad_pattern.search(md_text):
            issues.append(f"mischaracterized_failure_as_zero_yield:{phrase}")
    return issues


def _extract_headings_md(md_text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    normalized_md = _normalize_subsection_heading_layout(md_text)
    for line in normalized_md.splitlines():
        m = re.match(r"^(#{2,4})\s+(.+)$", line.strip())
        if not m:
            continue
        out.append((len(m.group(1)), _normalize_heading_for_parity(m.group(2))))
    return out


def _extract_headings_tex(tex_text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in tex_text.splitlines():
        s = line.strip()
        m1 = re.match(r"^\\section\{(.+)\}$", s)
        if m1:
            out.append((2, _normalize_heading_for_parity(m1.group(1))))
            continue
        m2 = re.match(r"^\\subsection\{(.+)\}$", s)
        if m2:
            out.append((3, _normalize_heading_for_parity(m2.group(1))))
            continue
        m3 = re.match(r"^\\subsubsection\{(.+)\}$", s)
        if m3:
            out.append((4, _normalize_heading_for_parity(m3.group(1))))
            continue
    return out


def _normalize_heading_for_parity(raw: str) -> str:
    title = str(raw or "").strip()
    title = re.sub(r"\s*(?:\[[^\]]+\]\s*)+$", "", title)
    title = re.sub(r"\\[A-Za-z]+\{([^}]*)\}", r"\1", title)
    title = re.sub(r"[^A-Za-z0-9 ]+", " ", title)
    return re.sub(r"\s{2,}", " ", title).strip().lower()


def _find_malformed_heading_lines(md_text: str) -> list[str]:
    """Detect heading lines that likely contain run-on body prose."""
    issues: list[str] = []
    spill_token_re = re.compile(r"\b(The|This|These|We|Our|In|Across|To|A|An)\b")
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^(#{2,6})\s+(.+)$", line)
        if not m:
            continue
        title = m.group(2).strip()
        if "## " in title:
            issues.append(line)
            continue
        words = title.split()
        if not words:
            continue
        spill = spill_token_re.search(title)
        if spill and spill.start() > 10:
            issues.append(line)
            continue
        if len(words) >= 10 and any(
            w.lower() in {"was", "were", "is", "are", "conducted", "assessed", "screened", "searched"}
            for w in words[4:]
        ):
            issues.append(line)
    return issues


def _extract_disclosed_included_counts(md_text: str) -> set[int]:
    """Extract explicit included-study counts disclosed in narrative text."""
    body = md_text.split("## References", 1)[0]
    counts: set[int] = set()
    patterns = (
        r"\b(\d{1,4})\s+(?:studies|study)\s+(?:were|was)?\s*included\b",
        r"\bincluded\s+(\d{1,4})\s+(?:studies|study)\b",
        r"\bultimately,?\s*(\d{1,4})\s+(?:studies|study)\b",
        r"\bwith\s+(\d{1,4})\s+(?:studies|study)\s+ultimately\s+included\b",
        r"\bwe\s+included\s+(\d{1,4})\s+(?:studies|study)\b",
    )
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("#"):
            continue
        for pat in patterns:
            for m in re.finditer(pat, stripped, flags=re.IGNORECASE):
                try:
                    counts.add(int(m.group(1)))
                except Exception:
                    continue
    return counts


def _is_heading_subsequence(needles: list[tuple[int, str]], haystack: list[tuple[int, str]]) -> bool:
    """Return True if each needle heading appears in haystack order."""
    if not needles:
        return True
    j = 0
    for level, title in haystack:
        n_level, n_title = needles[j]
        if level == n_level and title.strip().lower() == n_title.strip().lower():
            j += 1
            if j >= len(needles):
                return True
    return False


_AI_LEAKAGE_PATTERNS = re.compile(
    r"\b("
    r"as an ai language model|as a language model|i cannot access|i do not have access|"
    r"assistant:|"
    r"```|import re\b|subprocess\.run|pip install|"
    r"Congratulations on finishing"
    r")\b",
    re.IGNORECASE,
)


def _find_snake_case_prose_tokens(md_text: str) -> list[str]:
    """Detect snake_case tokens in manuscript prose outside code/refs."""
    hits: set[str] = set()
    ref_start = md_text.find("## References")
    body = md_text[:ref_start] if ref_start > 0 else md_text
    token_re = re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b")
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("!["):
            continue
        for token in token_re.findall(stripped):
            hits.add(token)
    return sorted(hits)


def _find_model_id_leakage(md_text: str) -> list[str]:
    """Detect raw model identifier leakage in prose."""
    hits: list[str] = []
    ref_start = md_text.find("## References")
    body = md_text[:ref_start] if ref_start > 0 else md_text
    model_re = re.compile(
        r"\b(?:google-gla:[A-Za-z0-9._-]+|gemini-[A-Za-z0-9._-]+|models/[A-Za-z0-9._-]+)\b",
        re.IGNORECASE,
    )
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if model_re.search(stripped):
            hits.append(stripped[:140])
    return hits


def _find_meta_feasibility_contradiction(md_text: str) -> bool:
    """Detect contradictory narrative about meta-analysis feasibility."""
    low = md_text.lower()
    feasible_markers = (
        "meta-analysis was feasible",
        "conducted a meta-analysis",
        "pooled effect size",
    )
    infeasible_markers = (
        "meta-analysis was not feasible",
        "narrative synthesis only",
        "pooling was not feasible",
    )
    return any(m in low for m in feasible_markers) and any(m in low for m in infeasible_markers)


def _find_protocol_registration_contradiction(md_text: str) -> bool:
    """Detect contradictory protocol registration claims."""
    lines = [ln.strip().lower() for ln in md_text.splitlines() if ln.strip()]
    has_non_prospective = any(
        ("not prospectively registered" in ln) or ("post-hoc registration" in ln) for ln in lines
    )
    if not has_non_prospective:
        return False
    # Positive markers must appear in a non-negated context.
    has_prospective_positive = any(
        (
            ("registered prospectively" in ln or "prospectively registered" in ln)
            and ("not prospectively registered" not in ln)
        )
        for ln in lines
    )
    return has_non_prospective and has_prospective_positive


def _canonical_h2_name(raw_heading: str) -> str:
    text = re.sub(r"\*\*", "", str(raw_heading or ""))
    text = re.sub(r"[_`]+", " ", text).strip().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _extract_abstract_lines(md_text: str) -> list[str]:
    normalized = re.sub(r"\s+(##\s+)", r"\n\n\1", md_text)
    lines = normalized.splitlines()
    in_abstract = False
    abstract_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        m = re.match(r"^##\s+abstract\b(.*)$", stripped, flags=re.IGNORECASE)
        if m:
            in_abstract = True
            remainder = m.group(1).strip()
            if remainder:
                abstract_lines.append(remainder)
            continue
        if in_abstract and stripped.startswith("## "):
            break
        if in_abstract:
            if stripped.lower().startswith("**keywords"):
                continue
            abstract_lines.append(stripped)
    return abstract_lines


def _find_missing_required_h2_sections(md_text: str) -> list[str]:
    """Return required top-level sections missing from manuscript."""
    required = ("abstract", "introduction", "methods", "results", "discussion", "conclusion", "references")
    present: set[str] = set()
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.+)$", line.strip())
        if not m:
            continue
        heading = _canonical_h2_name(m.group(1))
        for name in required:
            if heading == name or heading.startswith(f"{name} "):
                present.add(name)
                break
    return [name for name in required if name not in present]


def _find_section_order_violation(md_text: str) -> str | None:
    """Return a brief message when required H2 section order is invalid."""
    required = ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "references"]
    order: dict[str, int] = {}
    for idx, line in enumerate(md_text.splitlines()):
        m = re.match(r"^##\s+(.+)$", line.strip())
        if not m:
            continue
        key = _canonical_h2_name(m.group(1))
        for req in required:
            if key == req or key.startswith(f"{req} "):
                key = req
                break
        if key in required and key not in order:
            order[key] = idx
    if len(order) < len(required):
        return None
    for i in range(1, len(required)):
        if order[required[i]] < order[required[i - 1]]:
            return f"{required[i]} appears before {required[i - 1]}"
    return None


def _extract_h2_sections(md_text: str) -> dict[str, str]:
    """Map canonical H2 names to their section body text."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in md_text.splitlines():
        stripped = raw.strip()
        m = re.match(r"^##\s+(.+)$", stripped)
        if m:
            key = _canonical_h2_name(m.group(1))
            for req in ("abstract", "introduction", "methods", "results", "discussion", "conclusion", "references"):
                if key == req or key.startswith(f"{req} "):
                    key = req
                    break
            current = key
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _find_section_content_incomplete(md_text: str, included_study_count: int) -> list[str]:
    """Detect hollow or truncated required section bodies."""
    issues: list[str] = []
    sections = _extract_h2_sections(md_text)
    trailing_re = re.compile(r"\b(and|or|with|to|for|in|of|by|vs)\s*$", flags=re.IGNORECASE)
    for name in ("results", "discussion"):
        body = sections.get(name, "").strip()
        if not body:
            issues.append(f"{name}:empty_body")
            continue
        paragraphs: list[str] = []
        buf: list[str] = []
        for line in body.splitlines():
            s = line.strip()
            if not s:
                if buf:
                    paragraphs.append(" ".join(buf).strip())
                    buf.clear()
                continue
            if s.startswith("#"):
                if buf:
                    paragraphs.append(" ".join(buf).strip())
                    buf.clear()
                continue
            buf.append(s)
        if buf:
            paragraphs.append(" ".join(buf).strip())
        substantive = [p for p in paragraphs if len(p) >= 90 and len(p.split()) >= 14]
        min_required = 2 if included_study_count > 1 else 1
        if len(substantive) < min_required:
            issues.append(f"{name}:insufficient_substantive_paragraphs:{len(substantive)}")
        # Degenerate repetition guard: catches failures like repeated "Work"
        # lines under Discussion subsections that pass generic length checks.
        short_paragraphs = []
        for p in paragraphs:
            p_norm = re.sub(r"[^A-Za-z0-9 ]", "", p).strip().lower()
            if not p_norm:
                continue
            if len(p_norm) <= 20 and len(p_norm.split()) <= 3:
                short_paragraphs.append(p_norm)
        repeated_short = [frag for frag, cnt in Counter(short_paragraphs).items() if cnt >= 3]
        if repeated_short:
            issues.append(f"{name}:degenerate_repetition:{repeated_short[0]}")
        tail = substantive[-1] if substantive else (paragraphs[-1] if paragraphs else "")
        if tail:
            if trailing_re.search(tail):
                issues.append(f"{name}:trailing_fragment_word")
            elif tail[-1] not in ".!?":
                issues.append(f"{name}:trailing_fragment_punctuation")
    return issues


def _find_implications_misplaced(md_text: str) -> list[str]:
    """Detect implication subsections placed under Conclusion instead of Discussion."""
    issues: list[str] = []
    sections = _extract_h2_sections(md_text)
    conclusion = sections.get("conclusion", "")
    discussion = sections.get("discussion", "")
    implications = (
        "### Implications for Practice",
        "### Implications for Research",
    )
    misplaced = [h for h in implications if h.lower() in conclusion.lower()]
    if misplaced:
        missing_in_discussion = [h for h in implications if h.lower() not in discussion.lower()]
        if missing_in_discussion:
            issues.extend(h.lower().replace("### ", "") for h in missing_in_discussion)
    return issues


def _find_rob_figure_caption_mismatch(md_text: str) -> bool:
    """Detect static ROBINS-I/CASP figure caption when MMAT is the active tool family."""
    low = md_text.lower()
    has_mmat = "## mmat quality assessment" in low or "mmat (mixed-methods" in low
    has_legacy_caption = "risk of bias traffic-light plot for included non-randomized studies and reviews (robins-i/casp)" in low
    return bool(has_mmat and has_legacy_caption)


def _grade_claimed_without_rows(md_text: str) -> bool:
    """Return True when manuscript claims GRADE use in non-negated prose."""
    lines = [ln.strip().lower() for ln in md_text.splitlines() if "grade" in ln.lower()]
    if not lines:
        return False
    negative_markers = (
        "no grade",
        "without grade",
        "grade was not",
        "grade assessment was not",
        "grade certainty assessment was not",
        "no grade certainty assessment was performed",
    )
    for line in lines:
        if any(marker in line for marker in negative_markers):
            continue
        return True
    return False


def _find_missing_prisma_statements(md_text: str) -> list[str]:
    """Return required PRISMA-aligned disclosure families missing from prose."""
    low = md_text.lower()
    missing: list[str] = []

    if (
        ("independent reviewer" not in low)
        and ("independent reviewers" not in low)
        and ("independent dual review" not in low)
        and ("two independent reviewers" not in low)
    ):
        missing.append("selection_process_independent_reviewers")
    if re.search(
        r"reports?\s+(?:were\s+|was\s+|being\s+)?(?:\w+\s+){0,3}?sought\s+for(?:\s+full[-\u2010-\u2015 ]text)?\s+retrieval",
        low,
    ) is None and re.search(
        r"\b(?:\d+\s+)?reports?\s+for\s+full[-\u2010-\u2015 ]text\s+retrieval\b",
        low,
    ) is None and re.search(
        r"sought\s+full[-\u2010-\u2015 ]text\s+retrieval\s+for\s+(?:the\s+remaining\s+)?\d+\s+reports?",
        low,
    ) is None and re.search(
        r"advanced\s+to\s+full[-\u2010-\u2015 ]text\s+retrieval",
        low,
    ) is None and re.search(
        r"forwarded\s+for\s+full[-\u2010-\u2015 ]text\s+retrieval",
        low,
    ) is None:
        missing.append("study_selection_reports_sought_sentence")
    if (
        re.search(r"reports?\s+(?:were\s+|was\s+)?not\s+retrieved", low) is None
        and re.search(r"(?:reports?\s+)?could\s+not\s+be\s+retrieved", low) is None
        and re.search(r"reports?\s+remained\s+irretrievable", low) is None
    ):
        missing.append("study_selection_not_retrieved_disclosure")
    if "protocol registration" not in low and "registered" not in low:
        missing.append("protocol_registration_disclosure")
    if "risk of bias" not in low and "rob " not in low and "robins-i" not in low:
        missing.append("risk_of_bias_disclosure")
    return missing


def _find_duplicate_h2_sections(md_text: str) -> list[str]:
    """Return H2 heading titles that appear more than once."""
    headings: list[str] = []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.+)$", line.strip())
        if m:
            headings.append(_canonical_h2_name(m.group(1)))
    counts = Counter(headings)
    return [title for title, n in counts.items() if n > 1]


def _detect_ai_leakage(md_text: str) -> list[str]:
    """Return lines containing AI/chat/code artifact leakage."""
    hits: list[str] = []
    ref_start = md_text.find("## References")
    body = md_text[:ref_start] if ref_start > 0 else md_text
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Study tables can legitimately mention AI system names (e.g., ChatGPT)
        # as intervention content; leakage checks target narrative/code artifacts.
        if stripped.startswith("|"):
            continue
        if _AI_LEAKAGE_PATTERNS.search(stripped):
            hits.append(stripped[:120])
    return hits


def _abstract_word_count(md_text: str) -> int | None:
    """Count words in the abstract body (excludes Keywords line)."""
    abstract_lines = _extract_abstract_lines(md_text)
    if not abstract_lines:
        return None
    text = " ".join(abstract_lines)
    text = re.sub(r"\*\*[^*]+\*\*:?", "", text)
    return len(text.split())


def _missing_abstract_fields(md_text: str) -> list[str]:
    """Return required structured abstract labels missing from abstract section."""
    abstract_lines = _extract_abstract_lines(md_text)
    if not abstract_lines:
        return ["background", "objectives", "methods", "results", "conclusions"]
    abstract_text = "\n".join(abstract_lines)
    required = {
        "background": r"\*\*Background:\*\*",
        "objectives": r"\*\*Objectives:\*\*",
        "methods": r"\*\*Methods:\*\*",
        "results": r"\*\*Results:\*\*",
        "conclusions": r"\*\*(Conclusion|Conclusions):\*\*",
    }
    return [name for name, pattern in required.items() if re.search(pattern, abstract_text, flags=re.IGNORECASE) is None]


def _find_protocol_registration_future_tense(md_text: str) -> bool:
    """Detect future-tense protocol registration claims in finalized manuscript."""
    low = md_text.lower()
    patterns = (
        "will be registered",
        "to be registered",
        "planned registration",
        "will register",
    )
    return any(p in low for p in patterns)


def _extract_cited_citekeys_from_tex(tex_text: str) -> set[str]:
    """Extract citekeys from LaTeX \\cite{...} commands."""
    keys: set[str] = set()
    for match in re.finditer(r"\\cite\{([^}]+)\}", tex_text):
        for part in match.group(1).split(","):
            k = part.strip()
            if k:
                keys.add(k)
    return keys


def _extract_bib_keys(bib_text: str) -> set[str]:
    """Extract BibTeX entry keys from references.bib."""
    return {m.group(1).strip() for m in re.finditer(r"@\w+\{([^,]+),", bib_text)}


def _hard_failure(mode: str, code: str) -> bool:
    if mode == "observe":
        return False
    if mode == "soft":
        return code in {
            "PLACEHOLDER_LEAK",
            "UNRESOLVED_CITATIONS",
            "NON_PRIMARY_IN_TABLE",
            "INCLUDED_COUNT_MISMATCH",
            "HEADING_PARITY_MISMATCH",
            "MALFORMED_SECTION_HEADING",
            "PLACEHOLDER_FRAGMENT",
            "COUNT_DISCLOSURE_MISMATCH",
            "AI_LEAKAGE",
            "DUPLICATE_H2_SECTION",
            "REQUIRED_SECTION_MISSING",
            "SECTION_ORDER_INVALID",
            "PRISMA_STATEMENT_MISSING",
            "PROTOCOL_REGISTRATION_CONTRADICTION",
            "PROTOCOL_REGISTRATION_FUTURE_TENSE",
            "MODEL_ID_LEAKAGE",
            "META_FEASIBILITY_CONTRADICTION",
            "ABSTRACT_OVER_LIMIT",
            "ABSTRACT_STRUCTURE_MISSING_FIELDS",
            "UNUSED_BIB_ENTRY",
            "ARTIFACT_PLACEHOLDER_LEAK",
            "SECTION_CONTENT_INCOMPLETE",
            "IMPLICATIONS_MISPLACED",
            "ROB_FIGURE_CAPTION_MISMATCH",
            "FAILED_DB_DISCLOSURE_MISSING",
            "FAILED_DB_STATUS_MISCHARACTERIZED",
            "FIGURE_ASSET_MISSING",
            "FIGURE_NUMBERING_INVALID",
            "FIGURE_LATEX_MISMATCH",
        }
    return True


async def run_manuscript_contracts(
    *,
    repository: WorkflowRepository,
    citation_repository: CitationRepository,
    workflow_id: str,
    manuscript_md_path: str,
    manuscript_tex_path: str | None,
    extra_artifact_paths: list[str] | None = None,
    mode: str = "observe",
) -> ManuscriptContractResult:
    """Validate manuscript integrity invariants across DB and artifacts."""
    violations: list[ContractViolation] = []
    md_text = Path(manuscript_md_path).read_text(encoding="utf-8")
    tex_text = _read_optional_utf8_text(manuscript_tex_path)

    synthesis_ids = await repository.get_synthesis_included_paper_ids(workflow_id)
    if not synthesis_ids:
        synthesis_ids = await repository.get_included_paper_ids(workflow_id)

    table_row_count = _extract_table_row_count(md_text)
    if table_row_count is not None and table_row_count != len(synthesis_ids):
        violations.append(
            ContractViolation(
                code="INCLUDED_COUNT_MISMATCH",
                severity="error",
                message="Manuscript study table row count disagrees with canonical synthesis cohort.",
                expected=str(len(synthesis_ids)),
                actual=str(table_row_count),
            )
        )

    non_primary_included = await repository.db.execute(
        """
        SELECT COUNT(*)
        FROM study_cohort_membership
        WHERE workflow_id = ?
          AND synthesis_eligibility IN ('excluded_non_primary', 'excluded_failed_extraction')
          AND paper_id IN (
              SELECT paper_id
              FROM study_cohort_membership
              WHERE workflow_id = ? AND synthesis_eligibility = 'included_primary'
          )
        """,
        (workflow_id, workflow_id),
    )
    non_primary_row = await non_primary_included.fetchone()
    non_primary_count = int(non_primary_row[0]) if non_primary_row else 0
    if non_primary_count > 0:
        violations.append(
            ContractViolation(
                code="NON_PRIMARY_IN_TABLE",
                severity="error",
                message="Canonical cohort marks non-primary papers inside included synthesis set.",
                expected="0",
                actual=str(non_primary_count),
            )
        )

    if re.search(
        r"\b(CITATION_NEEDED|citation unavailable|TODO|TBD|Ref\d+|Paper_[A-Za-z0-9_\-]+)\b",
        md_text,
    ):
        violations.append(
            ContractViolation(
                code="PLACEHOLDER_LEAK",
                severity="error",
                message="Manuscript contains unresolved placeholder tokens.",
            )
        )
    if re.search(
        r"\|\s*Inclusion criteria\s*\|\s*[^|\n]*(?:^|;)\s*(?:and\s+)?will\s+be\s+considered\b",
        md_text,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        violations.append(
            ContractViolation(
                code="PLACEHOLDER_FRAGMENT",
                severity="error",
                message="Manuscript contains dangling placeholder fragments in criteria text.",
            )
        )
    malformed_headings = _find_malformed_heading_lines(md_text)
    if malformed_headings:
        violations.append(
            ContractViolation(
                code="MALFORMED_SECTION_HEADING",
                severity="error",
                message="Manuscript contains malformed run-on section headings.",
                actual=str(malformed_headings[:5]),
            )
        )

    disclosed_counts = _extract_disclosed_included_counts(md_text)
    if disclosed_counts and disclosed_counts != {len(synthesis_ids)}:
        violations.append(
            ContractViolation(
                code="COUNT_DISCLOSURE_MISMATCH",
                severity="error",
                message="Narrative included-study counts do not match canonical synthesis cohort.",
                expected=str(len(synthesis_ids)),
                actual=str(sorted(disclosed_counts)),
            )
        )

    citations = await citation_repository.get_all_citations_for_export()
    refs_numbers = {int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]\s", md_text, flags=re.MULTILINE)}
    cited_numbers = {int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", md_text) if int(m.group(1)) > 0}
    if cited_numbers and refs_numbers and not cited_numbers.issubset(refs_numbers):
        violations.append(
            ContractViolation(
                code="UNRESOLVED_CITATIONS",
                severity="error",
                message="Body cites numbered references not present in References section.",
                expected=str(sorted(refs_numbers)),
                actual=str(sorted(cited_numbers)),
            )
        )
    if citations and cited_numbers and not refs_numbers:
        violations.append(
            ContractViolation(
                code="UNRESOLVED_CITATIONS",
                severity="error",
                message="Citation catalog exists but manuscript References numbering was not parsed.",
            )
        )

    if manuscript_tex_path and tex_text:
        md_heads = _extract_headings_md(md_text)
        tex_heads = _extract_headings_tex(tex_text)
        md_heads_for_parity = [h for h in md_heads if not (h[0] == 2 and h[1] == "abstract")]
        if md_heads_for_parity and tex_heads and not _is_heading_subsequence(tex_heads, md_heads_for_parity):
            violations.append(
                ContractViolation(
                    code="HEADING_PARITY_MISMATCH",
                    severity="error",
                    message="Markdown and LaTeX heading trees diverge.",
                    expected=str(md_heads_for_parity[:20]),
                    actual=str(tex_heads[:20]),
                )
            )

    md_figure_paths = _extract_markdown_figure_paths(md_text)
    if md_figure_paths:
        md_parent = Path(manuscript_md_path).parent
        missing_figure_paths: list[str] = []
        for rel in md_figure_paths:
            resolved = (md_parent / rel).resolve()
            if not resolved.exists() or resolved.stat().st_size <= 0:
                missing_figure_paths.append(rel)
        if missing_figure_paths:
            violations.append(
                ContractViolation(
                    code="FIGURE_ASSET_MISSING",
                    severity="error",
                    message="Manuscript references figure assets that are missing or empty.",
                    actual=str(sorted(set(missing_figure_paths))),
                )
            )

        heading_nums, embed_nums = _extract_markdown_figure_numbers(md_text)
        expected_seq = list(range(1, len(heading_nums) + 1))
        if heading_nums and heading_nums != expected_seq:
            violations.append(
                ContractViolation(
                    code="FIGURE_NUMBERING_INVALID",
                    severity="error",
                    message="Markdown figure headings are not strictly sequential.",
                    expected=str(expected_seq),
                    actual=str(heading_nums),
                )
            )
        if heading_nums and embed_nums and embed_nums != heading_nums:
            violations.append(
                ContractViolation(
                    code="FIGURE_NUMBERING_INVALID",
                    severity="error",
                    message="Markdown figure headings and image embed labels disagree.",
                    expected=str(heading_nums),
                    actual=str(embed_nums),
                )
            )

    if manuscript_tex_path and tex_text and md_figure_paths:
        raster_suffixes = {".png", ".jpg", ".jpeg", ".pdf"}
        md_raster = sorted(
            {
                _canonical_figure_id(p)
                for p in md_figure_paths
                if Path(_canonical_rel_path(p)).suffix.lower() in raster_suffixes
            }
        )
        tex_raster = sorted({_canonical_figure_id(p) for p in _extract_tex_figure_paths(tex_text)})
        if md_raster and tex_raster and md_raster != tex_raster:
            violations.append(
                ContractViolation(
                    code="FIGURE_LATEX_MISMATCH",
                    severity="error",
                    message="LaTeX embedded figure set diverges from markdown raster figure set.",
                    expected=str(md_raster),
                    actual=str(tex_raster),
                )
            )

    dup_sections = _find_duplicate_h2_sections(md_text)
    if dup_sections:
        violations.append(
            ContractViolation(
                code="DUPLICATE_H2_SECTION",
                severity="error",
                message="Manuscript contains duplicate H2 section headings.",
                actual=str(dup_sections),
            )
        )

    missing_h2 = _find_missing_required_h2_sections(md_text)
    if missing_h2:
        violations.append(
            ContractViolation(
                code="REQUIRED_SECTION_MISSING",
                severity="error",
                message="Manuscript is missing required top-level sections.",
                expected="abstract,introduction,methods,results,discussion,conclusion,references",
                actual=str(missing_h2),
            )
        )

    order_issue = _find_section_order_violation(md_text)
    if order_issue:
        violations.append(
            ContractViolation(
                code="SECTION_ORDER_INVALID",
                severity="error",
                message="Required section order is invalid.",
                actual=order_issue,
            )
        )

    section_content_issues = _find_section_content_incomplete(md_text, len(synthesis_ids))
    if section_content_issues:
        violations.append(
            ContractViolation(
                code="SECTION_CONTENT_INCOMPLETE",
                severity="error",
                message="Required section content is hollow or truncated.",
                actual=str(section_content_issues),
            )
        )

    misplaced_implications = _find_implications_misplaced(md_text)
    if misplaced_implications:
        violations.append(
            ContractViolation(
                code="IMPLICATIONS_MISPLACED",
                severity="error",
                message="Implications subsections are misplaced under Conclusion while missing from Discussion.",
                actual=str(misplaced_implications),
            )
        )

    if _find_rob_figure_caption_mismatch(md_text):
        violations.append(
            ContractViolation(
                code="ROB_FIGURE_CAPTION_MISMATCH",
                severity="error",
                message="Risk-of-bias figure caption family conflicts with active MMAT assessment evidence.",
            )
        )

    try:
        failed_connectors = await repository.get_failed_search_connectors(workflow_id)
    except Exception:
        failed_connectors = []
    failed_db_issues = _find_failed_db_disclosure_issues(md_text, failed_connectors)
    for issue in failed_db_issues:
        if issue.startswith("missing_disclosure:"):
            db_name = issue.split(":", 1)[1]
            violations.append(
                ContractViolation(
                    code="FAILED_DB_DISCLOSURE_MISSING",
                    severity="error",
                    message="A failed search connector is missing from manuscript disclosure.",
                    actual=db_name,
                )
            )
        elif issue.startswith("mischaracterized_failure_as_zero_yield:"):
            db_name = issue.split(":", 1)[1]
            violations.append(
                ContractViolation(
                    code="FAILED_DB_STATUS_MISCHARACTERIZED",
                    severity="error",
                    message="A failed search connector is phrased as a successful zero-yield search.",
                    actual=db_name,
                )
            )

    missing_prisma = _find_missing_prisma_statements(md_text)
    if missing_prisma:
        violations.append(
            ContractViolation(
                code="PRISMA_STATEMENT_MISSING",
                severity="error",
                message="Required PRISMA-aligned disclosure statements are missing.",
                actual=str(missing_prisma),
            )
        )

    leakage_hits = _detect_ai_leakage(md_text)
    if leakage_hits:
        violations.append(
            ContractViolation(
                code="AI_LEAKAGE",
                severity="error",
                message="Manuscript body contains AI/chat/code artifact leakage.",
                actual=str(leakage_hits[:5]),
            )
        )

    snake_hits = _find_snake_case_prose_tokens(md_text)
    if snake_hits:
        violations.append(
            ContractViolation(
                code="SNAKE_CASE_LEAKAGE",
                severity="warning",
                message="Manuscript prose contains snake_case tokens that should be naturalized upstream.",
                actual=str(snake_hits[:20]),
            )
        )

    model_id_hits = _find_model_id_leakage(md_text)
    if model_id_hits:
        violations.append(
            ContractViolation(
                code="MODEL_ID_LEAKAGE",
                severity="error",
                message="Manuscript body leaks raw model identifiers.",
                actual=str(model_id_hits[:5]),
            )
        )

    if _find_meta_feasibility_contradiction(md_text):
        violations.append(
            ContractViolation(
                code="META_FEASIBILITY_CONTRADICTION",
                severity="error",
                message="Manuscript contains contradictory statements about meta-analysis feasibility.",
            )
        )

    if _find_protocol_registration_contradiction(md_text):
        violations.append(
            ContractViolation(
                code="PROTOCOL_REGISTRATION_CONTRADICTION",
                severity="error",
                message="Manuscript contains contradictory statements about protocol registration timing.",
            )
        )

    if _find_protocol_registration_future_tense(md_text):
        violations.append(
            ContractViolation(
                code="PROTOCOL_REGISTRATION_FUTURE_TENSE",
                severity="error",
                message="Manuscript contains future-tense protocol registration claims.",
            )
        )

    abs_words = _abstract_word_count(md_text)
    if abs_words is not None and abs_words > 250:
        violations.append(
            ContractViolation(
                code="ABSTRACT_OVER_LIMIT",
                severity="error",
                message="Abstract exceeds 250-word IEEE limit.",
                expected="<= 250",
                actual=str(abs_words),
            )
        )
    missing_abs = _missing_abstract_fields(md_text)
    if missing_abs:
        violations.append(
            ContractViolation(
                code="ABSTRACT_STRUCTURE_MISSING_FIELDS",
                severity="error",
                message="Structured abstract is missing required labeled fields.",
                actual=str(missing_abs),
            )
        )

    if manuscript_tex_path and tex_text:
        bib_path = Path(manuscript_tex_path).parent / "references.bib"
        if bib_path.exists():
            bib_keys = _extract_bib_keys(bib_path.read_text(encoding="utf-8"))
            cited_keys = _extract_cited_citekeys_from_tex(tex_text)
            unused = sorted(k for k in bib_keys if k not in cited_keys)
            if unused:
                violations.append(
                    ContractViolation(
                        code="UNUSED_BIB_ENTRY",
                        severity="error",
                        message="references.bib contains entries not cited in manuscript.tex.",
                        actual=str(unused[:20]),
                    )
                )

    if extra_artifact_paths:
        leaked_files: list[str] = []
        banned = re.compile(r"\b(TBD|TODO|TO BE ASSIGNED)\b", flags=re.IGNORECASE)
        for p in extra_artifact_paths:
            if not p:
                continue
            path = Path(p)
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".tex", ".txt"}:
                continue
            try:
                txt = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if banned.search(txt):
                leaked_files.append(path.name)
        if leaked_files:
            violations.append(
                ContractViolation(
                    code="ARTIFACT_PLACEHOLDER_LEAK",
                    severity="error",
                    message="Submission-critical artifacts contain banned placeholder tokens.",
                    actual=str(sorted(set(leaked_files))),
                )
            )

    grade_count_row = await repository.db.execute(
        "SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?",
        (workflow_id,),
    )
    grade_row = await grade_count_row.fetchone()
    grade_count = int(grade_row[0]) if grade_row else 0
    grade_claimed = _grade_claimed_without_rows(md_text)
    if grade_claimed and grade_count == 0:
        violations.append(
            ContractViolation(
                code="GRADE_UNGROUNDED",
                severity="error",
                message="Manuscript mentions GRADE but no grade_assessments rows exist for this run.",
                expected=">= 1 grade_assessments row",
                actual="0",
            )
        )

    passed = all(not _hard_failure(mode, v.code) for v in violations)
    return ManuscriptContractResult(passed=passed, mode=mode, violations=violations)
