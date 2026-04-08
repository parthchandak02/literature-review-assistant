"""Append Figures, Declarations, Study Table, and References to a Markdown manuscript."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from src.quality.grade import build_sof_table, cluster_grade_assessments_by_theme, sof_table_to_markdown

logger = logging.getLogger(__name__)

_SUMMARY_HTML_BOILERPLATE_MARKERS = (
    "html boilerplate",
    "metadata",
    "text excerpt",
    "javascript",
    "<!doctype",
    "<html",
)
_SUMMARY_PDF_METADATA_PREFIXES = (
    "pmc ",
    "doi ",
    "doi:",
    "p g y",
    "p g\n",
    "serial ",
    "## research",
    "# research",
    "### ",
    "## reviews",
    "open access",
)
_SUMMARY_LLM_EXPLANATION_PHRASES = (
    "the provided text is",
    "the text provided is",
    "this text does not",
    "does not contain the",
    "is an editorial header",
    "no specific methodology",
    "cannot be determined from",
    "the abstract does not",
    "no outcomes were reported",
    "insufficient information",
    "consists primarily of css and html code",
)


def _sanitize_summary_text(raw_text: str) -> str:
    """Return cleaned summary text or 'NR' when content is artifact-like."""
    summary = (raw_text or "").strip()
    if not summary:
        return "NR"
    summary_lower = summary.lower().lstrip()
    is_boilerplate = any(marker in summary_lower for marker in _SUMMARY_HTML_BOILERPLATE_MARKERS)
    is_pdf_metadata = any(summary_lower.startswith(pfx) for pfx in _SUMMARY_PDF_METADATA_PREFIXES)
    is_llm_explanation = any(phrase in summary_lower for phrase in _SUMMARY_LLM_EXPLANATION_PHRASES)
    if "doi.org/" in summary_lower or re.search(r"\bdoi:\s*10\.\S+", summary_lower):
        return "NR"
    if is_boilerplate or is_pdf_metadata or is_llm_explanation:
        return "NR"
    return summary


def _clip_table_text(text: str, max_chars: int) -> str:
    """Clip long table cell text at sentence boundary with ellipsis."""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    window = cleaned[:max_chars].rstrip()
    sentence_break = max(window.rfind(". "), window.rfind("; "), window.rfind(": "))
    if sentence_break > int(max_chars * 0.6):
        window = window[: sentence_break + 1].rstrip()
    return window + "..."


def _ascii_citekey(key: str) -> str:
    """Normalize a citekey to ASCII by stripping combining accent marks.

    Citekeys containing accented characters (e.g. Perez-Encinas from Perez-Encinas)
    are produced by the background SR discovery step when an author's surname has
    diacritics. The citation ledger stores the ASCII-normalized form, so lookup must
    also normalize before matching.
    """
    return "".join(c for c in unicodedata.normalize("NFD", key) if unicodedata.category(c) != "Mn")


def _validate_doi_year(doi: str | None, cited_year: int | None) -> str | None:
    """Return a warning string when a DOI's embedded year disagrees with the cited year.

    Elsevier DOIs encode the publication year: 10.1016/j.JOURNAL.YYYY.XXXXXX
    BMJ DOIs follow 10.1136/bmj.dYYYY or 10.1136/bmj.nYYYY patterns.
    A discrepancy of more than 1 year is flagged -- this catches cases like
    citing a paper as 2023 when the DOI contains 2025 (ahead-of-print issue).
    """
    import re as _re

    if not doi or not cited_year:
        return None
    # Elsevier: 10.1016/j.ABBREV.YEAR.ARTICLE_ID
    m = _re.search(r"10\.1016/\S+?\.(\d{4})\.\d", doi)
    if m:
        doi_year = int(m.group(1))
        if abs(doi_year - cited_year) > 1:
            return (
                f"DOI year mismatch: DOI encodes {doi_year} but citation year is {cited_year}. "
                f"Verify publication year for DOI {doi[:60]}."
            )
    return None


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


def _extract_surname(author_raw: Any) -> str:
    """Extract the family/surname from an author entry.

    Handles three author representations:
    - dict: reads the 'last' or 'family' key directly (correct)
    - string with comma ("Last, First Middle"): surname is the text before the
      first comma. The original split()[-1] pattern returned "Sadat" from
      "Kadkhodaei, Monireh Sadat" which was wrong.
    - string without comma ("First M. Last" / "F. Last"): surname is the last
      space-delimited token, consistent with Western name ordering.
    """
    if isinstance(author_raw, dict):
        surname = author_raw.get("last") or author_raw.get("family") or ""
        return _capitalize_name_part(surname) if surname else "NR"
    s = str(author_raw).strip()
    if not s:
        return "NR"
    if "," in s:
        # "Last, First Middle" format: everything before the first comma is the surname.
        return _capitalize_name_part(s.split(",")[0].strip())
    # "First M. Last" format: the last token is the surname.
    parts = s.split()
    return _capitalize_name_part(parts[-1]) if parts else s


def _fmt_author_str(raw: str) -> str:
    """Capitalize and lightly normalize a raw author string (Last, F. format).

    Also deduplicates doubled names that appear when metadata APIs return
    the full name in both given and family fields (e.g. "Peng Shumin Peng Shumin"
    or the CJK equivalent "彭淑敏 彭淑敏" -> "彭淑敏").
    """
    if not raw:
        return raw
    # Deduplicate doubled name: "A B A B" -> "A B" (handles both ASCII and CJK).
    words = raw.split()
    n = len(words)
    if n > 1 and n % 2 == 0:
        half = n // 2
        if words[:half] == words[half:]:
            raw = " ".join(words[:half])
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
    and validating each token. Keys containing non-ASCII letters (e.g. accented
    author surnames) are returned in their ASCII-normalized form so that catalog
    lookups succeed regardless of whether the manuscript text used the accented
    form.
    """
    seen: set[str] = set()
    keys: list[str] = []
    # Accept Unicode letters at the start so accented surnames are not silently skipped.
    _valid_key = re.compile(r"^[\w][\w0-9_:-]*$", re.UNICODE)
    for bracket_content in re.findall(r"\[([^\]]+)\]", text):
        # Split on both commas and semicolons to handle both citation styles
        for part in re.split(r"[,;]", bracket_content):
            raw_key = part.strip()
            if not _valid_key.match(raw_key):
                continue
            # Normalize to ASCII so lookups against the citation catalog succeed
            key = _ascii_citekey(raw_key)
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _sanitize_body(text: str) -> str:
    """Remove LLM-generated text artifacts from the assembled body.

    Strips:
    - Lines that are purely orphaned citation fragments starting with a comma
      (e.g. ', Katharina2025, Importancend].' with no preceding prose)
    - Lines that consist only of bracketed citekey lists with no prose

    Also removes obvious unresolved fallback keys that should never reach
    export output.
    """

    # Keep unresolved placeholders visible for contract checks; export should
    # not silently rewrite manuscript claims.
    text = text.replace(" ,", ",")
    text = text.replace(" .", ".")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\[\s*,\s*\]", "", text)

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
        if re.match(r"^\s*(?:and\s+)?will\s+be\s+considered\b", line, flags=re.IGNORECASE):
            continue
        clean.append(line)
    return "\n".join(clean)


