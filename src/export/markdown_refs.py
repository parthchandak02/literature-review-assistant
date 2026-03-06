"""Append Figures, Declarations, Study Table, and References to a Markdown manuscript."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.quality.grade import build_sof_table, sof_table_to_markdown

logger = logging.getLogger(__name__)


def _normalize_doi(doi: str | None) -> str:
    """Normalize DOI to https://doi.org/ URL format.

    Handles bare DOIs (10.X...), doi.org URLs (with or without https://),
    and already-normalized URLs. Returns empty string for None or empty input.
    """
    if not doi:
        return ""
    doi = doi.strip()
    if not doi:
        return ""
    # Already a full URL
    if doi.lower().startswith("https://doi.org/") or doi.lower().startswith("http://doi.org/"):
        return f"https://doi.org/{doi.split('doi.org/', 1)[-1]}"
    # doi.org URL without scheme
    if doi.lower().startswith("doi.org/"):
        return f"https://{doi}"
    # doi: prefix (e.g. "doi:10.1000/xyz")
    if doi.lower().startswith("doi:"):
        return f"https://doi.org/{doi[4:].lstrip('/')}"
    # Bare DOI (starts with 10.)
    if doi.startswith("10."):
        return f"https://doi.org/{doi}"
    # Unknown format -- return as-is
    return doi


def _capitalize_name_part(name: str) -> str:
    """Capitalize each word in a name part, preserving hyphenated names.

    Examples:
      'han-na' -> 'Han-na'
      'k lynette' -> 'K. Lynette'  (initial without period)
      'mcdonald' -> 'McDonald' (naive; full de/van/von handling not implemented)
    """
    if not name:
        return name
    # Handle hyphenated names: capitalize each segment
    segments = name.split("-")
    capitalized = []
    for seg in segments:
        # Capitalize first char only; preserve rest (e.g. "na" stays "na" not "Na")
        capitalized.append(seg[0].upper() + seg[1:] if seg else seg)
    return "-".join(capitalized)


def _fmt_author_str(raw: str) -> str:
    """Capitalize and lightly normalize a raw author string (Last, F. format)."""
    if not raw:
        return raw
    # If already looks properly formatted (capital start), return as-is
    if raw[0].isupper():
        return raw
    # Otherwise try to capitalize the name parts
    # Common format: "last, F." or "last first" or just "last"
    if "," in raw:
        parts = raw.split(",", 1)
        last = _capitalize_name_part(parts[0].strip())
        rest = parts[1].strip()
        # Capitalize initials in rest (e.g. "k." -> "K.")
        rest_parts = rest.split()
        rest_fixed = " ".join(p[0].upper() + p[1:] if p else p for p in rest_parts)
        return f"{last}, {rest_fixed}" if rest_fixed else last
    # No comma - try capitalizing all words
    words = raw.split()
    return " ".join(_capitalize_name_part(w) for w in words)


def _fmt_authors(authors_json: str) -> str:
    """Return 'Last, F. and Last, F. et al.' from authors JSON.

    Author names are capitalized to correct for sources that store them
    in lowercase (e.g. 'han-na Cho' -> 'Han-na Cho').
    """
    try:
        authors = json.loads(authors_json)
    except Exception:
        return "Unknown"
    if not isinstance(authors, list) or not authors:
        return "Unknown"
    parts: list[str] = []
    for a in authors:
        if isinstance(a, str):
            parts.append(_fmt_author_str(a))
        elif isinstance(a, dict):
            last = a.get("last", a.get("family", ""))
            first = a.get("first", a.get("given", ""))
            # Capitalize last name and first initial
            last = _capitalize_name_part(last) if last else ""
            initial = ""
            if first:
                first_fixed = _capitalize_name_part(first.split()[0]) if first.split() else first
                initial = first_fixed[0] + "."
            formatted = f"{last}, {initial}".strip(", ") if last else initial
            if formatted:
                parts.append(formatted)
    if not parts:
        return "Unknown"
    if len(parts) > 3:
        return " and ".join(parts[:3]) + " et al."
    return " and ".join(parts)


def extract_citekeys_in_order(text: str) -> list[str]:
    """Return unique citekeys in order of first appearance in text.

    Handles both single [Smith2023] and multi-key [Smith2023, Jones2024] or
    [Smith2023; Jones2024] citation groups, splitting on commas and semicolons
    and validating each token.
    """
    seen: set[str] = set()
    keys: list[str] = []
    _valid_key = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")
    for bracket_content in re.findall(r"\[([^\]]+)\]", text):
        # Split on both commas and semicolons to handle both citation styles
        for part in re.split(r"[,;]", bracket_content):
            key = part.strip()
            if _valid_key.match(key) and key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _sanitize_body(text: str) -> str:
    """Remove LLM-generated text artifacts from the assembled body.

    Strips:
    - Lines that are purely orphaned citation fragments starting with a comma
      (e.g. ', Katharina2025, Importancend].' with no preceding prose)
    - Lines that consist only of bracketed citekey lists with no prose

    Also normalizes reviewer wording: replaces 'human reviewer' or 'AI reviewer'
    with 'reviewer' (and plural forms) to keep neutral language.
    """
    # Normalize reviewer wording: use neutral 'reviewer(s)' only (no human/AI)
    text = re.sub(r"\bhuman\s+reviewers\b", "reviewers", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhuman\s+reviewer\b", "reviewer", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAI\s+reviewers\b", "reviewers", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAI\s+reviewer\b", "reviewer", text, flags=re.IGNORECASE)

    lines = text.split("\n")
    clean: list[str] = []
    # Orphaned fragment: line starts with optional whitespace then a comma then citekey tokens
    orphan_re = re.compile(r"^\s*,\s*[A-Za-z][A-Za-z0-9_:-]*")
    # Pure citekey line: entire line is one or more [Citekey] groups with no prose
    pure_cite_re = re.compile(r"^\s*(\[[A-Za-z][A-Za-z0-9_:-]*\]\s*[,;]?\s*)+\s*$")
    for line in lines:
        if orphan_re.match(line):
            continue
        if pure_cite_re.match(line) and line.strip():
            continue
        clean.append(line)
    return "\n".join(clean)


def convert_to_numbered_citations(
    body: str,
    citation_rows: list[tuple],
) -> tuple[str, list[tuple]]:
    """Replace [AuthorYear] citekeys in body with [N] sequential numbers.

    Handles both single [Smith2023] and multi-key [Smith2023, Jones2024] groups.
    Multi-key groups are replaced with comma-separated numbers: [1], [2].
    Returns (new_body, ordered_rows) where ordered_rows lists citation_rows
    in order of first appearance.  Unknown keys are left unchanged.
    """
    citekey_map: dict[str, tuple] = {row[1]: row for row in citation_rows}
    ordered_keys = extract_citekeys_in_order(body)
    key_to_number: dict[str, int] = {}
    ordered_rows: list[tuple] = []
    n = 1
    for key in ordered_keys:
        if key in citekey_map and key not in key_to_number:
            key_to_number[key] = n
            ordered_rows.append(citekey_map[key])
            n += 1

    _valid_key = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")

    def _replacer(match: re.Match) -> str:  # type: ignore[type-arg]
        bracket_content = match.group(1)
        # Split on both commas and semicolons to handle [Smith2023; Jones2024] style
        parts = [p.strip() for p in re.split(r"[,;]", bracket_content)]
        valid_parts = [p for p in parts if _valid_key.match(p)]
        if not valid_parts:
            return match.group(0)
        nums = [key_to_number[p] for p in valid_parts if p in key_to_number]
        if not nums:
            return match.group(0)
        return ", ".join(f"[{num}]" for num in nums)

    # Match bracket groups that contain citekey-like content (letters, commas, semicolons, spaces)
    new_body = re.sub(r"\[([A-Za-z][A-Za-z0-9_,; :-]*)\]", _replacer, body)
    return new_body, ordered_rows


# Figure definitions: ordered list of (artifact_key, caption).
# Numbers are NOT stored here -- they are assigned dynamically at render time
# by counting only figures whose artifact file actually exists on disk.
# This prevents gaps (e.g. Fig 1, 2, 4, 5) when optional figures like
# rob2_traffic_light or forest plots are absent.
FIGURE_DEFS: list[tuple[str, str]] = [
    (
        "prisma_diagram",
        "PRISMA 2020 flow diagram showing the study selection process.",
    ),
    (
        "rob_traffic_light",
        "Risk of bias traffic-light plot for included non-randomized studies and reviews (ROBINS-I/CASP).",
    ),
    (
        "rob2_traffic_light",
        "Risk of bias assessment using the Cochrane RoB 2 tool for the included randomized controlled trial.",
    ),
    (
        "fig_forest_plot",
        "Forest plot of pooled effect sizes for feasible meta-analysis outcomes.",
    ),
    (
        "fig_funnel_plot",
        "Funnel plot assessing publication bias for meta-analysis outcomes.",
    ),
    (
        "timeline",
        "Publication timeline of included studies.",
    ),
    (
        "geographic",
        "Geographic distribution of included studies by country of origin (or source database when country data is unavailable).",
    ),
    (
        "concept_taxonomy",
        "Conceptual taxonomy of key constructs identified across included studies.",
    ),
    (
        "conceptual_framework",
        "Conceptual framework derived from synthesis of included studies.",
    ),
    (
        "methodology_flow",
        "Systematic review methodology flow diagram.",
    ),
    (
        "evidence_network",
        "Evidence network of co-citation relationships among included studies.",
    ),
]


def build_markdown_figures_section(
    manuscript_path: Path,
    artifacts: dict[str, str],
) -> str:
    """Build a Figures section with relative-path image embeds and IEEE captions.

    Only includes figures whose artifact file actually exists on disk.
    Figure numbers are assigned sequentially (1, 2, 3, ...) based on which
    figures are present, preventing gaps in numbering when optional figures
    (e.g. RoB 2 traffic light, forest plot) are absent.
    Returns an empty string if no figures are available.
    """
    lines: list[str] = ["## Figures", ""]
    seq = 1
    for artifact_key, caption in FIGURE_DEFS:
        fig_path_str = artifacts.get(artifact_key, "")
        if not fig_path_str:
            continue
        fig_path = Path(fig_path_str)
        if not fig_path.exists():
            continue
        # Use caption sidecar file when present (allows visualization code to
        # override the default caption -- e.g. geographic falls back to source
        # database distribution when country data is unavailable).
        caption_sidecar = fig_path.with_suffix(".caption")
        if caption_sidecar.exists():
            try:
                caption = caption_sidecar.read_text(encoding="utf-8").strip() or caption
            except Exception:
                pass
        # Compute relative path from manuscript file to figure (they are siblings).
        try:
            rel = fig_path.relative_to(manuscript_path.parent)
        except ValueError:
            rel = fig_path  # type: ignore[assignment]
        lines.append(f"**Fig. {seq}.** {caption}")
        lines.append("")
        lines.append(f"![Fig. {seq}: {caption}]({rel})")
        lines.append("")
        seq += 1
    if seq == 1:
        return ""
    return "\n".join(lines)


def build_credit_section(author_name: str = "") -> str:
    """Build a CRediT (Contributor Roles Taxonomy) author contributions section.

    CRediT is required by most Elsevier, Wiley, and MDPI journals.
    For a tool-assisted systematic review the standard attribution separates
    the human author's conceptual/editorial role from the automated pipeline's
    drafting role.
    """
    author = author_name.strip() if author_name.strip() else "[Author name]"
    return (
        "## CRediT Author Contribution Statement\n\n"
        f"**{author}:** Conceptualization; Methodology; Software; "
        "Formal analysis; Writing -- review and editing; Supervision; "
        "Project administration.\n\n"
        "**Automated pipeline:** Data curation; Investigation; "
        "Writing -- original draft.\n\n"
        "_Note: This review was produced with the assistance of an automated "
        "systematic review pipeline. All results were reviewed and approved "
        "by the named author._"
    )


def build_markdown_declarations_section(
    funding: str = "",
    coi: str = "",
    protocol_registered: bool = False,
    registration_id: str = "",
    author_name: str = "",
) -> str:
    """Build a Declarations section with funding, COI, data availability, registration, and CRediT."""
    funding_text = funding or "No funding was received for this review."
    coi_text = coi or "The authors declare no conflicts of interest."
    if protocol_registered and registration_id:
        reg_text = f"The protocol was prospectively registered (ID: {registration_id})."
    else:
        reg_text = (
            "Protocol registration pending. To register, visit "
            "https://www.crd.york.ac.uk/prospero/ and add the registration number "
            "to review.yaml under protocol.registration_number before submission."
        )
    credit = build_credit_section(author_name)
    return (
        "## Declarations\n\n"
        f"**Funding:** {funding_text}\n\n"
        f"**Conflicts of Interest:** {coi_text}\n\n"
        "**Data Availability:** All data used in this review are available from "
        "the public databases searched. The extracted data supporting the findings "
        "are available from the corresponding author upon reasonable request.\n\n"
        f"**Protocol Registration:** {reg_text}\n\n"
        f"{credit}"
    )


_PLACEHOLDER_OUTCOME_NAMES = {"", "primary_outcome", "not reported", "not_reported"}
_RAW_SETTING_NORMALIZE = {
    "not_reported": "NR",
    "not reported": "NR",
    "not applicable": "NR",
    "n/a": "NR",
    "na": "NR",
    "unknown": "NR",
}


def is_extraction_failed(rec: Any) -> bool:
    """Return True when LLM extraction produced only placeholder/empty data.

    A record is considered failed when ALL three quality signals are absent:
    - all outcome names are placeholders ("primary_outcome", "not reported", empty)
    - study_design is "other" or unset (LLM defaulted)
    - participant_count is None (could not parse a number)

    Use this to exclude such records from the manuscript and study table so
    the final document contains only papers with meaningful extracted data.
    """
    outcome_names = {o.name.strip().lower() for o in (rec.outcomes or [])}
    all_placeholder = outcome_names.issubset(_PLACEHOLDER_OUTCOME_NAMES)
    design_obj = getattr(rec, "study_design", "other")
    if hasattr(design_obj, "value"):
        design_raw = design_obj.value.lower()
    else:
        design_raw = str(design_obj or "other").lower()
    design_is_other = design_raw in ("other", "")
    # Treat None and 0 the same: 0 participants is not a meaningful count.
    no_participant_count = not rec.participant_count
    return all_placeholder and design_is_other and no_participant_count


def build_study_characteristics_table(
    papers: list[Any],
    extraction_records: list[Any],
    pre_filtered_count: int = 0,
) -> str:
    """Build a GFM markdown table of included study characteristics.

    Joins CandidatePaper (author, year, country) with ExtractionRecord
    (study_design, participant_count, setting, outcomes) by paper_id.
    Excludes papers whose extraction completely failed (all placeholder data).
    Returns an empty string if no usable data is available.

    pre_filtered_count: number of extraction records already excluded by the
    caller before passing this list. Added to the footnote so the total
    omission count is accurate even when the caller pre-filters.
    """
    paper_map: dict[str, Any] = {p.paper_id: p for p in papers}
    extraction_map: dict[str, Any] = {r.paper_id: r for r in extraction_records}

    rows: list[dict[str, str]] = []
    excluded_count = pre_filtered_count
    for paper_id, paper in paper_map.items():
        rec = extraction_map.get(paper_id)
        if rec is None:
            continue

        if is_extraction_failed(rec):
            excluded_count += 1
            continue

        # Author(s), Year
        if paper.authors:
            first_author_raw = str(paper.authors[0])
            first_author = first_author_raw.split()[-1] if first_author_raw.split() else first_author_raw
            author_str = f"{first_author} et al." if len(paper.authors) > 1 else first_author_raw
        else:
            author_str = "NR"
        year_str = str(paper.year) if paper.year else "n.d."
        author_year = f"{author_str}, {year_str}"

        # Study design - show "NR" for uninformative "Other"
        design_val = rec.study_design
        if hasattr(design_val, "value"):
            design_raw = design_val.value
        else:
            design_raw = str(design_val or "")
        design_str = design_raw.replace("_", " ").title()
        if design_str.lower() in ("other", ""):
            design_str = "NR"

        # Sample size
        n_str = str(rec.participant_count) if rec.participant_count else "NR"

        # Country
        country_str = paper.country or "NR"

        # Setting - normalize raw enum-like values to NR
        raw_setting = (rec.setting or "").strip()
        setting_str = _RAW_SETTING_NORMALIZE.get(raw_setting.lower(), raw_setting) or "NR"

        # Key outcomes - take first two real (non-placeholder) outcome names
        _HTML_BOILERPLATE_MARKERS = (
            "html boilerplate",
            "metadata",
            "text excerpt",
            "javascript",
            "<!doctype",
            "<html",
        )
        real_names = [
            o.name.strip() for o in (rec.outcomes or [])[:3] if o.name.strip().lower() not in _PLACEHOLDER_OUTCOME_NAMES
        ]
        if real_names:
            outcomes_str = "; ".join(real_names[:2])
        else:
            # Fall back to results_summary["summary"] truncated to 80 chars
            summary = ""
            if isinstance(rec.results_summary, dict):
                summary = rec.results_summary.get("summary", "")
            elif isinstance(rec.results_summary, str):
                summary = rec.results_summary
            # Guard: if the summary looks like HTML boilerplate or LLM error text,
            # replace with "NR" rather than leaking extraction artifacts into the table.
            summary_lower = summary.lower()
            if any(marker in summary_lower for marker in _HTML_BOILERPLATE_MARKERS):
                outcomes_str = "NR"
                logger.warning(
                    "HTML/boilerplate detected in results_summary for paper %s; Key Outcomes set to NR.",
                    paper_id,
                )
            else:
                outcomes_str = summary[:80].rstrip() + "..." if len(summary) > 80 else summary or "NR"

        # Full text retrieved: Yes when extraction_source is not "text" (abstract-only)
        extraction_source = getattr(rec, "extraction_source", None) or "text"
        full_text_retrieved = "Yes" if extraction_source != "text" else "No"

        rows.append(
            {
                "author_year": author_year,
                "design": design_str,
                "n": n_str,
                "country": country_str,
                "setting": setting_str,
                "outcomes": outcomes_str,
                "full_text_retrieved": full_text_retrieved,
            }
        )

    if not rows:
        return ""

    rows.sort(key=lambda r: r["author_year"])

    header = "| Author(s), Year | Study Design | Sample Size | Country | Setting | Full Text Retrieved | Key Outcomes |"
    sep = "|----------------|------------|------------|-------|----------------------------|---------------------|------------------------------------|"
    data_rows = [
        f"| {r['author_year']} | {r['design']} | {r['n']} | {r['country']} | {r['setting']} | {r['full_text_retrieved']} | {r['outcomes']} |"
        for r in rows
    ]

    total_records = len(rows) + excluded_count
    footnote = (
        "_NR = Not Reported; n.d. = no publication date available. "
        "Full Text Retrieved: Yes = full-text PDF was retrieved and used for data extraction; "
        "No = extraction used abstract and extended metadata only (no full-text PDF obtained)._"
    )
    if excluded_count:
        footnote += (
            f" _{excluded_count} of {total_records} included studies omitted from "
            f"this table: automated data extraction produced only placeholder values "
            f"(study design unresolved, no quantitative outcome data, participant count "
            f"not reported). These studies are cited in the narrative synthesis above._"
        )
    table_md = "\n".join([header, sep] + data_rows) + "\n\n" + footnote
    return "## Appendix B: Characteristics of Included Studies\n\n" + table_md


_ROBINS_I_DOMAINS = [
    ("D1", "domain_1_confounding", "Confounding"),
    ("D2", "domain_2_selection", "Selection"),
    ("D3", "domain_3_classification", "Classification"),
    ("D4", "domain_4_deviations", "Deviations"),
    ("D5", "domain_5_missing_data", "Missing data"),
    ("D6", "domain_6_measurement", "Measurement"),
    ("D7", "domain_7_reported_result", "Reported result"),
]


def _robins_judgment_display(value: Any) -> str:
    """Format RobinsIJudgment for table display (Low, Moderate, Serious, etc.)."""
    if value is None:
        return "NR"
    raw = getattr(value, "value", None) or str(value)
    return raw.replace("_", " ").title()


def _paper_author_year(paper: Any) -> str:
    """Return 'Author et al., Year' for a paper."""
    if paper.authors:
        first_author_raw = str(paper.authors[0])
        first_author = first_author_raw.split()[-1] if first_author_raw.split() else first_author_raw
        author_str = f"{first_author} et al." if len(paper.authors) > 1 else first_author_raw
    else:
        author_str = "NR"
    year_str = str(paper.year) if paper.year else "n.d."
    return f"{author_str}, {year_str}"


def build_robins_i_domain_table(
    papers: list[Any],
    robins_i_assessments: list[Any],
) -> str:
    """Build a markdown table of ROBINS-I bias assessment (7 domains per study).

    Similar to Jeffrey et al. (2024) Table 3. One row per study; columns for
    D1-D7 and Overall. Returns empty string if no ROBINS-I assessments.
    """
    if not robins_i_assessments:
        return ""

    paper_map: dict[str, Any] = {p.paper_id: p for p in papers}
    # Build rows: (author_year, assessment) sorted by author_year
    rows_data: list[tuple[str, Any]] = []
    for a in robins_i_assessments:
        paper = paper_map.get(a.paper_id)
        label = _paper_author_year(paper) if paper else a.paper_id[:12]
        rows_data.append((label, a))
    rows_data.sort(key=lambda x: x[0])

    domain_cols = [f"{short} ({name})" for short, attr, name in _ROBINS_I_DOMAINS]
    header = "| Study | " + " | ".join(domain_cols) + " | Overall |"
    sep = "|" + "|".join(["-------"] * (len(_ROBINS_I_DOMAINS) + 2)) + "|"

    data_rows: list[str] = []
    for label, a in rows_data:
        cells = [label]
        for _short, attr, _name in _ROBINS_I_DOMAINS:
            val = getattr(a, attr, None)
            cells.append(_robins_judgment_display(val))
        cells.append(_robins_judgment_display(getattr(a, "overall_judgment", None)))
        data_rows.append("| " + " | ".join(cells) + " |")

    footnote = (
        "_ROBINS-I domains: D1 Confounding, D2 Selection of participants, "
        "D3 Classification of interventions, D4 Deviations from interventions, "
        "D5 Missing data, D6 Measurement of outcomes, D7 Selection of reported result. "
        "Judgments: Low, Moderate, Serious, Critical, No Information._"
    )
    table_md = "\n".join([header, sep] + data_rows) + "\n\n" + footnote
    return "## ROBINS-I Risk of Bias Assessment\n\n" + table_md


def build_picos_table(review_config: Any) -> str:
    """Build a markdown table of eligibility criteria (PICOS) from review config.

    Similar to benchmark Table 1: Inclusion/exclusion criteria (PICOS).
    Uses PICO elements plus inclusion and exclusion criteria from review.yaml.
    """
    pico = getattr(review_config, "pico", None)
    if not pico:
        return ""

    inclusion = getattr(review_config, "inclusion_criteria", []) or []
    exclusion = getattr(review_config, "exclusion_criteria", []) or []
    inc_str = "; ".join(str(c) for c in inclusion) if inclusion else "NR"
    exc_str = "; ".join(str(c) for c in exclusion) if exclusion else "NR"

    # Study design row: derive from review_type and any explicit study_design field
    review_type = getattr(review_config, "review_type", "") or ""
    study_design_val = getattr(pico, "study_design", None) or getattr(pico, "study_designs", None) or ""
    if not study_design_val:
        if review_type.lower() == "rct" or review_type.lower() == "randomized":
            study_design_val = "Randomized controlled trials (RCTs)"
        elif review_type.lower() in ("systematic", "sr"):
            study_design_val = (
                "Non-randomized studies of interventions, cohort studies, cross-sectional studies, "
                "and observational or usability study designs"
            )
        else:
            study_design_val = "All study designs considered"

    rows = [
        ("Population", getattr(pico, "population", "") or "NR"),
        ("Intervention", getattr(pico, "intervention", "") or "NR"),
        ("Comparison", getattr(pico, "comparison", "") or "NR"),
        ("Outcome", getattr(pico, "outcome", "") or "NR"),
        ("Study design", study_design_val),
        ("Inclusion criteria", inc_str),
        ("Exclusion criteria", exc_str),
    ]
    header = "| Element | Description |"
    sep = "|---------|-------------|"
    data_rows = [f"| {label} | {_escape_table_cell(desc)} |" for label, desc in rows]
    footnote = (
        "_PICOS = Population, Intervention, Comparison, Outcome, Study design. Eligibility criteria from protocol._"
    )
    table_md = "\n".join([header, sep] + data_rows) + "\n\n" + footnote
    return "## Appendix A: Eligibility Criteria (PICOS)\n\n" + table_md


def _escape_table_cell(text: str) -> str:
    """Escape pipe characters in table cell to avoid breaking markdown."""
    return text.replace("|", "\\|").replace("\n", " ")


_CERTAINTY_ORDER = {"high": 0, "moderate": 1, "low": 2, "very_low": 3}


def generate_grade_table(grade_assessments: list[Any]) -> str:
    """Generate a GRADE evidence profile table in Markdown from a list of GRADEOutcomeAssessment objects.

    Assessments are grouped by outcome_name. Per group we report the count of
    studies, the most common study design, the maximum downgrade values, and
    the most conservative certainty (worst-case per group).

    Returns an empty string when no assessments are provided.
    """
    if not grade_assessments:
        return ""

    # Group assessments by outcome_name, skipping placeholder/generic labels.
    # Per GRADE methodology, outcomes without usable named data are excluded
    # from the evidence profile (they add noise without contributing evidence).
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for g in grade_assessments:
        raw_name = (getattr(g, "outcome_name", None) or "").strip()
        # Normalize for placeholder check: lowercase, collapse underscores/spaces
        name_norm = raw_name.lower().replace(" ", "_")
        if name_norm in _PLACEHOLDER_OUTCOME_NAMES:
            continue
        outcome = raw_name.replace("_", " ").title() if raw_name else None
        if not outcome:
            continue
        groups[outcome].append(g)

    rows: list[str] = []
    header = (
        "| Outcome | Studies (N) | Study Design | Max RoB Downgrade | "
        "Max Imprecision Downgrade | Certainty (worst case) |"
    )
    sep = (
        "|---------|------------|-------------|------------------|--------------------------|------------------------|"
    )
    rows.append(header)
    rows.append(sep)

    for outcome, group in sorted(groups.items()):
        n_studies = len(group)

        # Collect designs -- most frequent
        designs: dict = {}
        for g in group:
            d = str(getattr(g, "study_designs", "") or "").strip()
            if d:
                designs[d] = designs.get(d, 0) + 1
        design_str = max(designs, key=designs.get) if designs else "NR"

        max_rob = max((getattr(g, "risk_of_bias_downgrade", 0) or 0) for g in group)
        max_imp = max((getattr(g, "imprecision_downgrade", 0) or 0) for g in group)

        # Most conservative certainty
        worst_order = -1
        worst_cert = "NR"
        for g in group:
            cr = getattr(g, "final_certainty", None)
            cert_val = cr.value if hasattr(cr, "value") else str(cr or "")
            order = _CERTAINTY_ORDER.get(cert_val.lower(), -1)
            if order > worst_order:
                worst_order = order
                worst_cert = cert_val.replace("_", " ").upper()

        rows.append(f"| {outcome} | {n_studies} | {design_str} | {max_rob} | {max_imp} | {worst_cert} |")

    footnote = (
        "_GRADE certainty levels: HIGH, MODERATE, LOW, VERY LOW. "
        "Downgrade values: 0=not downgraded, 1=serious, 2=very serious. "
        "Inconsistency, indirectness, and publication-bias domains were not auto-computed and default to 0. "
        "Outcomes without a reported name are excluded from this profile per GRADE methodology._"
    )
    return "## GRADE Evidence Profile\n\n" + "\n".join(rows) + "\n\n" + footnote


def build_markdown_references_section(
    manuscript_text: str,
    citation_rows: list[tuple],
    numbered: bool = True,
) -> str:
    """Build a References section for citekeys used in the manuscript body.

    When numbered=True (default), citation_rows must already be ordered by
    convert_to_numbered_citations(); entries are formatted [N] Authors, ...

    When numbered=False, uses author-year citekeys in order of first appearance.

    Entries with no author, no DOI, and no year are omitted with a footer note.
    Returns an empty string if no citations are found.
    """
    entries: list[str] = []
    omitted: list[str] = []

    if numbered:
        for idx, row in enumerate(citation_rows, start=1):
            _cid, citekey, doi, title, authors_json, year, journal, _bibtex = row
            authors = _fmt_authors(authors_json)
            year_str = str(year) if year else "n.d."
            if authors == "Unknown" and not doi and not year:
                omitted.append(citekey)
                continue
            entry = f'[{idx}] {authors}, "{title},"'
            if journal:
                entry += f" *{journal}*,"
            entry += f" {year_str}."
            doi_url = _normalize_doi(doi)
            if doi_url:
                entry += f" doi: {doi_url}"
            entries.append(entry)
    else:
        citekey_map: dict[str, tuple] = {row[1]: row for row in citation_rows}
        ordered_keys = extract_citekeys_in_order(manuscript_text)
        for key in ordered_keys:
            row = citekey_map.get(key)
            if not row:
                continue
            _cid, citekey, doi, title, authors_json, year, journal, _bibtex = row
            authors = _fmt_authors(authors_json)
            year_str = str(year) if year else "n.d."
            if authors == "Unknown" and not doi and not year:
                omitted.append(citekey)
                continue
            entry = f'[{citekey}] {authors}, "{title},"'
            if journal:
                entry += f" *{journal}*,"
            entry += f" {year_str}."
            doi_url = _normalize_doi(doi)
            if doi_url:
                entry += f" doi: {doi_url}"
            entries.append(entry)

    if not entries:
        return ""

    section = "## References\n\n" + "\n\n".join(entries)
    if omitted:
        section += (
            "\n\n*Note: " + str(len(omitted)) + " citation(s) omitted from this list due to incomplete metadata "
            "(no author, DOI, or year recovered from source).*"
        )
    return section


def assemble_submission_manuscript(
    body: str,
    manuscript_path: Path,
    artifacts: dict[str, str],
    citation_rows: list[tuple],
    papers: list[Any] | None = None,
    extraction_records: list[Any] | None = None,
    funding: str = "",
    coi: str = "",
    grade_assessments: list[Any] | None = None,
    robins_i_assessments: list[Any] | None = None,
    review_config: Any | None = None,
    failed_count: int = 0,
    search_appendix_path: Path | None = None,
    research_question: str = "",
    title: str | None = None,
) -> str:
    """Combine all manuscript sections with HR separators.

    Assembly order:
      [Title + Research Question block if provided] -> body -> Declarations ->
      Eligibility Criteria (PICOS) -> GRADE Evidence Profile -> GRADE SoF Table ->
      ROBINS-I domain table -> Study Table -> Figures -> References ->
      Search Strategies Appendix

    The body is sanitized to remove LLM text artifacts and author-year
    citation keys are converted to sequential [N] numbered format.

    failed_count: number of extraction records already excluded by the caller
    (e.g. pre-filtered with is_extraction_failed) before passing extraction_records.
    Forwarded to build_study_characteristics_table so the omission footnote is accurate.

    search_appendix_path: optional path to doc_search_strategies_appendix.md written
    by SearchStrategyCoordinator in Phase 2. When present it is appended as Appendix B.

    research_question: from review.yaml; prepended at top with title when provided.
    title: optional manuscript title; if None and research_question given, derived as
    "A Systematic Review: " + research_question (full text, no truncation).
    """
    clean_body = _sanitize_body(body)

    # Convert [AuthorYear] -> [N] numbered citations
    numbered_body, ordered_citation_rows = convert_to_numbered_citations(clean_body, citation_rows)

    # Prepend title and research question block when provided
    header_block = ""
    if research_question or title:
        # Strip any existing title block to avoid duplication when re-running finalize
        _title_block_re = re.compile(
            r"^# .+?\n\n\*\*Research Question:\*\* .+?\n\n---\n\n",
            re.DOTALL,
        )
        numbered_body = _title_block_re.sub("", numbered_body)

        _title = title
        if _title is None and research_question:
            _title = f"A Systematic Review: {research_question}"
        if _title:
            header_block = f"# {_title}\n\n"
        if research_question:
            header_block += f"**Research Question:** {research_question}\n\n---\n\n"
        if header_block:
            numbered_body = header_block + numbered_body

    _protocol_registered = False
    _registration_id = ""
    if review_config is not None and hasattr(review_config, "protocol"):
        _proto = review_config.protocol
        _protocol_registered = bool(getattr(_proto, "registered", False))
        _registration_id = str(getattr(_proto, "registration_number", "") or "")
    declarations_section = build_markdown_declarations_section(
        funding=funding,
        coi=coi,
        protocol_registered=_protocol_registered,
        registration_id=_registration_id,
    )

    picos_section = ""
    if review_config:
        picos_section = build_picos_table(review_config)

    grade_section = ""
    sof_section = ""
    if grade_assessments:
        grade_section = generate_grade_table(grade_assessments)
        # Full GRADE Summary of Findings table (with RoB/inconsistency breakdown)
        # appended after the simplified Evidence Profile
        sof_table = build_sof_table(grade_assessments)
        sof_section = sof_table_to_markdown(sof_table)

    robins_section = ""
    if papers and robins_i_assessments:
        robins_section = build_robins_i_domain_table(papers, robins_i_assessments)

    study_table_section = ""
    if papers and extraction_records:
        study_table_section = build_study_characteristics_table(
            papers, extraction_records, pre_filtered_count=failed_count
        )

    figures_section = build_markdown_figures_section(manuscript_path, artifacts)

    refs_section = build_markdown_references_section(numbered_body, ordered_citation_rows, numbered=True)

    search_appendix_section = ""
    if search_appendix_path and search_appendix_path.exists():
        raw = search_appendix_path.read_text(encoding="utf-8").strip()
        # Normalize the top-level heading to fit as an appendix
        raw = raw.replace(
            "# Search Strategies Appendix",
            "## Appendix C: Search Strategies",
        )
        search_appendix_section = raw

    parts = [numbered_body]
    if declarations_section:
        parts.append(declarations_section)
    if picos_section:
        parts.append(picos_section)
    if grade_section:
        parts.append(grade_section)
    if sof_section:
        parts.append(sof_section)
    if robins_section:
        parts.append(robins_section)
    if study_table_section:
        parts.append(study_table_section)
    if figures_section:
        parts.append(figures_section)
    if refs_section:
        parts.append(refs_section)
    if search_appendix_section:
        parts.append(search_appendix_section)

    return "\n\n---\n\n".join(parts)


def strip_appended_sections(text: str) -> str:
    """Remove previously appended sections (idempotent helper for re-runs)."""
    for marker in (
        "\n\n---\n\n## Declarations",
        "\n\n## Declarations",
        "\n\n---\n\n## GRADE Evidence Profile",
        "\n\n## GRADE Evidence Profile",
        "\n\n---\n\n## Appendix A: Eligibility Criteria",
        "\n\n## Appendix A: Eligibility Criteria",
        "\n\n---\n\n## ROBINS-I Risk of Bias Assessment",
        "\n\n## ROBINS-I Risk of Bias Assessment",
        "\n\n---\n\n## Appendix B",
        "\n\n## Appendix B",
        "\n\n---\n\n## Figures",
        "\n\n## Figures",
        "\n\n---\n\n## References",
        "\n\n## References",
    ):
        if marker in text:
            return text.split(marker)[0]
    return text
