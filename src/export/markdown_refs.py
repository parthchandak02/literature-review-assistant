"""Append Figures, Declarations, Study Table, and References to a Markdown manuscript."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _fmt_authors(authors_json: str) -> str:
    """Return 'Last, F. and Last, F. et al.' from authors JSON."""
    try:
        authors = json.loads(authors_json)
    except Exception:
        return "Unknown"
    if not isinstance(authors, list) or not authors:
        return "Unknown"
    parts: List[str] = []
    for a in authors:
        if isinstance(a, str):
            parts.append(a)
        elif isinstance(a, dict):
            last = a.get("last", a.get("family", ""))
            first = a.get("first", a.get("given", ""))
            initial = (first[0] + ".") if first else ""
            formatted = f"{last}, {initial}".strip(", ") if last else initial
            if formatted:
                parts.append(formatted)
    if not parts:
        return "Unknown"
    if len(parts) > 3:
        return " and ".join(parts[:3]) + " et al."
    return " and ".join(parts)


def extract_citekeys_in_order(text: str) -> List[str]:
    """Return unique citekeys in order of first appearance in text.

    Handles both single [Smith2023] and multi-key [Smith2023, Jones2024, Paper42]
    citation groups, splitting on commas and validating each token.
    """
    seen: set[str] = set()
    keys: List[str] = []
    _valid_key = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")
    for bracket_content in re.findall(r"\[([^\]]+)\]", text):
        for part in bracket_content.split(","):
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
    """
    lines = text.split("\n")
    clean: List[str] = []
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
    citation_rows: List[Tuple],
) -> Tuple[str, List[Tuple]]:
    """Replace [AuthorYear] citekeys in body with [N] sequential numbers.

    Handles both single [Smith2023] and multi-key [Smith2023, Jones2024] groups.
    Multi-key groups are replaced with comma-separated numbers: [1], [2].
    Returns (new_body, ordered_rows) where ordered_rows lists citation_rows
    in order of first appearance.  Unknown keys are left unchanged.
    """
    citekey_map: Dict[str, Tuple] = {row[1]: row for row in citation_rows}
    ordered_keys = extract_citekeys_in_order(body)
    key_to_number: Dict[str, int] = {}
    ordered_rows: List[Tuple] = []
    n = 1
    for key in ordered_keys:
        if key in citekey_map and key not in key_to_number:
            key_to_number[key] = n
            ordered_rows.append(citekey_map[key])
            n += 1

    _valid_key = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")

    def _replacer(match: re.Match) -> str:  # type: ignore[type-arg]
        bracket_content = match.group(1)
        parts = [p.strip() for p in bracket_content.split(",")]
        valid_parts = [p for p in parts if _valid_key.match(p)]
        if not valid_parts:
            return match.group(0)
        nums = [key_to_number[p] for p in valid_parts if p in key_to_number]
        if not nums:
            return match.group(0)
        return ", ".join(f"[{num}]" for num in nums)

    # Match bracket groups that contain citekey-like content (letters, commas, spaces)
    new_body = re.sub(r"\[([A-Za-z][A-Za-z0-9_, :-]*)\]", _replacer, body)
    return new_body, ordered_rows


# Figure definitions: (artifact_key, figure_number, caption)
FIGURE_DEFS: List[Tuple[str, int, str]] = [
    (
        "prisma_diagram",
        1,
        "PRISMA 2020 flow diagram showing the study selection process.",
    ),
    (
        "rob_traffic_light",
        2,
        "Risk of bias traffic-light plot for included non-randomized studies"
        " and reviews (ROBINS-I/CASP).",
    ),
    (
        "rob2_traffic_light",
        3,
        "Risk of bias assessment using the Cochrane RoB 2 tool for the"
        " included randomized controlled trial.",
    ),
    (
        "timeline",
        4,
        "Publication timeline of included studies (2016-2026).",
    ),
    (
        "geographic",
        5,
        "Geographic distribution of included studies by country of origin.",
    ),
]


