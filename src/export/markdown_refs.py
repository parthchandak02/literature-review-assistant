"""Append Figures and References sections to a Markdown manuscript."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


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
    """Return unique citekeys in order of first appearance in text."""
    seen: set[str] = set()
    keys: List[str] = []
    for key in re.findall(r"\[([A-Za-z][A-Za-z0-9_:-]*)\]", text):
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


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


def build_markdown_references_section(
    manuscript_text: str,
    citation_rows: List[Tuple],
) -> str:
    """Build a References section for citekeys used in the manuscript body.

    Only citekeys that appear in *manuscript_text* are included, ordered by
    first appearance.  Format: [Citekey] Authors, "Title," Journal, Year. doi:
    Returns an empty string if no citations are found.
    """
    citekey_map: Dict[str, Tuple] = {row[1]: row for row in citation_rows}
    ordered_keys = extract_citekeys_in_order(manuscript_text)
    entries: List[str] = []
    for key in ordered_keys:
        row = citekey_map.get(key)
        if not row:
            continue
        _cid, citekey, doi, title, authors_json, year, journal, _bibtex = row
        authors = _fmt_authors(authors_json)
        year_str = str(year) if year else "n.d."
        entry = f'[{citekey}] {authors}, "{title},"'
        if journal:
            entry += f" *{journal}*,"
        entry += f" {year_str}."
        if doi:
            entry += f" doi: {doi}"
        entries.append(entry)
    if not entries:
        return ""
    return "## References\n\n" + "\n\n".join(entries)


def assemble_submission_manuscript(
    body: str,
    manuscript_path: Path,
    artifacts: Dict[str, str],
    citation_rows: List[Tuple],
) -> str:
    """Combine body + Figures section + References section with HR separators."""
    figures_section = build_markdown_figures_section(manuscript_path, artifacts)
    refs_section = build_markdown_references_section(body, citation_rows)
    parts = [body]
    if figures_section:
        parts.append(figures_section)
    if refs_section:
        parts.append(refs_section)
    return "\n\n---\n\n".join(parts)


def strip_appended_sections(text: str) -> str:
    """Remove previously appended Figures/References sections (idempotent helper)."""
    for marker in ("\n\n---\n\n## Figures", "\n\n## Figures", "\n\n---\n\n## References", "\n\n## References"):
        if marker in text:
            return text.split(marker)[0]
    return text
