"""Deterministic PRISMA 2020 checklist validator."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

_STATUS_REPORTED = "REPORTED"
_STATUS_PARTIAL = "PARTIAL"
_STATUS_MISSING = "MISSING"
_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class PrismaRule:
    """Rule describing one PRISMA item check."""

    item_id: str
    section: str
    description: str
    keyword_groups: tuple[tuple[str, ...], ...]
    scopes: tuple[str, ...]
    applies_if: str | None = None


@dataclass
class PrismaItemResult:
    """Result for one PRISMA item."""

    item_id: str
    section: str
    description: str
    status: str  # REPORTED | PARTIAL | MISSING | NOT_APPLICABLE
    rationale: str = ""
    applies: bool = True
    evidence_terms: list[str] = field(default_factory=list)


@dataclass
class PrismaValidationResult:
    """Result of PRISMA checklist validation."""

    items: list[PrismaItemResult] = field(default_factory=list)
    reported_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    not_applicable_count: int = 0
    passed: bool = False  # compatibility score (>=24/27)
    source_state: str = "artifact_missing"  # artifact_missing | validated_md | validated_tex | validated_md_and_tex
    primary_total: int = 27


_PRISMA_RULES: tuple[PrismaRule, ...] = (
    PrismaRule("1", "Title", "Identify report as systematic review", (("systematic review", "meta-analysis", "meta analysis"),), ("title",)),
    PrismaRule("2", "Abstract", "Structured abstract reports PRISMA abstract items", (("objective", "aim", "purpose"), ("method", "methods"), ("result", "results"), ("conclusion", "conclusions")), ("abstract",)),
    PrismaRule("3", "Introduction", "Rationale in context of existing knowledge", (("rationale", "background", "context"), ("gap", "uncertaint", "needed", "necessary")), ("introduction",)),
    PrismaRule("4", "Introduction", "Explicit objectives or questions", (("objective", "aim", "research question", "question"),), ("introduction", "abstract")),
    PrismaRule("5", "Methods", "Eligibility criteria and synthesis groups", (("eligibility", "inclusion", "exclusion"), ("study design", "population", "intervention", "outcome", "pico")), ("methods",)),
    PrismaRule("6", "Methods", "Information sources and last search dates", (("database", "register", "source", "website"), ("searched", "search date", "last search")), ("methods",)),
    PrismaRule("7", "Methods", "Full search strategies with filters and limits", (("search strategy", "search string", "query"), ("filter", "limit", "boolean")), ("methods", "other")),
    PrismaRule("8", "Methods", "Selection process including reviewer independence and automation use", (("selection", "screening"), ("reviewer", "independent", "adjudicat"), ("automation", "machine learning", "batch", "bm25", "tool")), ("methods",)),
    PrismaRule("9", "Methods", "Data collection process including reviewer processes", (("data collection", "data extraction"), ("reviewer", "independent", "disagreement")), ("methods",)),
    PrismaRule("10a", "Methods", "Data items outcomes defined and sought", (("outcome", "outcomes"), ("defined", "sought", "time point")), ("methods",)),
    PrismaRule("10b", "Methods", "Other data items and assumptions for missing info", (("participant", "intervention", "funding", "characteristics"), ("missing", "assumption", "unclear")), ("methods",)),
    PrismaRule("11", "Methods", "Study risk of bias methods and tool details", (("risk of bias", "rob", "robins", "casp", "mmat"), ("reviewer", "tool", "domain")), ("methods",)),
    PrismaRule("12", "Methods", "Effect measures for outcomes", (("effect measure", "odds ratio", "risk ratio", "mean difference", "smd"),), ("methods", "results")),
    PrismaRule("13a", "Methods", "Synthesis eligibility process", (("eligible", "eligibility"), ("synthesis", "group", "comparison")), ("methods", "results")),
    PrismaRule("13b", "Methods", "Methods to prepare data for synthesis", (("missing data", "conversion", "prepare", "imputation"),), ("methods",), "has_synthesis"),
    PrismaRule("13c", "Methods", "Tabulation and visual display methods", (("table", "tabulate", "figure", "plot", "visual"),), ("methods", "results"), "has_synthesis"),
    PrismaRule("13d", "Methods", "Statistical synthesis methods and software", (("meta-analysis", "synthesis", "model"), ("software", "statsmodels", "scipy", "method")), ("methods",), "has_synthesis"),
    PrismaRule("13e", "Methods", "Methods to explore heterogeneity", (("heterogeneity", "subgroup", "meta-regression"),), ("methods",), "has_meta"),
    PrismaRule("13f", "Methods", "Sensitivity analysis methods", (("sensitivity analysis", "leave-one-out", "robust"),), ("methods",), "has_synthesis"),
    PrismaRule("14", "Methods", "Reporting bias assessment methods", (("reporting bias", "publication bias", "small-study"), ("funnel", "asymmetry", "bias")), ("methods", "results"), "has_synthesis"),
    PrismaRule("15", "Methods", "Certainty assessment methods", (("certainty", "confidence", "grade"), ("assessment", "summary of findings")), ("methods", "results")),
    PrismaRule("16a", "Results", "Search and selection results with flow", (("identified", "screened", "included"), ("flow", "prisma")), ("results", "methods")),
    PrismaRule("16b", "Results", "Excluded studies that seemed eligible with reasons", (("excluded", "exclusion reason", "reason for exclusion"),), ("results", "other")),
    PrismaRule("17", "Results", "Characteristics of included studies", (("study characteristics", "included studies", "table"),), ("results",)),
    PrismaRule("18", "Results", "Risk of bias in studies results", (("risk of bias", "rob", "traffic light"),), ("results",)),
    PrismaRule("19", "Results", "Results of individual studies with effect estimates", (("individual studies", "effect estimate", "confidence interval", "study characteristics"),), ("results",)),
    PrismaRule("20a", "Results", "Summary of characteristics and risk of bias for each synthesis", (("synthesis",), ("risk of bias", "characteristics")), ("results",), "has_synthesis"),
    PrismaRule("20b", "Results", "Results of statistical syntheses with heterogeneity", (("summary estimate", "pooled", "meta-analysis"), ("heterogeneity", "i2", "tau")), ("results",), "has_synthesis"),
    PrismaRule("20c", "Results", "Results of heterogeneity investigations", (("subgroup", "heterogeneity", "meta-regression"), ("result", "interaction", "modifier")), ("results",), "has_meta"),
    PrismaRule("20d", "Results", "Results of sensitivity analyses", (("sensitivity", "robust"), ("result", "analysis")), ("results",), "has_synthesis"),
    PrismaRule("21", "Results", "Reporting bias assessments for syntheses", (("reporting bias", "publication bias", "funnel"),), ("results",), "has_synthesis"),
    PrismaRule("22", "Results", "Certainty of evidence for each outcome", (("certainty", "grade", "summary of findings"), ("outcome",)), ("results", "discussion")),
    PrismaRule("23a", "Discussion", "Interpretation in context of other evidence", (("interpret", "context", "other evidence", "literature"),), ("discussion",)),
    PrismaRule("23b", "Discussion", "Limitations of the evidence", (("limitation",), ("evidence", "study")), ("discussion",)),
    PrismaRule("23c", "Discussion", "Limitations of review processes", (("limitation",), ("review process", "screening process", "method")), ("discussion",)),
    PrismaRule("23d", "Discussion", "Implications for practice policy and research", (("implication", "practice", "policy", "future research"),), ("discussion",)),
    PrismaRule("24a", "Other", "Registration information", (("registration", "prospero", "crd"),), ("other", "methods", "abstract")),
    PrismaRule("24b", "Other", "Protocol accessibility statement", (("protocol",), ("available", "access", "link")), ("other", "methods")),
    PrismaRule("24c", "Other", "Amendments to protocol or registration information", (("amendment", "deviation", "updated protocol"),), ("other", "methods"), "has_registration_or_protocol"),
    PrismaRule("25", "Other", "Support and role of funders", (("funding", "support", "sponsor"), ("role", "grant", "no role")), ("other", "abstract")),
    PrismaRule("26", "Other", "Competing interests declaration", (("competing interest", "conflict of interest", "disclosure"),), ("other", "abstract")),
    PrismaRule("27", "Other", "Availability of data code and materials", (("data availability", "code availability", "materials"), ("repository", "available", "upon request")), ("other",)),
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _extract_title(md_text: str, tex_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    m = re.search(r"\\title\{([^}]*)\}", tex_text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extract_abstract(md_text: str, tex_text: str) -> str:
    lines = md_text.splitlines()
    block: list[str] = []
    in_abstract = False
    for line in lines:
        low = line.strip().lower()
        if low.startswith("## ") and in_abstract:
            break
        if low in {"## abstract", "### abstract", "**abstract**", "abstract"}:
            in_abstract = True
            continue
        if in_abstract:
            block.append(line)
    if block:
        return "\n".join(block)
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex_text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    preface: list[str] = []
    for line in lines:
        if line.startswith("## "):
            break
        preface.append(line)
    return "\n".join(preface)


def _split_markdown_sections(md_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {
        "introduction": [],
        "methods": [],
        "results": [],
        "discussion": [],
        "other": [],
    }
    current = "other"
    for line in md_text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if "intro" in heading or "background" in heading or "rationale" in heading:
                current = "introduction"
            elif "method" in heading:
                current = "methods"
            elif "result" in heading:
                current = "results"
            elif "discussion" in heading or "conclusion" in heading:
                current = "discussion"
            else:
                current = "other"
            continue
        sections[current].append(line)
    return {key: "\n".join(val) for key, val in sections.items()}


def _build_scope_text(md_text: str, tex_text: str) -> dict[str, str]:
    title = _extract_title(md_text, tex_text)
    abstract = _extract_abstract(md_text, tex_text)
    parts = _split_markdown_sections(md_text)
    scope = {
        "title": title,
        "abstract": abstract,
        "introduction": parts["introduction"],
        "methods": parts["methods"],
        "results": parts["results"],
        "discussion": parts["discussion"],
        "other": parts["other"],
    }
    scope["all"] = "\n".join(scope.values())
    return {k: _normalize_text(v) for k, v in scope.items()}


def _term_present(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    return bool(re.search(rf"\b{escaped}\b", text))


def _condition_applies(condition: str | None, flags: dict[str, bool]) -> bool:
    if condition is None:
        return True
    if condition == "has_synthesis":
        return flags["has_synthesis"]
    if condition == "has_meta":
        return flags["has_meta"]
    if condition == "has_registration_or_protocol":
        return flags["has_registration"] or flags["has_protocol"]
    return True


def _check_rule(rule: PrismaRule, scope_text: dict[str, str], flags: dict[str, bool]) -> PrismaItemResult:
    applies = _condition_applies(rule.applies_if, flags)
    item = PrismaItemResult(
        item_id=rule.item_id,
        section=rule.section,
        description=rule.description,
        status=_STATUS_MISSING,
        rationale="No evidence found",
        applies=applies,
        evidence_terms=[],
    )
    if not applies:
        item.status = _STATUS_NOT_APPLICABLE
        item.rationale = "Not applicable based on manuscript context"
        return item

    inspected = " ".join(scope_text.get(scope, "") for scope in rule.scopes)
    groups_hit = 0
    groups_with_terms: list[str] = []
    matched_terms: list[str] = []
    for group in rule.keyword_groups:
        found_term = ""
        for term in group:
            if _term_present(inspected, term):
                found_term = term
                matched_terms.append(term)
                break
        if found_term:
            groups_hit += 1
            groups_with_terms.append(found_term)

    if groups_hit == len(rule.keyword_groups):
        item.status = _STATUS_REPORTED
        item.rationale = f"Matched {groups_hit}/{len(rule.keyword_groups)} evidence groups"
    elif groups_hit > 0:
        item.status = _STATUS_PARTIAL
        item.rationale = f"Matched {groups_hit}/{len(rule.keyword_groups)} evidence groups"
    else:
        item.status = _STATUS_MISSING
        item.rationale = "No required evidence groups matched"
    item.evidence_terms = matched_terms
    return item


def _group_primary_status(items: list[PrismaItemResult]) -> tuple[int, int, int, int]:
    grouped: dict[str, list[PrismaItemResult]] = {}
    for item in items:
        primary = re.match(r"\d+", item.item_id)
        if not primary:
            continue
        grouped.setdefault(primary.group(0), []).append(item)

    reported = 0
    partial = 0
    missing = 0
    not_applicable = 0
    for _, group_items in grouped.items():
        applicable = [it for it in group_items if it.applies]
        if not applicable:
            not_applicable += 1
            continue
        statuses = {it.status for it in applicable}
        if statuses == {_STATUS_REPORTED}:
            reported += 1
        elif _STATUS_REPORTED in statuses or _STATUS_PARTIAL in statuses:
            partial += 1
        else:
            missing += 1
    return reported, partial, missing, not_applicable


def validate_prisma(tex_content: str | None, md_content: str | None = None) -> PrismaValidationResult:
    """Validate manuscript against PRISMA 2020 checklist with deterministic rules."""
    md_text = md_content or ""
    tex_text = tex_content or ""
    source_state = "artifact_missing"
    if md_text and tex_text:
        source_state = "validated_md_and_tex"
    elif md_text:
        source_state = "validated_md"
    elif tex_text:
        source_state = "validated_tex"

    scope_text = _build_scope_text(md_text, tex_text)
    all_text = scope_text["all"]
    flags = {
        "has_synthesis": any(_term_present(all_text, term) for term in ("synthesis", "narrative", "meta-analysis", "meta analysis", "pooled")),
        "has_meta": any(_term_present(all_text, term) for term in ("meta-analysis", "meta analysis", "forest plot", "i2", "tau", "random-effects", "fixed-effect")),
        "has_registration": any(_term_present(all_text, term) for term in ("prospero", "registration", "crd")),
        "has_protocol": _term_present(all_text, "protocol"),
    }
    items = [_check_rule(rule, scope_text, flags) for rule in _PRISMA_RULES]
    reported, partial, missing, not_applicable = _group_primary_status(items)
    return PrismaValidationResult(
        items=items,
        reported_count=reported,
        partial_count=partial,
        missing_count=missing,
        not_applicable_count=not_applicable,
        passed=reported >= 24,
        source_state=source_state,
    )


def render_prisma_markdown_table(result: PrismaValidationResult) -> str:
    """Render checklist as markdown supplementary artifact."""
    header = [
        "# PRISMA 2020 checklist validation",
        "",
        f"- source_state: {result.source_state}",
        f"- primary_reported: {result.reported_count}/{result.primary_total}",
        f"- primary_partial: {result.partial_count}",
        f"- primary_missing: {result.missing_count}",
        f"- primary_not_applicable: {result.not_applicable_count}",
        f"- pass_threshold_24_of_27: {'PASS' if result.passed else 'FAIL'}",
        "",
        "| Item | Section | Status | Applies | Description | Rationale | Evidence terms |",
        "|------|---------|--------|---------|-------------|-----------|----------------|",
    ]
    rows = []
    for item in result.items:
        terms = ", ".join(item.evidence_terms) if item.evidence_terms else ""
        rows.append(
            f"| {item.item_id} | {item.section} | {item.status} | {'YES' if item.applies else 'NO'} | "
            f"{item.description} | {item.rationale} | {terms} |"
        )
    return "\n".join(header + rows) + "\n"


def render_prisma_csv(result: PrismaValidationResult) -> str:
    """Render checklist as CSV supplementary artifact."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["item_id", "section", "status", "applies", "description", "rationale", "evidence_terms"])
    for item in result.items:
        writer.writerow(
            [
                item.item_id,
                item.section,
                item.status,
                "YES" if item.applies else "NO",
                item.description,
                item.rationale,
                "; ".join(item.evidence_terms),
            ]
        )
    return buf.getvalue()