def build_markdown_figures_section(
    manuscript_path: Path,
    artifacts: Dict[str, str],
) -> str:
    """Build a Figures section with relative-path image embeds and IEEE captions.

    Only includes figures whose artifact file actually exists on disk.
    Returns an empty string if no figures are available.
    """
    lines: List[str] = ["## Figures", ""]
    any_fig = False
    for artifact_key, fig_num, caption in FIGURE_DEFS:
        fig_path_str = artifacts.get(artifact_key, "")
        if not fig_path_str:
            continue
        fig_path = Path(fig_path_str)
        if not fig_path.exists():
            continue
        # Compute relative path from manuscript file to figure (they are siblings).
        try:
            rel = fig_path.relative_to(manuscript_path.parent)
        except ValueError:
            rel = fig_path  # type: ignore[assignment]
        lines.append(f"**Fig. {fig_num}.** {caption}")
        lines.append("")
        lines.append(f"![Fig. {fig_num}: {caption}]({rel})")
        lines.append("")
        any_fig = True
    if not any_fig:
        return ""
    return "\n".join(lines)


def build_markdown_declarations_section(
    funding: str = "",
    coi: str = "",
    protocol_registered: bool = False,
    registration_id: str = "",
) -> str:
    """Build a Declarations section with funding, COI, data availability, and registration."""
    funding_text = funding or "No funding was received for this review."
    coi_text = coi or "The authors declare no conflicts of interest."
    if protocol_registered and registration_id:
        reg_text = f"The protocol was prospectively registered (ID: {registration_id})."
    else:
        reg_text = "The protocol was not prospectively registered."
    return (
        "## Declarations\n\n"
        f"**Funding:** {funding_text}\n\n"
        f"**Conflicts of Interest:** {coi_text}\n\n"
        "**Data Availability:** All data used in this review are available from "
        "the public databases searched. The extracted data supporting the findings "
        "are available from the corresponding author upon reasonable request.\n\n"
        f"**Protocol Registration:** {reg_text}"
    )


def build_study_characteristics_table(
    papers: List[Any],
    extraction_records: List[Any],
) -> str:
    """Build a GFM markdown table of included study characteristics.

    Joins CandidatePaper (author, year, country) with ExtractionRecord
    (study_design, participant_count, setting, outcomes) by paper_id.
    Returns an empty string if no data is available.
    """
    paper_map: Dict[str, Any] = {p.paper_id: p for p in papers}
    extraction_map: Dict[str, Any] = {r.paper_id: r for r in extraction_records}

    rows: List[Dict[str, str]] = []
    for paper_id, paper in paper_map.items():
        rec = extraction_map.get(paper_id)
        if rec is None:
            continue

        # Author(s), Year
        if paper.authors:
            first_author_raw = str(paper.authors[0])
            # Use the last word of the first author string as the family name
            first_author = first_author_raw.split()[-1] if first_author_raw.split() else first_author_raw
            author_str = f"{first_author} et al." if len(paper.authors) > 1 else first_author_raw
        else:
            author_str = "Unknown"
        year_str = str(paper.year) if paper.year else "n.d."
        author_year = f"{author_str}, {year_str}"

        # Study design
        design_val = rec.study_design
        if hasattr(design_val, "value"):
            design_str = design_val.value.replace("_", " ").title()
        else:
            design_str = str(design_val).replace("_", " ").title()

        # N
        n_str = str(rec.participant_count) if rec.participant_count else "NR"

        # Country
        country_str = paper.country or "NR"

        # Setting
        setting_str = rec.setting or "NR"

        # Key outcomes - take first two outcome names or results_summary keys
        outcomes_str = "NR"
        if rec.outcomes:
            outcome_names = [
                o.get("name", o.get("outcome", ""))
                for o in rec.outcomes[:2]
                if isinstance(o, dict)
            ]
            outcome_names = [name for name in outcome_names if name]
            if outcome_names:
                outcomes_str = "; ".join(outcome_names)
        if outcomes_str == "NR" and rec.results_summary:
            outcomes_str = "; ".join(list(rec.results_summary.keys())[:2])

        rows.append({
            "author_year": author_year,
            "design": design_str,
            "n": n_str,
            "country": country_str,
            "setting": setting_str,
            "outcomes": outcomes_str,
        })

    if not rows:
        return ""

    rows.sort(key=lambda r: r["author_year"])

    header = "| Author(s), Year | Study Design | N | Country | Setting | Key Outcomes |"
    sep = "|---|---|---|---|---|---|"
    data_rows = [
        f"| {r['author_year']} | {r['design']} | {r['n']} | {r['country']} | {r['setting']} | {r['outcomes']} |"
        for r in rows
    ]

    table_md = "\n".join([header, sep] + data_rows)
    return "## Appendix A: Characteristics of Included Studies\n\n" + table_md