def _strip_compact_study_tables(text: str) -> str:
    """Remove previously injected compact Study Characteristics tables."""
    _compact_block_re = re.compile(
        r"\| Study \(Year\) \| Country \| Design \| N \| Key Finding \|\n"
        r"\|---\|---\|---\|---\|---\|\n"
        r"(?:\|.*\|\n)+"
        r"\n?_Table 1\. Summary of .*?included studies.*?_",
        re.DOTALL,
    )
    return _compact_block_re.sub("", text)


def _strip_section_block_markers(text: str) -> str:
    """Remove deterministic writing boundary markers from export-facing markdown."""
    text = re.sub(r"(?m)^\s*<!--\s*SECTION_BLOCK:[^>]+-->\s*\n?", "", text)
    return re.sub(r"\s*<!--\s*SECTION_BLOCK:[^>]+-->\s*", "\n\n", text)


def _normalize_subsection_heading_layout(text: str) -> str:
    """Split inline heading+body into canonical multiline markdown.

    wf-0009 showed patterns like:
      "### Information Sources The systematic search was conducted ..."
    which should be:
      "### Information Sources"
      ""
      "The systematic search was conducted ..."

    This transform is deterministic and idempotent.
    """
    # Some legacy runs collapse multiple markdown headings into a single line.
    # Insert hard line breaks before each heading marker first.
    text = re.sub(r"\s+(#{2,6}\s+)", r"\n\n\1", text)

    _heading_re = re.compile(r"^(#{2,6})\s+(.+)$")
    _sentence_start_re = re.compile(
        r"^(The|This|These|We|Our|In|Across|To|A|An|Studies|Study|Data|Evidence|Findings|Overall|One|Demographic|Meta-analysis|Also)\b"
    )
    _title_token_re = re.compile(r"^[A-Z][A-Za-z0-9()/:,\-']*$")
    _connector_tail = {"and", "or", "of", "for", "to", "with"}
    _citation_tail_re = re.compile(r"\s*(?:\[[^\]]+\]\s*)+$")

    def _looks_title_fragment(s: str) -> bool:
        words = s.strip().split()
        if not words or len(words) > 5:
            return False
        return all(_title_token_re.match(w) or w.lower() in _connector_tail for w in words)

    out_lines: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _heading_re.match(line.strip())
        if m:
            level = m.group(1)
            tail = m.group(2).strip()
            tail = _citation_tail_re.sub("", tail).strip()
            _known_prefix_map = {
                "data items": "Data Items",
                "comparison with prior work": "Comparison with Prior Work",
                "search strategy": "Search Strategy",
                "risk of bias and critical appraisal": "Risk of Bias and Critical Appraisal",
            }
            _tail_low = tail.lower()
            _matched_known = False
            for _raw_prefix, _canonical in _known_prefix_map.items():
                _needle = _raw_prefix + " "
                if _tail_low.startswith(_needle):
                    _body = tail[len(_raw_prefix) :].strip()
                    out_lines.extend([f"{level} {_canonical}", ""])
                    if _body:
                        out_lines.append(_body)
                    _matched_known = True
                    break
            if _matched_known:
                i += 1
                continue
            if len(level) >= 4:
                _spill = re.search(
                    r"\b(The|This|These|We|Our|In|Across|To|A|An|Evidence|Findings|Overall|One|Demographic|Meta-analysis|Also)\b",
                    tail,
                )
                if _spill and _spill.start() > 10:
                    _left = tail[: _spill.start()].strip(" -:")
                    _right = tail[_spill.start() :].strip()
                    if _left and _right:
                        out_lines.extend([f"{level} {_left}", "", _right])
                        i += 1
                        continue
            # Handle run-on headings like "#### Other Outcomes such as ...".
            if " such as " in tail.lower():
                _idx = tail.lower().find(" such as ")
                _left = tail[:_idx].strip()
                _right = tail[_idx + 1 :].strip()
                if _left and _right:
                    out_lines.extend([f"{level} {_left}", "", _right])
                    i += 1
                    continue
            nxt_idx = i + 1
            while nxt_idx < len(lines) and not lines[nxt_idx].strip():
                nxt_idx += 1
            nxt = lines[nxt_idx].strip() if nxt_idx < len(lines) else ""
            tail_words = tail.split()
            if nxt and not nxt.startswith("#"):
                if tail_words and tail_words[-1].lower() in _connector_tail:
                    # Case: heading line ends with connector and next line starts with
                    # title token + sentence punctuation, e.g. "and" + "Performance. ...".
                    _nxt_words = nxt.split()
                    if _nxt_words:
                        _first = _nxt_words[0]
                        _first_clean = _first.rstrip(".,;:!?")
                        if _first_clean and _first_clean[:1].isupper():
                            if _first != _first_clean:
                                _new_heading = f"{level} {tail} {_first_clean}".strip()
                                _new_body = " ".join(_nxt_words[1:]).strip()
                                if _new_body:
                                    out_lines.extend([_new_heading, "", _new_body])
                                    i = nxt_idx + 1
                                    continue
                    nxt_words = nxt.split()
                    consumed = 0
                    for j, w in enumerate(nxt_words):
                        if (
                            j > 0
                            and w.lower() in {"the", "this", "these", "we", "our", "in", "across", "to", "a", "an"}
                            and j + 1 < len(nxt_words)
                            and nxt_words[j + 1][:1].islower()
                        ):
                            break
                        if _title_token_re.match(w):
                            consumed = j + 1
                            if consumed >= 4:
                                break
                            continue
                        break
                    if consumed > 0:
                        title_join = " ".join(nxt_words[:consumed]).strip()
                        body_rest = " ".join(nxt_words[consumed:]).strip()
                        line = f"{level} {tail} {title_join}".strip()
                        if body_rest:
                            out_lines.extend([line, "", body_rest])
                            i = nxt_idx + 1
                            continue
                        out_lines.append(line)
                        i = nxt_idx + 1
                        continue
                # Case: heading absorbed one title token that actually begins body prose,
                # e.g. "Risk of Bias Assessment Risk" + "of bias was assessed...".
                if (
                    nxt[:1].islower()
                    and len(tail_words) >= 3
                    and tail_words[-1][:1].isupper()
                    and tail_words[-1].isalpha()
                ):
                    spill = tail_words[-1]
                    heading_tail = " ".join(tail_words[:-1]).strip()
                    if heading_tail:
                        out_lines.extend([f"{level} {heading_tail}", "", f"{spill} {nxt}".strip()])
                        i = nxt_idx + 1
                        continue
                if (tail_words and tail_words[-1].lower() in _connector_tail and _looks_title_fragment(nxt)) or (
                    len(tail_words) <= 3 and _looks_title_fragment(nxt) and not _sentence_start_re.match(nxt)
                ):
                    line = f"{level} {tail} {nxt}".strip()
                    i = nxt_idx + 1

            words = line.strip().split()
            split_applied = False
            if len(words) >= 4 and words[0].startswith("#"):
                for idx in range(3, min(len(words), 12)):
                    left_words = words[1:idx]
                    right = " ".join(words[idx:]).strip()
                    left_ok = all(_title_token_re.match(w) or w.lower() in _connector_tail for w in left_words)
                    if not left_ok:
                        continue
                    right_lower = right.lower()
                    if (
                        _sentence_start_re.match(right)
                        or (
                            right_lower.startswith(
                                (
                                    "for ",
                                    "in ",
                                    "across ",
                                    "to ",
                                    "from ",
                                    "with ",
                                    "is ",
                                    "are ",
                                    "was ",
                                    "were ",
                                    "followed ",
                                    "defined ",
                                    "developed ",
                                )
                            )
                        )
                        or (right and right[0].isupper() and any(c in right for c in ".,"))
                    ) and not _looks_title_fragment(right):
                        out_lines.extend([f"{words[0]} {' '.join(left_words)}", "", right])
                        split_applied = True
                        break
            if not split_applied:
                out_lines.append(line)
        else:
            out_lines.append(line)
        i += 1

    return "\n".join(out_lines)


