"""Cross-artifact manuscript integrity contracts.

Contracts are deterministic, fast checks that run during FinalizeNode and
at the /api/run/{run_id}/manuscript-contracts endpoint. They catch
structural/integrity defects that must never reach the auditor or a
human reviewer.

The manuscript-auditor agent reads the contract results from
run_summary.json and only audits what contracts do NOT cover:
methodology compliance, narrative quality, benchmark comparison.
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


def _extract_table_row_count(md_text: str) -> int | None:
    marker = "### Study Characteristics"
    pos = md_text.find(marker)
    if pos < 0:
        return None
    section = md_text[pos : pos + 6000]
    lines = section.splitlines()
    in_table = False
    rows = 0
    for line in lines:
        s = line.strip()
        if s.startswith("| Study (Year) |"):
            in_table = True
            continue
        if in_table and s.startswith("|---"):
            continue
        if in_table and s.startswith("| ") and s.endswith(" |"):
            rows += 1
            continue
        if in_table and s.startswith("_Table 1."):
            break
    return rows if in_table else None


def _extract_headings_md(md_text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    normalized_md = _normalize_subsection_heading_layout(md_text)
    for line in normalized_md.splitlines():
        m = re.match(r"^(#{2,4})\s+(.+)$", line.strip())
        if not m:
            continue
        out.append((len(m.group(1)), m.group(2).strip()))
    return out


def _extract_headings_tex(tex_text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in tex_text.splitlines():
        s = line.strip()
        m1 = re.match(r"^\\section\{(.+)\}$", s)
        if m1:
            out.append((2, m1.group(1).strip()))
            continue
        m2 = re.match(r"^\\subsection\{(.+)\}$", s)
        if m2:
            out.append((3, m2.group(1).strip()))
            continue
        m3 = re.match(r"^\\subsubsection\{(.+)\}$", s)
        if m3:
            out.append((4, m3.group(1).strip()))
            continue
    return out


def _find_malformed_heading_lines(md_text: str) -> list[str]:
    """Detect heading lines that likely contain run-on body prose."""
    issues: list[str] = []
    spill_token_re = re.compile(r"\b(The|This|These|We|Our|In|Across|To|A|An)\b")
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^(#{3,6})\s+(.+)$", line)
        if not m:
            continue
        title = m.group(2).strip()
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
        r"\bultimately,\s*(\d{1,4})\s+(?:studies|study)\b",
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
    r"as an ai|language model|i cannot access|i do not have access|"
    r"chatgpt|claude|gemini|assistant:|"
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
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
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
    low = md_text.lower()
    prospective_markers = (
        "registered prospectively",
        "prospectively registered",
    )
    non_prospective_markers = (
        "not prospectively registered",
        "post-hoc registration",
    )
    return any(m in low for m in prospective_markers) and any(m in low for m in non_prospective_markers)


def _find_missing_required_h2_sections(md_text: str) -> list[str]:
    """Return required top-level sections missing from manuscript."""
    required = ("abstract", "introduction", "methods", "results", "discussion", "conclusion", "references")
    present = {
        m.group(1).strip().lower()
        for line in md_text.splitlines()
        if (m := re.match(r"^##\s+(.+)$", line.strip()))
    }
    return [name for name in required if name not in present]


def _find_section_order_violation(md_text: str) -> str | None:
    """Return a brief message when required H2 section order is invalid."""
    required = ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "references"]
    order: dict[str, int] = {}
    for idx, line in enumerate(md_text.splitlines()):
        m = re.match(r"^##\s+(.+)$", line.strip())
        if not m:
            continue
        key = m.group(1).strip().lower()
        if key in required and key not in order:
            order[key] = idx
    if len(order) < len(required):
        return None
    for i in range(1, len(required)):
        if order[required[i]] < order[required[i - 1]]:
            return f"{required[i]} appears before {required[i - 1]}"
    return None


def _find_missing_prisma_statements(md_text: str) -> list[str]:
    """Return required PRISMA-aligned disclosure families missing from prose."""
    low = md_text.lower()
    missing: list[str] = []

    if "independent reviewer" not in low:
        missing.append("selection_process_independent_reviewers")
    if "reports sought for retrieval" not in low:
        missing.append("study_selection_reports_sought_sentence")
    if "reports were not retrieved" not in low and "not retrieved" not in low:
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
            headings.append(m.group(1).strip().lower())
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
        if _AI_LEAKAGE_PATTERNS.search(stripped):
            hits.append(stripped[:120])
    return hits


def _abstract_word_count(md_text: str) -> int | None:
    """Count words in the abstract body (excludes Keywords line)."""
    lines = md_text.splitlines()
    in_abstract = False
    abstract_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and "abstract" in stripped.lower():
            in_abstract = True
            continue
        if in_abstract and stripped.startswith("## "):
            break
        if in_abstract:
            if stripped.lower().startswith("**keywords"):
                continue
            abstract_lines.append(stripped)
    if not abstract_lines:
        return None
    text = " ".join(abstract_lines)
    text = re.sub(r"\*\*[^*]+\*\*:?", "", text)
    return len(text.split())


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
            "MODEL_ID_LEAKAGE",
            "META_FEASIBILITY_CONTRADICTION",
            "ABSTRACT_OVER_LIMIT",
        }
    return True


async def run_manuscript_contracts(
    *,
    repository: WorkflowRepository,
    citation_repository: CitationRepository,
    workflow_id: str,
    manuscript_md_path: str,
    manuscript_tex_path: str | None,
    mode: str = "observe",
) -> ManuscriptContractResult:
    """Validate manuscript integrity invariants across DB and artifacts."""
    violations: list[ContractViolation] = []
    md_text = Path(manuscript_md_path).read_text(encoding="utf-8")
    tex_text = Path(manuscript_tex_path).read_text(encoding="utf-8") if manuscript_tex_path else ""

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
        if md_heads and tex_heads and not _is_heading_subsequence(tex_heads, md_heads):
            violations.append(
                ContractViolation(
                    code="HEADING_PARITY_MISMATCH",
                    severity="error",
                    message="Markdown and LaTeX heading trees diverge.",
                    expected=str(md_heads[:20]),
                    actual=str(tex_heads[:20]),
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

    grade_count_row = await repository.db.execute(
        "SELECT COUNT(*) FROM grade_assessments WHERE workflow_id = ?",
        (workflow_id,),
    )
    grade_row = await grade_count_row.fetchone()
    grade_count = int(grade_row[0]) if grade_row else 0
    grade_mentioned = bool(re.search(r"\bGRADE\b", md_text))
    if grade_mentioned and grade_count == 0:
        violations.append(
            ContractViolation(
                code="GRADE_UNGROUNDED",
                severity="warning",
                message="Manuscript mentions GRADE but no grade_assessments rows exist for this run.",
                expected=">= 1 grade_assessments row",
                actual="0",
            )
        )

    passed = all(not _hard_failure(mode, v.code) for v in violations)
    return ManuscriptContractResult(passed=passed, mode=mode, violations=violations)