def build_markdown_references_section(
    manuscript_text: str,
    citation_rows: List[Tuple],
    numbered: bool = True,
) -> str:
    """Build a References section for citekeys used in the manuscript body.

    When numbered=True (default), citation_rows must already be ordered by
    convert_to_numbered_citations(); entries are formatted [N] Authors, ...

    When numbered=False, uses author-year citekeys in order of first appearance.

    Entries with no author, no DOI, and no year are omitted with a footer note.
    Returns an empty string if no citations are found.
    """
    entries: List[str] = []
    omitted: List[str] = []

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
            if doi:
                entry += f" doi: {doi}"
            entries.append(entry)
    else:
        citekey_map: Dict[str, Tuple] = {row[1]: row for row in citation_rows}
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
            if doi:
                entry += f" doi: {doi}"
            entries.append(entry)

    if not entries:
        return ""

    section = "## References\n\n" + "\n\n".join(entries)
    if omitted:
        section += (
            "\n\n*Note: "
            + str(len(omitted))
            + " citation(s) omitted from this list due to incomplete metadata "
            "(no author, DOI, or year recovered from source).*"
        )
    return section


def assemble_submission_manuscript(
    body: str,
    manuscript_path: Path,
    artifacts: Dict[str, str],
    citation_rows: List[Tuple],
    papers: Optional[List[Any]] = None,
    extraction_records: Optional[List[Any]] = None,
    funding: str = "",
    coi: str = "",
) -> str:
    """Combine all manuscript sections with HR separators.

    Assembly order:
      body -> Declarations -> Study Characteristics Table -> Figures -> References

    The body is sanitized to remove LLM text artifacts and author-year
    citation keys are converted to sequential [N] numbered format.
    """
    clean_body = _sanitize_body(body)

    # Convert [AuthorYear] -> [N] numbered citations
    numbered_body, ordered_citation_rows = convert_to_numbered_citations(clean_body, citation_rows)

    declarations_section = build_markdown_declarations_section(funding=funding, coi=coi)

    study_table_section = ""
    if papers and extraction_records:
        study_table_section = build_study_characteristics_table(papers, extraction_records)

    figures_section = build_markdown_figures_section(manuscript_path, artifacts)

    refs_section = build_markdown_references_section(
        numbered_body, ordered_citation_rows, numbered=True
    )

    parts = [numbered_body]
    if declarations_section:
        parts.append(declarations_section)
    if study_table_section:
        parts.append(study_table_section)
    if figures_section:
        parts.append(figures_section)
    if refs_section:
        parts.append(refs_section)

    return "\n\n---\n\n".join(parts)


def strip_appended_sections(text: str) -> str:
    """Remove previously appended sections (idempotent helper for re-runs)."""
    for marker in (
        "\n\n---\n\n## Declarations",
        "\n\n## Declarations",
        "\n\n---\n\n## Appendix A",
        "\n\n## Appendix A",
        "\n\n---\n\n## Figures",
        "\n\n## Figures",
        "\n\n---\n\n## References",
        "\n\n## References",
    ):
        if marker in text:
            return text.split(marker)[0]
    return text