def _dedup_citation_rows_by_doi(rows: list[tuple]) -> list[tuple]:
    """Return rows with duplicate DOIs collapsed to the first occurrence.

    A paper registered twice in the citation ledger (e.g., once as an included
    study and once as a background reference) produces two citekeys that resolve
    to the same DOI, which then renders as two numbered entries in the reference
    list.  This helper keeps the first row per normalized DOI and silently drops
    all subsequent duplicates.  Rows with no DOI are kept as-is (they cannot be
    matched on DOI).
    """
    seen_dois: set[str] = set()
    deduped: list[tuple] = []
    for row in rows:
        # row layout: (cid, citekey, doi, title, authors_json, year, journal, bibtex, url)
        raw_doi = row[2] if len(row) > 2 else None
        norm = _normalize_doi(raw_doi) if raw_doi else ""
        if norm and norm in seen_dois:
            continue
        if norm:
            seen_dois.add(norm)
        deduped.append(row)
    return deduped


def convert_to_numbered_citations(
    body: str,
    citation_rows: list[tuple],
) -> tuple[str, list[tuple]]:
    """Replace [AuthorYear] citekeys in body with [N] sequential numbers.

    Handles both single [Smith2023] and multi-key [Smith2023, Jones2024] groups.
    Multi-key groups are replaced with comma-separated numbers: [1], [2].
    Returns (new_body, ordered_rows) where ordered_rows lists citation_rows
    in order of first appearance.  Unknown keys are left unchanged.

    Citekeys with non-ASCII characters (e.g. accented author surnames like
    Perez-Encinas) are normalized to ASCII before catalog lookup so they resolve
    correctly regardless of how they appear in the manuscript text.
    """

    def _canonical_key(raw: str) -> str:
        # Forgiving key for matching legacy variants (spaces/punctuation/accents).
        return re.sub(r"[^A-Za-z0-9]", "", _ascii_citekey(raw)).lower()

    # Build catalog maps for robust lookup.
    citekey_map: dict[str, tuple] = {_ascii_citekey(row[1]): row for row in citation_rows}
    canonical_map: dict[str, str] = {}
    for row in citation_rows:
        key = _ascii_citekey(row[1])
        canonical_map[_canonical_key(key)] = key
    ordered_keys = extract_citekeys_in_order(body)  # already returns ASCII-normalized keys
    # Augment with legacy space-containing keys that extract_citekeys_in_order
    # intentionally skips (it expects citekey-like tokens).
    seen_ordered = set(ordered_keys)
    for m in re.finditer(r"\[([^\]\[]{1,120})\]", body):
        for part in [p.strip() for p in re.split(r"[,;]", m.group(1))]:
            if not part:
                continue
            canon = _canonical_key(part)
            mapped = canonical_map.get(canon)
            if mapped and mapped not in seen_ordered:
                ordered_keys.append(mapped)
                seen_ordered.add(mapped)
    key_to_number: dict[str, int] = {}
    ordered_rows: list[tuple] = []
    n = 1
    for key in ordered_keys:
        if key in citekey_map and key not in key_to_number:
            key_to_number[key] = n
            ordered_rows.append(citekey_map[key])
            n += 1

    # Accept Unicode word chars so accented citekeys in the text are captured by the pattern
    _valid_key = re.compile(r"^[\w][\w0-9_:\- '.]*$", re.UNICODE)

    def _replacer(match: re.Match) -> str:  # type: ignore[type-arg]
        bracket_content = match.group(1)
        # Split on both commas and semicolons to handle [Smith2023; Jones2024] style
        parts = [p.strip() for p in re.split(r"[,;]", bracket_content)]
        valid_parts = [p for p in parts if _valid_key.match(p)]
        if not valid_parts:
            return match.group(0)
        # Normalize each part before catalog lookup (supports space-containing legacy keys).
        nums: list[int] = []
        for p in valid_parts:
            ascii_key = _ascii_citekey(p)
            if ascii_key in key_to_number:
                nums.append(key_to_number[ascii_key])
                continue
            canon = _canonical_key(ascii_key)
            mapped = canonical_map.get(canon)
            if mapped and mapped in key_to_number:
                nums.append(key_to_number[mapped])
        if not nums:
            return match.group(0)
        return ", ".join(f"[{num}]" for num in nums)

    # Extend outer pattern to capture Unicode letters so accented citekeys are matched
    new_body = re.sub(r"\[([^\]\[]{1,120})\]", _replacer, body)
    return new_body, ordered_rows