def render_prisma_html(result: PrismaValidationResult) -> str:
    """Render checklist as a styled HTML supplementary artifact."""
    def _esc(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _status_class(status: str) -> str:
        if status == _STATUS_REPORTED:
            return "reported"
        if status == _STATUS_PARTIAL:
            return "partial"
        if status == _STATUS_NOT_APPLICABLE:
            return "na"
        return "missing"

    rows: list[str] = []
    for item in result.items:
        terms = ", ".join(item.evidence_terms)
        rows.append(
            "<tr>"
            f"<td>{_esc(item.item_id)}</td>"
            f"<td>{_esc(item.section)}</td>"
            f"<td><span class=\"badge {_status_class(item.status)}\">{_esc(item.status)}</span></td>"
            f"<td>{'YES' if item.applies else 'NO'}</td>"
            f"<td>{_esc(item.description)}</td>"
            f"<td>{_esc(item.rationale)}</td>"
            f"<td>{_esc(terms)}</td>"
            "</tr>"
        )

    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        "  <title>PRISMA 2020 Checklist Validation</title>\n"
        "  <style>\n"
        "    :root { color-scheme: dark; }\n"
        "    body { margin: 0; padding: 24px; background: #0b1020; color: #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }\n"
        "    h1 { margin: 0 0 12px; font-size: 22px; }\n"
        "    .summary { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 8px; margin: 12px 0 18px; }\n"
        "    .card { background: #111827; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; }\n"
        "    .label { font-size: 12px; color: #94a3b8; }\n"
        "    .value { font-size: 18px; font-weight: 700; margin-top: 4px; }\n"
        "    table { width: 100%; border-collapse: collapse; background: #0f172a; border: 1px solid #334155; }\n"
        "    th, td { border-bottom: 1px solid #1e293b; padding: 8px 10px; text-align: left; vertical-align: top; font-size: 12px; }\n"
        "    th { position: sticky; top: 0; background: #111827; z-index: 1; }\n"
        "    tr:hover td { background: #0b1225; }\n"
        "    .badge { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 700; }\n"
        "    .reported { color: #052e16; background: #4ade80; }\n"
        "    .partial { color: #422006; background: #fbbf24; }\n"
        "    .missing { color: #450a0a; background: #f87171; }\n"
        "    .na { color: #111827; background: #94a3b8; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>PRISMA 2020 Checklist Validation</h1>\n"
        f"  <p>Source state: <strong>{_esc(result.source_state)}</strong> | Primary score: <strong>{result.reported_count}/{result.primary_total}</strong> | Pass: <strong>{'PASS' if result.passed else 'FAIL'}</strong></p>\n"
        "  <div class=\"summary\">\n"
        f"    <div class=\"card\"><div class=\"label\">Reported</div><div class=\"value\">{result.reported_count}</div></div>\n"
        f"    <div class=\"card\"><div class=\"label\">Partial</div><div class=\"value\">{result.partial_count}</div></div>\n"
        f"    <div class=\"card\"><div class=\"label\">Missing</div><div class=\"value\">{result.missing_count}</div></div>\n"
        f"    <div class=\"card\"><div class=\"label\">Not applicable</div><div class=\"value\">{result.not_applicable_count}</div></div>\n"
        f"    <div class=\"card\"><div class=\"label\">Item rows</div><div class=\"value\">{len(result.items)}</div></div>\n"
        f"    <div class=\"card\"><div class=\"label\">Threshold</div><div class=\"value\">24/27</div></div>\n"
        "  </div>\n"
        "  <table>\n"
        "    <thead><tr><th>Item</th><th>Section</th><th>Status</th><th>Applies</th><th>Description</th><th>Rationale</th><th>Evidence terms</th></tr></thead>\n"
        f"    <tbody>{''.join(rows)}</tbody>\n"
        "  </table>\n"
        "</body>\n"
        "</html>\n"
    )
