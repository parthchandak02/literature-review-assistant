"""Cross-artifact manuscript integrity contracts."""

from __future__ import annotations

import re
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

    if re.search(r"\b(CITATION_NEEDED|citation unavailable|TODO|TBD)\b", md_text):
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
    refs_numbers = {
        int(m.group(1))
        for m in re.finditer(r"^\[(\d+)\]\s", md_text, flags=re.MULTILINE)
    }
    cited_numbers = {
        int(m.group(1))
        for m in re.finditer(r"\[(\d+)\]", md_text)
        if int(m.group(1)) > 0
    }
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

    passed = all(not _hard_failure(mode, v.code) for v in violations)
    return ManuscriptContractResult(passed=passed, mode=mode, violations=violations)