# Figure definitions: ordered list of (artifact_key, caption).
# Numbers are NOT stored here -- they are assigned dynamically at render time
# by counting only figures whose artifact file actually exists on disk.
# This prevents gaps (e.g. Fig 1, 2, 4, 5) when optional figures like
# rob2_traffic_light or forest plots are absent.
FIGURE_DEFS: list[tuple[str, str]] = [
    (
        "prisma_diagram",
        "PRISMA 2020 flow diagram showing the study selection process. "
        "Records excluded at the title/abstract stage include two automated steps "
        "applied before independent dual review: (1) BM25 keyword relevance filtering "
        "and (2) batch LLM pre-ranking (records scoring below the configured relevance threshold were "
        "automatically excluded). Only records passing both steps were forwarded for "
        "independent dual review.",
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


def _rob_traffic_caption_for_assessments(
    robins_i_assessments: list[Any] | None = None,
    casp_assessments: list[Any] | None = None,
    mmat_assessments: list[Any] | None = None,
) -> str:
    """Return run-aware caption for the non-RCT risk-of-bias figure."""
    has_robins = bool(robins_i_assessments)
    has_casp = bool(casp_assessments)
    has_mmat = bool(mmat_assessments)
    if has_mmat and not has_robins and not has_casp:
        return "Risk of bias traffic-light plot for included mixed-methods studies (MMAT)."
    if has_mmat and has_casp and not has_robins:
        return "Risk of bias traffic-light plot for included studies (MMAT/CASP)."
    if has_mmat and has_robins and not has_casp:
        return "Risk of bias traffic-light plot for included studies (ROBINS-I/MMAT)."
    if has_mmat and has_robins and has_casp:
        return "Risk of bias traffic-light plot for included studies (ROBINS-I/CASP/MMAT)."
    if has_robins and has_casp:
        return "Risk of bias traffic-light plot for included non-randomized studies and reviews (ROBINS-I/CASP)."
    if has_robins:
        return "Risk of bias traffic-light plot for included non-randomized studies (ROBINS-I)."
    if has_casp:
        return "Risk of bias traffic-light plot for included studies appraised with CASP."
    return "Risk of bias traffic-light plot for included non-randomized studies and reviews (ROBINS-I/CASP)."


def get_existing_figure_entries(
    manuscript_path: Path,
    artifacts: dict[str, str],
    caption_overrides: dict[str, str] | None = None,
) -> list[tuple[str, Path, str]]:
    """Return ordered existing figures as (caption, absolute_path, relative_path).

    Uses FIGURE_DEFS ordering and caption sidecar overrides so markdown and LaTeX
    paths are derived from one canonical manifest.
    """
    entries: list[tuple[str, Path, str]] = []
    _overrides = caption_overrides or {}
    for artifact_key, default_caption in FIGURE_DEFS:
        fig_path_str = artifacts.get(artifact_key, "")
        if not fig_path_str:
            continue
        fig_path = Path(fig_path_str)
        if not fig_path.exists():
            continue
        caption = _overrides.get(artifact_key, default_caption)
        caption_sidecar = fig_path.with_suffix(".caption")
        if caption_sidecar.exists():
            try:
                caption = caption_sidecar.read_text(encoding="utf-8").strip() or caption
            except Exception as exc:
                logger.warning("Could not read figure caption sidecar %s: %s", caption_sidecar, exc)
        try:
            rel_path = str(fig_path.relative_to(manuscript_path.parent))
        except ValueError:
            rel_path = str(fig_path)
        entries.append((caption, fig_path, rel_path))
    return entries


def get_latex_figure_paths(
    manuscript_path: Path,
    artifacts: dict[str, str],
    caption_overrides: dict[str, str] | None = None,
) -> list[str]:
    """Return ordered figure paths safe for pdflatex includegraphics.

    The list is derived from the same canonical figure entries used by markdown.
    SVG files are excluded here because the current pdflatex toolchain does not
    natively embed SVG without conversion.
    """
    raster_suffixes = {".png", ".jpg", ".jpeg", ".pdf"}
    paths: list[str] = []
    for _caption, fig_path, rel_path in get_existing_figure_entries(manuscript_path, artifacts, caption_overrides):
        if fig_path.suffix.lower() in raster_suffixes:
            paths.append(rel_path)
    return paths


def build_markdown_figures_section(
    manuscript_path: Path,
    artifacts: dict[str, str],
    caption_overrides: dict[str, str] | None = None,
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
    for caption, _fig_path, rel in get_existing_figure_entries(manuscript_path, artifacts, caption_overrides):
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
    author = author_name.strip() if author_name.strip() else "Corresponding Author"
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
    elif protocol_registered:
        reg_text = "The protocol was prospectively registered (registration number not on file)."
    else:
        reg_text = (
            "This review was not prospectively registered. "
            "Because the review was conducted retrospectively, PROSPERO registration was not possible. "
            "The completed protocol has been submitted for post-hoc registration via the "
            "Open Science Framework (OSF; https://osf.io), declared transparently "
            "per PRISMA 2020 item 24. The authors confirm that no outcomes were added, "
            "removed, or re-specified after data collection began."
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


def _is_primary_study_record(rec: Any) -> bool:
    """Return True unless record is explicitly marked non-primary.

    Legacy runs and many unit fixtures do not carry primary_study_status.
    Those should remain eligible unless explicitly classified as non-primary.
    """
    status_obj = getattr(rec, "primary_study_status", None)
    status = getattr(status_obj, "value", status_obj)
    return str(status or "unknown").lower() not in {"secondary_review", "protocol_only", "non_empirical"}


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


def build_compact_study_table(
    papers: list[Any],
    extraction_records: list[Any],
    max_rows: int = 78,
) -> str:
    """Build a compact 5-column GFM table for the Results body (PRISMA 2020 Item 19).

    Columns: Study (Year) | Country | Design | N | Key Finding

    This is a concise in-body table, not the full Appendix B table. It is
    inserted right after the Study Characteristics heading in the assembled
    Results section so PRISMA Item 19 is satisfied.

    Returns an empty string when no usable data is available.
    """
    paper_map: dict[str, Any] = {p.paper_id: p for p in papers}
    extraction_map: dict[str, Any] = {r.paper_id: r for r in extraction_records}

    rows: list[tuple[str, str, str, str, str]] = []
    for paper_id, paper in paper_map.items():
        rec = extraction_map.get(paper_id)
        if rec is None or is_extraction_failed(rec) or not _is_primary_study_record(rec):
            continue

        # Author (Year) column
        if paper.authors:
            first = _extract_surname(paper.authors[0])
            author_str = f"{first} et al." if len(paper.authors) > 1 else first
        else:
            author_str = "NR"
        year_str = str(paper.year) if getattr(paper, "year", None) else "n.d."
        study_col = f"{author_str} ({year_str})"

        # Country -- use paper.country only; the setting fallback is unreliable
        # (it can yield institution names like "Clinical facility" or lab names).
        country = str(getattr(paper, "country", None) or "").strip()
        country = country[:30] if country else "NR"

        # Study design
        design_val = getattr(rec, "study_design", None)
        if design_val is None:
            design_str = "NR"
        elif hasattr(design_val, "value"):
            raw = design_val.value.replace("_", " ")
            design_str = raw.title() if raw else "NR"
        else:
            design_str = str(design_val).replace("_", " ").title() or "NR"
        # Shorten very long labels for table readability
        _DESIGN_SHORT: dict[str, str] = {
            "Randomized Controlled Trial": "RCT",
            "Non Randomized Interventional": "Non-RCT",
            "Prospective Cohort": "Cohort",
            "Retrospective Cohort": "Retro Cohort",
        }
        design_str = _DESIGN_SHORT.get(design_str, design_str)

        # N (participant count)
        n_val = getattr(rec, "participant_count", None)
        n_str = str(n_val) if n_val else "NR"

        # Key finding -- ExtractionRecord has results_summary: dict[str, str],
        # not a key_finding field. Pull the most descriptive sub-key available.
        summary_dict: dict[str, str] = getattr(rec, "results_summary", {}) or {}
        finding = (
            summary_dict.get("summary")
            or summary_dict.get("main_finding")
            or summary_dict.get("key_finding")
            or summary_dict.get("primary_outcome")
            or ""
        ).strip()
        finding = _sanitize_summary_text(finding)
        finding = finding if finding else "NR"
        if finding != "NR":
            finding = _clip_table_text(finding, max_chars=180)
        finding = _escape_table_cell(finding)

        rows.append((study_col, country, design_str, n_str, finding))

    if not rows:
        return ""

    total_usable = len(rows)
    rows = rows[:max_rows]

    header = "| Study (Year) | Country | Design | N | Key Finding |"
    sep = "|---|---|---|---|---|"
    data_lines = [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
    if total_usable > len(rows):
        note = (
            f"\n_Table 1. Summary of {len(rows)} of {total_usable} included studies "
            f"(compact in-body view). See Appendix B for full characteristics. "
            "NR means not reported in the source report or unavailable after extraction._"
        )
    else:
        note = (
            f"\n_Table 1. Summary of {len(rows)} included studies. See Appendix B for full characteristics. "
            "NR means not reported in the source report or unavailable after extraction._"
        )
    return "\n".join([header, sep] + data_lines) + note


def build_study_characteristics_table(
    papers: list[Any],
    extraction_records: list[Any],
    pre_filtered_count: int = 0,
    fulltext_paper_ids: set[str] | None = None,
) -> str:
    """Build a GFM markdown table of included study characteristics.

    Joins CandidatePaper (author, year, country) with ExtractionRecord
    (study_design, participant_count, setting, outcomes) by paper_id.
    Excludes papers whose extraction completely failed (all placeholder data).
    Returns an empty string if no usable data is available.

    pre_filtered_count: number of extraction records already excluded by the
    caller before passing this list. Added to the footnote so the total
    omission count is accurate even when the caller pre-filters.

    fulltext_paper_ids: set of paper_ids for which a full-text PDF or TXT
    file was retrieved and saved to disk. Used to correctly mark
    "Full Text Retrieved" as Yes even when extraction_source stayed "text"
    because the retrieval fell back to abstract for extraction purposes.
    """
    paper_map: dict[str, Any] = {p.paper_id: p for p in papers}
    extraction_map: dict[str, Any] = {r.paper_id: r for r in extraction_records}

    rows: list[dict[str, str]] = []
    excluded_count = pre_filtered_count
    for paper_id, paper in paper_map.items():
        rec = extraction_map.get(paper_id)
        if rec is None:
            continue

        if is_extraction_failed(rec) or not _is_primary_study_record(rec):
            excluded_count += 1
            continue

        # Author(s), Year
        if paper.authors:
            first_author = _extract_surname(paper.authors[0])
            author_str = f"{first_author} et al." if len(paper.authors) > 1 else first_author
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
        real_names = [
            o.name.strip() for o in (rec.outcomes or [])[:3] if o.name.strip().lower() not in _PLACEHOLDER_OUTCOME_NAMES
        ]
        if real_names:
            outcomes_str = "; ".join(real_names[:2])
        else:
            # Fall back to results_summary["summary"] truncated and cleaned.
            summary = ""
            if isinstance(rec.results_summary, dict):
                summary = rec.results_summary.get("summary", "")
            elif isinstance(rec.results_summary, str):
                summary = rec.results_summary
            sanitized_summary = _sanitize_summary_text(summary)
            if sanitized_summary == "NR":
                outcomes_str = "NR"
                logger.warning(
                    "Artifact/explanation text detected in results_summary for paper %s; Key Outcomes set to NR.",
                    paper_id,
                )
            else:
                outcomes_str = _clip_table_text(sanitized_summary, max_chars=260)
        # Escape newlines and pipe chars so the cell does not break the markdown table.
        outcomes_str = _escape_table_cell(outcomes_str)

        # Full text retrieved: Yes when a full-text file exists on disk OR when
        # extraction_source indicates a non-abstract source was used.
        # Check file presence first (fulltext_paper_ids from papers/ directory)
        # to correctly handle cases where a PDF was retrieved but extraction
        # fell back to abstract text (extraction_source stays "text").
        # Uses the same _ABSTRACT_ONLY_SOURCES set as context_builder.py to ensure
        # consistent classification across the manuscript and Appendix B.
        _ABSTRACT_ONLY_SOURCES = frozenset({"text", "heuristic", None, ""})
        extraction_source = getattr(rec, "extraction_source", None)
        has_fulltext_file = paper_id in (fulltext_paper_ids or set())
        full_text_retrieved = "Yes" if (extraction_source not in _ABSTRACT_ONLY_SOURCES or has_fulltext_file) else "No"

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
        "_NR = not reported in source report or unavailable after extraction; n.d. = no publication date available. "
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
        first_author = _extract_surname(paper.authors[0])
        author_str = f"{first_author} et al." if len(paper.authors) > 1 else first_author
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


def build_quality_assessment_coverage_table(
    papers: list[Any],
    rob2_assessments: list[Any] | None = None,
    robins_i_assessments: list[Any] | None = None,
    casp_assessments: list[Any] | None = None,
    mmat_assessments: list[Any] | None = None,
) -> str:
    """Build per-study quality tool coverage table for included studies.

    This avoids appendix ambiguity where a single tool table (for example,
    ROBINS-I) can look incomplete when other included studies were assessed
    with CASP/MMAT/RoB 2.
    """
    if not papers:
        return ""

    tool_map: dict[str, tuple[str, str]] = {}
    for a in rob2_assessments or []:
        judgment = _robins_judgment_display(getattr(a, "overall_judgment", None))
        tool_map[str(getattr(a, "paper_id", ""))] = ("RoB 2", judgment)
    for a in robins_i_assessments or []:
        judgment = _robins_judgment_display(getattr(a, "overall_judgment", None))
        tool_map[str(getattr(a, "paper_id", ""))] = ("ROBINS-I", judgment)
    for a in casp_assessments or []:
        summary = (str(getattr(a, "overall_summary", "") or "").strip() or "NR").replace("|", "-")
        tool_map[str(getattr(a, "paper_id", ""))] = ("CASP", summary[:80])
    for a in mmat_assessments or []:
        score = getattr(a, "overall_score", None)
        score_str = f"score {score}/5" if score is not None else "NR"
        tool_map[str(getattr(a, "paper_id", ""))] = ("MMAT", score_str)

    header = "| Study | Tool Used | Overall Assessment |"
    sep = "|---|---|---|"
    rows = [header, sep]
    missing = 0
    for p in sorted(papers, key=lambda x: _paper_author_year(x)):
        pid = str(getattr(p, "paper_id", ""))
        label = _paper_author_year(p)
        tool, overall = tool_map.get(pid, ("Not mapped", "NR"))
        if tool == "Not mapped":
            missing += 1
        rows.append(f"| {label} | {tool} | {overall} |")

    note = (
        "_Coverage table maps each included study to the quality tool that generated "
        "its final risk-of-bias assessment. Use this table to interpret why a given "
        "study may appear in ROBINS-I, CASP, MMAT, or RoB 2 sections._"
    )
    if missing > 0:
        note += f" _Warning: {missing} included study row(s) had no mapped quality assessment._"
    return "## Quality Assessment Coverage\n\n" + "\n".join(rows) + "\n\n" + note


def _normalize_criteria_text(raw_text: str) -> str:
    """Normalize criteria lists and drop malformed placeholder fragments."""
    if not (raw_text or "").strip():
        return "NR"
    parts = [p.strip(" ;") for p in raw_text.split(";")]
    cleaned_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if re.match(r"^(?:will\s+be\s+considered|to\s+ensure\s+technological\s+relevance)\b", part, re.IGNORECASE):
            continue
        if len(re.findall(r"[A-Za-z]", part)) < 4:
            continue
        cleaned_parts.append(re.sub(r"\s{2,}", " ", part).strip())
    return "; ".join(cleaned_parts) if cleaned_parts else "NR"


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

    # Strip date-range phrases from inclusion/exclusion criteria text entirely.
    # The PICOS table already has a dedicated "Date range" row that shows the
    # authoritative protocol window (date_range_start - date_range_end).
    # Criteria text should describe WHAT is eligible, not WHEN -- having a date
    # phrase there creates duplication and risks inconsistency with the Date range row.
    # Pattern: "Research published between January 2010 and December 2025 is included..."
    #          "Studies published from 2000 to 2026..."
    # We strip the date-range sub-clause (and any trailing filler like "is included
    # to ensure technological relevance") from each criterion that contains one.
    _ds = getattr(review_config, "date_range_start", None)
    _de = getattr(review_config, "date_range_end", None)
    if _ds and _de:
        _month = (
            r"(?:January|February|March|April|May|June|"
            r"July|August|September|October|November|December)\s+"
        )
        _date_phrase_re = re.compile(
            r"(?:Research\s+published\s+|Studies\s+published\s+)?"
            r"(?:from\s+|between\s+)?"
            r"(?:" + _month + r")?\d{4}"
            r"\s+(?:and|to)\s+"
            r"(?:" + _month + r")?\d{4}"
            r"(?:\s+is\s+included[^.;]*)?",
            re.IGNORECASE,
        )
        inc_str = _date_phrase_re.sub("", inc_str).strip("; ").strip()
        exc_str = _date_phrase_re.sub("", exc_str).strip("; ").strip()
    inc_str = _normalize_criteria_text(inc_str)
    exc_str = _normalize_criteria_text(exc_str)

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

    # Date range row: use the protocol eligibility window, not the publication years of
    # included papers. This prevents the PICOS table from showing a narrower window
    # than the protocol actually specified.
    date_start = getattr(review_config, "date_range_start", None)
    date_end = getattr(review_config, "date_range_end", None)
    if date_start and date_end:
        date_range_val = f"{date_start} to {date_end}"
    elif date_start:
        date_range_val = f"{date_start} to present"
    else:
        date_range_val = "NR"

    rows = [
        ("Population", getattr(pico, "population", "") or "NR"),
        ("Intervention", getattr(pico, "intervention", "") or "NR"),
        ("Comparison", getattr(pico, "comparison", "") or "NR"),
        ("Outcome", getattr(pico, "outcome", "") or "NR"),
        ("Study design", study_design_val),
        ("Date range", date_range_val),
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


def generate_casp_table(
    casp_assessments: list[Any],
    paper_id_to_label: dict[str, str] | None = None,
) -> str:
    """Generate a CASP checklist summary table for qualitative studies.

    Each row represents one included study. When paper_id_to_label is provided,
    uses the citekey/author-year label for the Paper column instead of a raw UUID.
    Returns an empty string when no assessments are provided.
    """
    if not casp_assessments:
        return ""

    _label_map = paper_id_to_label or {}

    _CRITERIA = [
        ("design_appropriate", "Design Appropriate"),
        ("recruitment_strategy", "Recruitment"),
        ("data_collection_rigorous", "Data Collection"),
        ("reflexivity_considered", "Reflexivity"),
        ("ethics_considered", "Ethics"),
        ("analysis_rigorous", "Analysis"),
        ("findings_clear", "Findings Clear"),
        ("value_of_research", "Value"),
    ]
    header_cols = ["Study"] + [c[1] for c in _CRITERIA] + ["Overall Summary"]
    header = "| " + " | ".join(header_cols) + " |"
    sep = "| " + " | ".join(["---"] * len(header_cols)) + " |"
    rows = [header, sep]
    for a in casp_assessments:
        pid = getattr(a, "paper_id", "")
        label = _label_map.get(pid, pid[:12])
        vals = ["YES" if getattr(a, attr, False) else "NO" for attr, _ in _CRITERIA]
        summary = (getattr(a, "overall_summary", "") or "")[:100].replace("|", "-").replace("\n", " ")
        rows.append("| " + " | ".join([label] + vals + [summary]) + " |")

    footnote = (
        "_CASP: Critical Appraisal Skills Programme checklist for qualitative studies. "
        "YES = criterion met; NO = criterion not met or unclear._"
    )
    return "## CASP Quality Assessment\n\n" + "\n".join(rows) + "\n\n" + footnote


def generate_mmat_table(
    mmat_assessments: list[Any],
    paper_id_to_label: dict[str, str] | None = None,
) -> str:
    """Generate an MMAT 2018 quality assessment summary table for mixed-methods studies.

    Each row shows the study, study type, screening criteria, five type-specific
    criteria as YES/NO, overall score (0-5), and summary. When paper_id_to_label
    is provided, uses citekey/author-year labels instead of raw UUID prefixes.
    Returns an empty string when no assessments are provided.
    """
    if not mmat_assessments:
        return ""

    _label_map = paper_id_to_label or {}

    header_cols = [
        "Study",
        "Study Type",
        "Screen 1",
        "Screen 2",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "Score (0-5)",
        "Summary",
    ]
    header = "| " + " | ".join(header_cols) + " |"
    sep = "| " + " | ".join(["---"] * len(header_cols)) + " |"
    rows = [header, sep]
    for a in mmat_assessments:
        pid = getattr(a, "paper_id", "")
        label = _label_map.get(pid, pid[:12])
        stype = str(getattr(a, "study_type", "") or "").replace("_", " ")
        s1 = "YES" if getattr(a, "screening_1_clear_question", False) else "NO"
        s2 = "YES" if getattr(a, "screening_2_appropriate_data", False) else "NO"
        c1 = "YES" if getattr(a, "criterion_1", False) else "NO"
        c2 = "YES" if getattr(a, "criterion_2", False) else "NO"
        c3 = "YES" if getattr(a, "criterion_3", False) else "NO"
        c4 = "YES" if getattr(a, "criterion_4", False) else "NO"
        c5 = "YES" if getattr(a, "criterion_5", False) else "NO"
        score = str(getattr(a, "overall_score", "NR"))
        summary_raw = str(getattr(a, "overall_summary", "") or "")
        summary_clean = summary_raw.replace("|", "-").replace("\n", " ")
        summary = summary_clean.strip()
        rows.append("| " + " | ".join([label, stype, s1, s2, c1, c2, c3, c4, c5, score, summary]) + " |")

    footnote = (
        "_MMAT 2018: Mixed Methods Appraisal Tool. "
        "Screen 1: Research question clearly stated? Screen 2: Appropriate data collected? "
        "C1-C5: Study-type-specific criteria. Score = count of YES criteria (max 5)._"
    )
    return "## MMAT Quality Assessment\n\n" + "\n".join(rows) + "\n\n" + footnote


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
            _cid, citekey, doi, title, authors_json, year, journal, _bibtex, _url = row
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
            # Warn on DOI/year mismatch (e.g. Elsevier ahead-of-print papers)
            _doi_warn = _validate_doi_year(doi, year)
            if _doi_warn:
                import logging as _log_mod

                _log_mod.getLogger(__name__).warning("Reference [%d] %s: %s", idx, citekey, _doi_warn)
            entries.append(entry)
    else:
        citekey_map: dict[str, tuple] = {row[1]: row for row in citation_rows}
        ordered_keys = extract_citekeys_in_order(manuscript_text)
        for key in ordered_keys:
            row = citekey_map.get(key)
            if not row:
                continue
            _cid, citekey, doi, title, authors_json, year, journal, _bibtex, _url = row
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


def _normalize_date_range(text: str, date_start: str, date_end: str) -> str:
    """Replace inconsistent date range mentions with the authoritative protocol values.

    The LLM writing step sometimes outputs a different year than the config (e.g.
    writes "2000 and 2025" when the protocol says 2000-2026). This function
    deterministically corrects the date range in the manuscript body so that
    the Methods eligibility window always matches the PICOS table.

    Only replaces year pairs that are clearly date-range constructs (e.g.
    "from YYYY to YYYY", "YYYY-YYYY", "between YYYY and YYYY") and where at
    least one of the years is close to the expected values.
    """
    # Patterns that represent a date range in the manuscript Methods section.
    # We only normalize where the start year matches date_start exactly.
    # The end year may be off by 1-2 years (LLM drift); we correct it to date_end.
    patterns = [
        # "from 2000 to 2025" / "from 2000 to 2026"
        (
            re.compile(
                r"\bfrom\s+" + re.escape(date_start) + r"\s+to\s+(\d{4})\b",
                re.IGNORECASE,
            ),
            f"from {date_start} to {date_end}",
        ),
        # "2000 and 2025" (common LLM phrasing for date range in eligibility)
        (
            re.compile(
                re.escape(date_start) + r"\s+and\s+(\d{4})\b",
                re.IGNORECASE,
            ),
            f"{date_start} and {date_end}",
        ),
        # "2000-2025" or "2000 - 2025"
        (
            re.compile(
                re.escape(date_start) + r"\s*[-\u2013]\s*(\d{4})\b",
            ),
            f"{date_start}-{date_end}",
        ),
        # "between 2000 and 2025"
        (
            re.compile(
                r"\bbetween\s+" + re.escape(date_start) + r"\s+and\s+(\d{4})\b",
                re.IGNORECASE,
            ),
            f"between {date_start} and {date_end}",
        ),
    ]
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


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
    rob2_assessments: list[Any] | None = None,
    robins_i_assessments: list[Any] | None = None,
    casp_assessments: list[Any] | None = None,
    mmat_assessments: list[Any] | None = None,
    paper_id_to_citekey: dict[str, str] | None = None,
    review_config: Any | None = None,
    failed_count: int = 0,
    search_appendix_path: Path | None = None,
    research_question: str = "",
    title: str | None = None,
    fulltext_paper_ids: set[str] | None = None,
    include_rq_block: bool = False,
    ir_validated: bool = False,
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
    include_rq_block: when True, prepend "Research Question: <question>" between the
    title and the abstract body. Defaults to False (omit for IEEE submissions where
    this non-standard prefix would appear before the structured abstract).
    ir_validated: when True, the body came from validated IR blocks (WS1+WS2 path)
    and redundant sanitization passes are skipped. The assembly does only structural
    transforms (citation numbering, table insertion, appendix stitching).
    """
    _body_wo_markers = _strip_section_block_markers(body)
    if ir_validated:
        clean_body = _strip_compact_study_tables(_body_wo_markers)
    else:
        _needs_legacy_heading_fix = bool(
            re.search(r"(?m)^#{2,6}\s+.+\s+#{2,6}\s+", _body_wo_markers)
            or re.search(r"(?m)^#{2,6}\s+\S.{8,}\s+(?:The|This|These|for|in|Across|To)\b", _body_wo_markers)
        )
        if _needs_legacy_heading_fix:
            _body_wo_markers = _normalize_subsection_heading_layout(_body_wo_markers)
        clean_body = _strip_compact_study_tables(_sanitize_body(_body_wo_markers))

    # Normalize date range in Methods section to the authoritative protocol values
    # before citation conversion so the Methods text is consistent with PICOS table.
    if review_config is not None:
        _date_start = getattr(review_config, "date_range_start", None)
        _date_end = getattr(review_config, "date_range_end", None)
        if _date_start and _date_end:
            clean_body = _normalize_date_range(clean_body, str(_date_start), str(_date_end))

    # Collapse duplicate DOIs before numbering so the same paper is never
    # assigned two sequential [N] numbers (e.g., included-study citekey and
    # background-SR citekey that both resolve to the same DOI).
    deduped_citation_rows = _dedup_citation_rows_by_doi(list(citation_rows))

    # Convert [AuthorYear] -> [N] numbered citations
    numbered_body, ordered_citation_rows = convert_to_numbered_citations(clean_body, deduped_citation_rows)

    # Prepend title and research question block when provided
    header_block = ""
    # Deduplicate repeated leading H1 title lines from legacy reruns.
    _lines = numbered_body.splitlines()
    if _lines and _lines[0].startswith("# "):
        _title_line = _lines[0]
        _idx = 1
        while _idx < len(_lines) and (_lines[_idx].strip() == "" or _lines[_idx] == _title_line):
            _idx += 1
        numbered_body = "\n".join([_title_line, ""] + _lines[_idx:]).lstrip("\n")

    if research_question or title:
        # Strip any existing leading H1 title block to avoid duplication when re-running finalize.
        # This applies to both:
        # - legacy "title + optional research question" blocks
        # - plain leading H1-only title lines.
        numbered_body = re.sub(r"^(?:# .+\r?\n(?:\s*\r?\n)*)+", "", numbered_body, count=1)
        # Strip any existing title+research-question composite block (in case it survived above).
        _title_block_re = re.compile(
            r"^# .+?\n\n\*\*Research Question:\*\* .+?\n\n---\n\n",
            re.DOTALL,
        )
        numbered_body = _title_block_re.sub("", numbered_body)
        # Strip any orphaned Research Question line that may remain after the H1 was removed
        # (happens when include_rq_block=False on a body that previously had the RQ prefix).
        numbered_body = re.sub(
            r"^\*\*Research Question:\*\* .+?\r?\n\r?\n---\r?\n\r?\n",
            "",
            numbered_body,
        )

        _title = title
        if _title is None and research_question:
            _title = f"A Systematic Review: {research_question}"
        if _title:
            header_block = f"# {_title}\n\n"
        if research_question and include_rq_block:
            header_block += f"**Research Question:** {research_question}\n\n---\n\n"
        if header_block:
            numbered_body = header_block + numbered_body

    _protocol_registered = False
    _registration_id = ""
    _author_name = ""
    if review_config is not None and hasattr(review_config, "protocol"):
        _proto = review_config.protocol
        _protocol_registered = bool(getattr(_proto, "registered", False))
        _registration_id = str(getattr(_proto, "registration_number", "") or "")
    if review_config is not None:
        _author_name = str(getattr(review_config, "author_name", "") or "")
    declarations_section = build_markdown_declarations_section(
        funding=funding,
        coi=coi,
        protocol_registered=_protocol_registered,
        registration_id=_registration_id,
        author_name=_author_name,
    )

    picos_section = ""
    if review_config:
        picos_section = build_picos_table(review_config)

    grade_section = ""
    sof_section = ""
    if grade_assessments:
        grade_section = generate_grade_table(grade_assessments)
        # Cluster per-study GRADE assessments into canonical outcome themes
        # (accuracy, efficiency, safety, cost, implementation) so the Summary
        # of Findings table shows 3-5 meaningful rows rather than 1-18 per-study rows.
        clustered_grade = cluster_grade_assessments_by_theme(grade_assessments)
        sof_table = build_sof_table(clustered_grade if clustered_grade else grade_assessments)
        sof_section = sof_table_to_markdown(sof_table)

    robins_section = ""
    if papers and robins_i_assessments:
        robins_section = build_robins_i_domain_table(papers, robins_i_assessments)
    quality_coverage_section = ""
    if papers and (rob2_assessments or robins_i_assessments or casp_assessments or mmat_assessments):
        quality_coverage_section = build_quality_assessment_coverage_table(
            papers,
            rob2_assessments=rob2_assessments or [],
            robins_i_assessments=robins_i_assessments or [],
            casp_assessments=casp_assessments or [],
            mmat_assessments=mmat_assessments or [],
        )

    # Build paper_id -> citekey label map for CASP/MMAT tables.
    # Primary: use the DOI-based map from the repository (get_paper_id_to_citekey_map).
    # Fallback: try extracting from deduped_citation_rows (which may include paper_id field).
    _pid_to_label: dict[str, str] = dict(paper_id_to_citekey or {})
    for _crow in deduped_citation_rows:
        _ckey = (
            _crow.get("citekey", "") or _crow.get("cite_key", "")
            if isinstance(_crow, dict)
            else getattr(_crow, "citekey", None) or getattr(_crow, "cite_key", "")
        ) or ""
        _cpid = (_crow.get("paper_id", "") if isinstance(_crow, dict) else getattr(_crow, "paper_id", "")) or ""
        if _ckey and _cpid:
            _pid_to_label.setdefault(str(_cpid), str(_ckey))

    casp_section = ""
    if casp_assessments:
        casp_section = generate_casp_table(casp_assessments, paper_id_to_label=_pid_to_label)

    mmat_section = ""
    if mmat_assessments:
        mmat_section = generate_mmat_table(mmat_assessments, paper_id_to_label=_pid_to_label)

    # Inject compact study table into the Results body right after the
    # "### Study Characteristics" heading (PRISMA 2020 Item 19).
    if papers and extraction_records:
        _compact_table = build_compact_study_table(papers, extraction_records)
        if _compact_table:
            _study_char_marker = "### Study Characteristics"
            if _study_char_marker in numbered_body:
                # Find end of the Study Characteristics heading line and insert table.
                _sc_pos = numbered_body.index(_study_char_marker) + len(_study_char_marker)
                # Skip to the next blank line after the heading
                _sc_newline = numbered_body.find("\n", _sc_pos)
                if _sc_newline >= 0:
                    numbered_body = (
                        numbered_body[: _sc_newline + 1]
                        + "\n"
                        + _compact_table
                        + "\n"
                        + numbered_body[_sc_newline + 1 :]
                    )

    study_table_section = ""
    if papers and extraction_records:
        study_table_section = build_study_characteristics_table(
            papers,
            extraction_records,
            pre_filtered_count=failed_count,
            fulltext_paper_ids=fulltext_paper_ids,
        )

    _figure_caption_overrides = {
        "rob_traffic_light": _rob_traffic_caption_for_assessments(
            robins_i_assessments=robins_i_assessments or [],
            casp_assessments=casp_assessments or [],
            mmat_assessments=mmat_assessments or [],
        )
    }
    figures_section = build_markdown_figures_section(
        manuscript_path,
        artifacts,
        caption_overrides=_figure_caption_overrides,
    )

    refs_section = build_markdown_references_section(numbered_body, ordered_citation_rows, numbered=True)

    search_appendix_section = ""
    if search_appendix_path and search_appendix_path.exists():
        raw = search_appendix_path.read_text(encoding="utf-8").strip()
        # Replace top-level title with Appendix C heading (H1 -> H2).
        raw = raw.replace(
            "# Search Strategies Appendix",
            "## Appendix C: Search Strategies",
        )
        # Demote remaining H2 connector subsections to H3 so they nest
        # correctly under the H2 "## Appendix C" heading in the manuscript.
        # Only demote lines that start with exactly "## " (not "### " already).
        import re as _re

        raw = _re.sub(r"^## (?!#)", "### ", raw, flags=_re.MULTILINE)
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
    if quality_coverage_section:
        parts.append(quality_coverage_section)
    if casp_section:
        parts.append(casp_section)
    if mmat_section:
        parts.append(mmat_section)
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
