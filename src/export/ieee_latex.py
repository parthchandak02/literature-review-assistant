"""Convert Markdown manuscript to IEEE LaTeX."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pylatexenc.latexencode import UnicodeToLatexEncoder

if TYPE_CHECKING:
    from src.models.quality import GradeSoFTable

logger = logging.getLogger(__name__)

# Module-level encoder instance (avoids re-initialisation on every call).
# non_ascii_only=True: only converts chars > 127, leaving ASCII LaTeX commands
# we already emitted (\\&, ---,  `` etc.) completely untouched.
_LATEX_ENCODER = UnicodeToLatexEncoder(
    non_ascii_only=True,
    replacement_latex_protection="braces",
)


def _escape_latex(s: str) -> str:
    """Escape LaTeX special characters in plain text.

    Processing order matters:
      1. Protect already-converted LaTeX commands (\\cite{}, \\textbf{}, etc.)
         using null-byte placeholders so their arguments survive escaping.
      2. Convert typographic Unicode punctuation that has a preferred
         IEEEtran-specific ASCII form (--- for em-dash, -- for en-dash, etc.).
         We handle these manually rather than delegating to pylatexenc because
         pylatexenc produces \\textemdash{} / \\textendash{} which, while valid,
         differ from the de-facto IEEEtran convention.
      3. Escape LaTeX special chars (&, %, $, #, _).
      4. Degree sign: uses math mode and must be inserted AFTER $ is escaped.
      5. pylatexenc fallback: converts ALL remaining non-ASCII chars (accented
         author names, Greek symbols, etc.) to valid LaTeX sequences.  This is
         the sustainable alternative to maintaining a manual enumeration list.
      6. Last-resort guard: any char still > ASCII 126 after pylatexenc (e.g.
         Arabic script which has no pdflatex representation) is replaced with
         [?] and a warning is logged so the compile never fails silently.
      7. Restore protected LaTeX commands.
    """
    protected: list[str] = []

    def _protect(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"\x00P{len(protected) - 1}\x00"

    # Step 1: Shield command+argument pairs before escaping special chars.
    s = re.sub(
        r"\\(?:cite|textbf|textit|emph|ref|label|url|href)\{[^}]*\}",
        _protect,
        s,
    )

    # Step 2: Targeted typographic substitutions with IEEEtran-preferred forms.
    # Accented Latin letters (a-tilde, e-acute, etc.) are intentionally NOT
    # listed here -- \usepackage[utf8]{inputenc} handles them transparently in
    # pdflatex, and pylatexenc (step 5) covers any that slip through.
    for old, new in [
        ("\u2014", "---"),  # em-dash
        ("\u2013", "--"),  # en-dash
        ("\u2019", "'"),  # right single quotation mark
        ("\u2018", "`"),  # left single quotation mark
        ("\u201c", "``"),  # left double quotation mark
        ("\u201d", "''"),  # right double quotation mark
        ("\u2011", "-"),  # non-breaking hyphen
    ]:
        s = s.replace(old, new)

    # Step 3: LaTeX special chars.
    for old, new in [
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
    ]:
        s = s.replace(old, new)

    # Step 4: Degree sign -- math mode, inserted AFTER $ is escaped so the new
    # $ delimiters are not themselves re-escaped by step 3.
    s = s.replace("\u00b0", "$^{\\circ}$")

    # Step 4.5: Strip characters in CJK Unicode blocks before pylatexenc.
    # pdflatex cannot render CJK without specialised packages (CJKutf8, XeLaTeX,
    # etc.) which are not part of the IEEEtran template used here.  Silently
    # removing CJK characters is cleaner than the [?] substitution that would
    # otherwise appear in author names and titles of East-Asian-language papers.
    # Ranges: CJK Unified Ideographs (4E00-9FFF), Extension A (3400-4DBF),
    # CJK Compatibility Ideographs (F900-FAFF), Bopomofo (3100-312F),
    # CJK Radicals Supplement (2E80-2EFF), Kangxi Radicals (2F00-2FDF),
    # CJK Symbols and Punctuation (3000-303F), Enclosed CJK (3200-32FF).
    _CJK_RE = re.compile(
        r"[\u2e80-\u2eff\u2f00-\u2fdf\u3000-\u303f\u3100-\u312f"
        r"\u3200-\u32ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
    )
    if _CJK_RE.search(s):
        logger.debug("_escape_latex: stripped CJK characters from string (not renderable in pdflatex)")
        s = _CJK_RE.sub("", s)
        # Remove any resulting runs of double-spaces
        s = re.sub(r"  +", " ", s).strip()

    # Step 5: pylatexenc fallback for all remaining non-ASCII characters.
    # non_ascii_only=True means ASCII chars we emitted in steps 2-4 (---, \\&,
    # etc.) are left completely untouched.
    s = _LATEX_ENCODER.unicode_to_latex(s)

    # Step 6: Last-resort guard -- replace any char still above ASCII 126 with
    # [?] and log a warning so the compile never fails silently.
    def _replace_unknown(m: re.Match) -> str:
        ch = m.group(0)
        logger.warning(
            "No LaTeX representation for U+%04X (%s); substituted [?]",
            ord(ch),
            ch,
        )
        return "[?]"

    s = re.sub(r"[^\x00-\x7e]", _replace_unknown, s)

    # Step 7: Restore protected LaTeX commands.
    for i, orig in enumerate(protected):
        s = s.replace(f"\x00P{i}\x00", orig)
    return s


def _convert_citations(
    text: str,
    citekeys: set[str],
    num_to_citekey: dict[str, str] | None = None,
) -> str:
    """Convert [citekey] or [N] to \\cite{citekey} when valid.

    Also handles comma-separated citekey lists emitted by the writing LLM:
        [YangKun2020, Keaton2019, Leigh2025]  ->  \\cite{YangKun2020,Keaton2019,Leigh2025}

    These lists appear when the LLM groups several citations in one bracket instead
    of using individual \\cite{} calls. The regex below matches the list pattern first
    (all entries must look like citekeys and at least one must be known) so the
    per-key handler can then clean up any remaining single-key brackets.
    """
    num_to_citekey = num_to_citekey or {}
    _num_key_map: dict[str, str] = {str(k).strip(): v for k, v in num_to_citekey.items()}
    # Remove unresolved placeholder markers from final LaTeX prose.
    text = text.replace("[CITATION_NEEDED]", "(citation unavailable)")
    text = re.sub(r"\[\s*Ref\d+\s*\]", "(citation unavailable)", text)
    text = re.sub(r"\bRef\d+\b", "(citation unavailable)", text)
    text = re.sub(r"\[\s*Paper_[A-Za-z0-9_\-]+\s*\]", "(citation unavailable)", text)
    text = re.sub(r"\bPaper_[A-Za-z0-9_\-]+\b", "(citation unavailable)", text)

    def _norm_token(token: str) -> str:
        # Canonical key for forgiving lookup (spaces/punctuation-insensitive).
        return re.sub(r"[^A-Za-z0-9]", "", token).lower()

    # Canonical lookup maps to resolve legacy/malformed tokens such as
    # "Engineering Inclusiv" -> "EngineeringInclusiv".
    _norm_citekey_map: dict[str, str] = {}
    for ck in citekeys:
        _norm_citekey_map[_norm_token(ck)] = ck
    _norm_num_key_map: dict[str, str] = {}
    for key, val in _num_key_map.items():
        _norm_num_key_map[_norm_token(key)] = val

    def _resolve_token(token: str) -> str | None:
        stripped = token.strip()
        if not stripped:
            return None
        if stripped in citekeys:
            return stripped
        if stripped in _num_key_map:
            return _num_key_map[stripped]
        norm = _norm_token(stripped)
        if norm in _norm_citekey_map:
            return _norm_citekey_map[norm]
        if norm in _norm_num_key_map:
            return _norm_num_key_map[norm]
        return None

    def _looks_like_citation_placeholder(token: str) -> bool:
        stripped = token.strip()
        return bool(
            re.fullmatch(r"Ref\d+", stripped)
            or re.fullmatch(r"Paper_[A-Za-z0-9_\-]+", stripped)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-']+\d{4}[a-z]?", stripped)
        )

    # Pass 1: comma-separated bracket lists -> \cite{key1,key2,...}
    # Use a permissive pattern so one malformed key does not block valid keys.
    _list_re = re.compile(r"\[([^\[\]\n]*,[^\[\]\n]*)\]")

    def list_repl(m: re.Match) -> str:
        raw_keys = [k.strip() for k in m.group(1).split(",")]
        # Resolve each key; skip unknown keys, dedupe while preserving order.
        resolved: list[str] = []
        seen_resolved: set[str] = set()
        for k in raw_keys:
            rk = _resolve_token(k)
            if rk and rk not in seen_resolved:
                resolved.append(rk)
                seen_resolved.add(rk)
        if resolved:
            return f"\\cite{{{','.join(resolved)}}}"
        if any(_looks_like_citation_placeholder(k) for k in raw_keys):
            return "(citation unavailable)"
        return m.group(0)  # Nothing resolved -- leave as-is.

    text = _list_re.sub(list_repl, text)

    # Pass 1.5: numeric citation lists/singles ([1], [2, 3]) via num_to_citekey map.
    def numeric_repl(m: re.Match) -> str:
        raw_nums = [n.strip() for n in m.group(1).split(",")]
        resolved: list[str] = []
        seen: set[str] = set()
        for n in raw_nums:
            rk = _resolve_token(n)
            if rk and rk not in seen:
                resolved.append(rk)
                seen.add(rk)
        if resolved:
            return f"\\cite{{{','.join(resolved)}}}"
        return m.group(0)

    text = re.sub(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]", numeric_repl, text)

    # Pass 2: single-key brackets -> \cite{key}
    def repl(m: re.Match) -> str:
        key = m.group(1)
        resolved = _resolve_token(key)
        if resolved:
            return f"\\cite{{{resolved}}}"
        if _looks_like_citation_placeholder(key):
            return "(citation unavailable)"
        return m.group(0)

    return re.sub(r"\[([A-Za-z0-9_\-:' ]+)\]", repl, text)


def _convert_inline_formatting(
    text: str,
    citekeys: set[str],
    num_to_citekey: dict[str, str] | None = None,
) -> str:
    """Convert **bold**, *italic*, _italic_, and `code` to LaTeX. Citations already converted."""

    def bold_repl(m: re.Match) -> str:
        inner = m.group(1)
        return f"\\textbf{{{_escape_latex(inner)}}}"

    def italic_repl(m: re.Match) -> str:
        inner = m.group(1)
        return f"\\textit{{{_escape_latex(inner)}}}"

    def code_repl(m: re.Match) -> str:
        inner = m.group(1)
        return f"\\texttt{{{_escape_latex(inner)}}}"

    # Code spans must be processed before bold/italic to avoid misinterpreting
    # asterisks or underscores inside backtick-delimited spans.
    text = re.sub(r"`([^`]+)`", code_repl, text)
    text = re.sub(r"\*\*(.+?)\*\*", bold_repl, text)
    text = re.sub(r"\*(.+?)\*", italic_repl, text)
    # Handle _text_ italic, guarded by word boundaries so underscores inside
    # identifiers (e.g. fig_name, non_randomized) are not converted.
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", italic_repl, text)
    return text


def _extract_title_and_abstract(md: str) -> tuple[str | None, str | None, str]:
    """Extract title and abstract, return (title, abstract, rest).

    Supports two formats:
    1. **Title:** and **Abstract** markers (legacy)
    2. Structured abstract: first # line as title, **Objectives:** through **Keywords:**
       before first ## heading (e.g. ## Introduction)
    """
    title = None
    abstract_lines: list[str] = []
    rest_lines: list[str] = []
    in_abstract = False
    abstract_done = False

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("**Title:**"):
            title = line.replace("**Title:**", "").strip()
            i += 1
            continue
        if line.strip() == "**Abstract**":
            in_abstract = True
            i += 1
            continue
        if in_abstract and not abstract_done:
            if line.strip() == "" and abstract_lines:
                abstract_done = True
                rest_lines = lines[i + 1 :]
                break
            abstract_lines.append(line)
            i += 1
            continue
        if not in_abstract:
            rest_lines.append(line)
        i += 1

    abstract = "\n".join(abstract_lines).strip() if abstract_lines else None
    rest = "\n".join(rest_lines) if rest_lines else md

    # Fallback: structured abstract format (Objectives: ... Keywords: before ## Introduction)
    if abstract is None or title is None:
        fallback_lines = md.split("\n")
        fallback_title = None
        fallback_abstract_start = -1
        fallback_abstract_end = -1
        first_h2_idx = -1
        for idx, ln in enumerate(fallback_lines):
            if ln.strip().startswith("# ") and not ln.strip().startswith("## "):
                fallback_title = ln.strip()[2:].strip()
                if fallback_title.endswith("..."):
                    fallback_title = fallback_title[:-3].strip()
            if (
                "**Background:**" in ln
                or ln.strip() == "**Background:**"
                or "**Objectives:**" in ln
                or ln.strip() == "**Objectives:**"
            ) and fallback_abstract_start < 0:
                fallback_abstract_start = idx
            if "**Keywords:**" in ln or ln.strip().startswith("**Keywords:**"):
                fallback_abstract_end = idx
            if ln.strip().startswith("## ") and first_h2_idx < 0:
                first_h2_idx = idx
        if fallback_title and title is None:
            title = fallback_title
        # Structured abstracts often end with **Conclusion:** rather than
        # **Keywords:**, leaving fallback_abstract_end unset. Fall back to
        # using everything up to (but not including) the first ## heading.
        if fallback_abstract_start >= 0 and fallback_abstract_end < 0 and first_h2_idx > fallback_abstract_start:
            fallback_abstract_end = first_h2_idx - 1
        if fallback_abstract_start >= 0 and fallback_abstract_end >= fallback_abstract_start and abstract is None:
            abstract = "\n".join(fallback_lines[fallback_abstract_start : fallback_abstract_end + 1]).strip()
        if abstract and first_h2_idx >= 0 and rest == md:
            rest = "\n".join(fallback_lines[first_h2_idx:])
        # Strip the "# Title\n\n**Research Question:** ...\n\n---\n\n" header block
        # from rest when it was not consumed by the abstract extractor above.
        # Without this the title line becomes a spurious \section{} in the body.
        if fallback_title and rest == md:
            rest = re.sub(
                r"^# [^\n]+\n\n(?:\*\*Research Question:\*\*[^\n]*\n\n)?---\n\n",
                "",
                rest,
                flags=re.DOTALL,
            )

    return title, abstract, rest


def _is_table_separator_row(row: str) -> bool:
    """Return True for |---|---| alignment rows used in markdown tables."""
    return bool(re.match(r"^\|[\s\-\|:]+\|$", row))


def _convert_md_table_to_latex(
    table_lines: list[str],
    citekeys: set[str],
    num_to_citekey: dict[str, str],
) -> list[str]:
    """Convert a list of markdown table lines to a LaTeX tabular block.

    Separator rows (|---|) are detected and used only to identify the header;
    they are not emitted as data rows.
    """
    # Separate header, separator, and body rows
    header_row: list[str] | None = None
    body_rows: list[list[str]] = []
    for row in table_lines:
        if _is_table_separator_row(row):
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if header_row is None:
            header_row = cells
        else:
            body_rows.append(cells)

    if header_row is None:
        return []

    n_cols = len(header_row)
    # Pad body rows that have fewer cells than the header
    for r in body_rows:
        while len(r) < n_cols:
            r.append("")

    # tabularx with X columns: auto-fills \textwidth equally regardless of
    # column count. No arithmetic needed -- works for 2-col or 11-col tables
    # without any per-review tuning.
    col_spec = " ".join([">{\\raggedright\\arraybackslash}X"] * n_cols)

    def convert_cell(cell: str) -> str:
        # Strip HTML tags that leak from upstream extraction data (e.g. <i>, <b>,
        # <sub>, <sup>, <em>) into cell content. LaTeX cannot render raw HTML and
        # it triggers undefined command errors during pdflatex compilation.
        cell = re.sub(r"<[^>]+>", "", cell)
        # Strip leaked markdown heading markers (##, ###, #) that sometimes
        # appear when study abstracts are used as cell content verbatim.
        cell = re.sub(r"^#{1,6}\s*", "", cell)
        # Strip raw URLs that would cause line-breaking issues in narrow columns.
        cell = re.sub(r"https?://\S+", "", cell)
        conv = _convert_inline_formatting(
            _convert_citations(cell, citekeys, num_to_citekey),
            citekeys,
            num_to_citekey,
        )
        result = _escape_latex(conv)
        # Break semicolon-delimited list items (.; ) onto separate lines within
        # the p{} column so multi-item cells (e.g. PICOS criteria) are readable.
        result = result.replace(".; ", ".\\\\ ")
        return result

    # IEEEtran requires table* for two-column-spanning tables and strongly
    # favors top placement ([!t]). No caption is emitted because the section
    # writer does not supply table titles to this converter; IEEEtran will still
    # number the float via the table* counter.
    #
    # For wide tables (>5 cols) reduce inter-column padding so the 9-11 column
    # GRADE/MMAT/Appendix B tables do not overflow the page margins.
    tabcolsep_override = ["\\setlength{\\tabcolsep}{4pt}"] if n_cols > 5 else []
    result: list[str] = [
        "\\begin{table*}[!t]",
        "\\centering",
        "\\renewcommand{\\arraystretch}{1.15}",
        *tabcolsep_override,
        f"\\small\\begin{{tabularx}}{{\\textwidth}}{{{col_spec}}}",
        "\\toprule",
    ]
    # Header row in bold
    header_cells = [f"\\textbf{{{convert_cell(c)}}}" for c in header_row]
    result.append(" & ".join(header_cells) + " \\\\")
    result.append("\\midrule")
    for row in body_rows:
        result.append(" & ".join(convert_cell(c) for c in row) + " \\\\")
    result.extend(["\\bottomrule", "\\end{tabularx}", "\\end{table*}"])
    return result


def _strip_section_block_markers(text: str) -> str:
    """Remove deterministic writing boundary markers from export body."""
    text = re.sub(r"(?m)^\s*<!--\s*SECTION_BLOCK:[^>]+-->\s*\n?", "", text)
    return re.sub(r"\s*<!--\s*SECTION_BLOCK:[^>]+-->\s*", "\n\n", text)


def _normalize_subsection_heading_layout(text: str) -> str:
    """Normalize malformed subsection markdown before LaTeX conversion.

    Handles:
    - inline heading/body run-ons: `### Heading Body...`
    - multiple headings collapsed on one line
    - split heading lines: `### Risk of` then `Bias Assessment`
    """
    text = re.sub(r"\s+(#{3,4}\s+)", r"\n\n\1", text)
    heading_re = re.compile(r"^(#{3,6})\s+(.+)$")
    title_token_re = re.compile(r"^[A-Z][A-Za-z0-9()/:,\-']*$")
    sentence_start_re = re.compile(r"^(The|This|These|We|Our|In|Across|To|A|An|Studies|Study|Data)\b")
    connector_tail = {"and", "or", "of", "for", "to", "with"}
    sentence_starters = {"the", "this", "these", "we", "our", "in", "across", "to", "a", "an", "studies", "study", "data"}

    def _looks_title_fragment(s: str) -> bool:
        words = s.strip().split()
        if not words or len(words) > 5:
            return False
        return all(title_token_re.match(w) or w.lower() in connector_tail for w in words)

    def _starts_with_title_prefix_then_sentence(s: str) -> bool:
        words = s.strip().split()
        if len(words) < 3:
            return False
        if not (title_token_re.match(words[0]) and title_token_re.match(words[1])):
            return False
        remainder = " ".join(words[2:])
        return bool(sentence_start_re.match(remainder))

    out: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = heading_re.match(line.strip())
        if m:
            level = m.group(1)
            tail = m.group(2).strip()
            next_idx = i + 1
            while next_idx < len(lines) and not lines[next_idx].strip():
                next_idx += 1
            next_line = lines[next_idx].strip() if next_idx < len(lines) else ""
            if next_line and not next_line.startswith("#"):
                tail_words = tail.split()
                if tail_words and tail_words[-1].lower() in connector_tail:
                    nxt_words = next_line.split()
                    consumed = 0
                    for j, w in enumerate(nxt_words):
                        if (
                            j > 0
                            and w.lower() in sentence_starters
                            and j + 1 < len(nxt_words)
                            and nxt_words[j + 1][:1].islower()
                        ):
                            break
                        if title_token_re.match(w):
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
                            out.append(line)
                            out.append("")
                            out.append(body_rest)
                            i = next_idx + 1
                            continue
                        out.append(line)
                        i = next_idx + 1
                        continue
                if (tail_words and tail_words[-1].lower() in connector_tail and _looks_title_fragment(next_line)) or (
                    len(tail_words) <= 3 and _looks_title_fragment(next_line) and not sentence_start_re.match(next_line)
                ):
                    line = f"{level} {tail} {next_line}".strip()
                    i = next_idx + 1
            words = line.strip().split()
            if len(words) >= 4 and words[0].startswith("#"):
                split_found = False
                for idx in range(3, min(len(words), 12)):
                    left_words = words[1:idx]
                    right = " ".join(words[idx:]).strip()
                    left_ok = all(title_token_re.match(w) or w.lower() in connector_tail for w in left_words)
                    if not left_ok:
                        continue
                    right_lower = right.lower()
                    if (
                        sentence_start_re.match(right)
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
                    ) and not _looks_title_fragment(right) and not _starts_with_title_prefix_then_sentence(right):
                        out.append(f"{words[0]} {' '.join(left_words)}")
                        out.append("")
                        out.append(right)
                        split_found = True
                        break
                if not split_found:
                    out.append(line)
            else:
                out.append(line)
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def _md_section_to_latex(
    rest: str,
    citekeys: set[str],
    num_to_citekey: dict[str, str] | None = None,
) -> str:
    """Convert markdown body to LaTeX sections."""
    num_to_citekey = num_to_citekey or {}
    parts: list[str] = []
    rest = _normalize_subsection_heading_layout(_strip_section_block_markers(rest))
    lines = rest.split("\n")
    i = 0
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_items, parts
        if list_items:
            parts.append("\\begin{itemize}")
            for item in list_items:
                item_conv = _convert_inline_formatting(
                    _convert_citations(item.strip(), citekeys, num_to_citekey),
                    citekeys,
                    num_to_citekey,
                )
                parts.append(f"  \\item {_escape_latex(item_conv)}")
            parts.append("\\end{itemize}")
            list_items = []

    def _split_inline_subheading(line_text: str) -> tuple[str, str, str] | None:
        """Return (level, title, body) for inline heading+body lines.

        Example:
          "### Information Sources The search was conducted..."
        -> ("###", "Information Sources", "The search was conducted...")
        """
        _heading_re = re.compile(r"^(#{3,6})\s+(.+)$")
        _sentence_start_re = re.compile(r"^(The|This|These|We|Our|In|Across|To|A|An|Studies|Study|Data)\b")
        _title_token_re = re.compile(r"^[A-Z][A-Za-z0-9()/:,\-']*$")
        _connector_tail = {"and", "of", "for", "to", "with"}
        _sentence_starters = {"the", "this", "these", "we", "our", "in", "across", "to", "a", "an", "studies", "study", "data"}

        def _looks_title_fragment(s: str) -> bool:
            words = s.strip().split()
            if not words or len(words) > 5:
                return False
            return all(_title_token_re.match(w) or w.lower() in _connector_tail for w in words)

        m = _heading_re.match(line_text.strip())
        if not m:
            return None
        level = m.group(1)
        tail = m.group(2).strip()
        if not tail:
            return None
        words = tail.split()
        if len(words) < 4:
            return None
        for idx in range(2, min(len(words), 12)):
            left_words = words[:idx]
            right_words = words[idx:]
            left_ok = all(
                _title_token_re.match(w) or w.lower() in {"and", "of", "for", "to", "with"} for w in left_words
            )
            if not left_ok:
                continue
            right = " ".join(right_words).strip()
            # If the split point ends on a connector and the right side begins
            # with a short title fragment, move that fragment into the heading.
            if (
                left_words
                and left_words[-1].lower() in _connector_tail
                and right_words
                and not _sentence_start_re.match(right)
            ):
                consumed = 0
                for pos, w in enumerate(right_words):
                    # Stop if heading fragment starts to absorb body prose, e.g.
                    # "Findings This section ..." -> keep "This section ..." as body.
                    if (
                        pos > 0
                        and w.lower() in _sentence_starters
                        and pos + 1 < len(right_words)
                        and right_words[pos + 1][:1].islower()
                    ):
                        break
                    if _title_token_re.match(w):
                        consumed += 1
                        if consumed >= 3:
                            break
                        continue
                    break
                if 0 < consumed < len(right_words):
                    merged_left = left_words + right_words[:consumed]
                    merged_right = " ".join(right_words[consumed:]).strip()
                    if merged_right:
                        return level, " ".join(merged_left), merged_right
            if (_sentence_start_re.match(right) or (right and right[0].isupper() and any(c in right for c in ".,"))) and (
                not _looks_title_fragment(right)
            ):
                return level, " ".join(left_words), right
        return None

    def _sanitize_heading_title(raw_title: str) -> str:
        """Normalize malformed heading titles and strip citation leakage."""
        title = raw_title.strip()
        # Remove inline numeric citation clusters that should not appear in headings.
        title = re.sub(r"\s*(?:\[\s*\d+\s*\]\s*)+", " ", title)
        title = re.sub(r"\s*\\cite\{[^}]+\}", " ", title)
        # Cut at sentence punctuation when run-on prose leaked into heading text.
        title = re.split(r"[.;:!?]\s+", title, maxsplit=1)[0]
        title = re.sub(r"\s{2,}", " ", title).strip(" -:,;.")
        # Guardrail: overly long headings are usually sentence spillover.
        words = title.split()
        if len(words) > 14:
            title = " ".join(words[:14]).strip()
        # Trim trailing connectors that indicate a broken split.
        title = re.sub(r"\b(and|of|for|to|with|due)\s*$", "", title, flags=re.IGNORECASE).strip()
        return title

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        inline_heading = _split_inline_subheading(stripped)

        if inline_heading and inline_heading[0] == "####":
            flush_list()
            _, title, body_text = inline_heading
            title = _sanitize_heading_title(title)
            parts.append(f"\\subsubsection{{{_escape_latex(title)}}}")
            parts.append("")
            conv = _convert_inline_formatting(
                _convert_citations(body_text, citekeys, num_to_citekey),
                citekeys,
                num_to_citekey,
            )
            parts.append(_escape_latex(conv))
            parts.append("")
        elif inline_heading and inline_heading[0] == "###":
            flush_list()
            _, title, body_text = inline_heading
            title = _sanitize_heading_title(title)
            parts.append(f"\\subsection{{{_escape_latex(title)}}}")
            parts.append("")
            conv = _convert_inline_formatting(
                _convert_citations(body_text, citekeys, num_to_citekey),
                citekeys,
                num_to_citekey,
            )
            parts.append(_escape_latex(conv))
            parts.append("")
        elif stripped.startswith("#### "):
            flush_list()
            title = _sanitize_heading_title(stripped[5:].strip())
            parts.append(f"\\subsubsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("### "):
            flush_list()
            title = _sanitize_heading_title(stripped[4:].strip())
            parts.append(f"\\subsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("## "):
            flush_list()
            title = _sanitize_heading_title(stripped[3:].strip())
            parts.append(f"\\section{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("# "):
            # Top-level title is already in \title{}; skip to avoid duplication.
            # The _extract_title_and_abstract fallback strips the header block, but
            # if any # heading survives (e.g. in appendices), emit as \section.
            flush_list()
            title = _sanitize_heading_title(stripped[2:].strip())
            parts.append(f"\\section{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped == "---":
            # Markdown horizontal rules are section separators; skip silently
            flush_list()
        elif stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            # Accumulate all consecutive table rows
            table_lines = [stripped]
            while i + 1 < len(lines) and lines[i + 1].strip().startswith("|") and lines[i + 1].strip().endswith("|"):
                i += 1
                table_lines.append(lines[i].strip())
            table_latex = _convert_md_table_to_latex(table_lines, citekeys, num_to_citekey)
            parts.extend(table_latex)
            parts.append("")
        elif stripped.startswith("*   ") or stripped.startswith("-   "):
            content = stripped[4:].strip()
            list_items.append(content)
        elif stripped.startswith("* ") or stripped.startswith("- "):
            content = stripped[2:].strip()
            list_items.append(content)
        elif stripped == "":
            flush_list()
            if parts and parts[-1] != "":
                parts.append("")
        else:
            flush_list()
            # Skip citation conversion for References section lines ([1] Author, "Title"...)
            if re.match(r"^\[\d+\]\s+[A-Za-z]", stripped):
                parts.append(_escape_latex(stripped))
            else:
                conv = _convert_inline_formatting(
                    _convert_citations(stripped, citekeys, num_to_citekey),
                    citekeys,
                    num_to_citekey,
                )
                parts.append(_escape_latex(conv))
        i += 1

    flush_list()
    return "\n".join(parts)


def _merge_consecutive_cites(text: str) -> str:
    """Merge adjacent \\cite{A}, \\cite{B} sequences into \\cite{A,B}.

    The cite package only compresses citation ranges (e.g. [1]-[3]) when all
    keys are listed in a single \\cite{} command. This post-processor collapses
    any run of comma-separated consecutive \\cite{} calls into one.
    """

    def repl(m: re.Match) -> str:
        keys = re.findall(r"\\cite\{([^}]+)\}", m.group(0))
        return f"\\cite{{{','.join(keys)}}}"

    return re.sub(r"\\cite\{[^}]+\}(?:,\s*\\cite\{[^}]+\})+", repl, text)


def markdown_to_latex(
    md_content: str,
    citekeys: set[str] | None = None,
    figure_paths: list[str] | None = None,
    num_to_citekey: dict[str, str] | None = None,
    author_name: str = "",
) -> str:
    """Convert markdown manuscript to IEEE LaTeX.

    Args:
        md_content: Full markdown manuscript text.
        citekeys: Set of valid citekeys for citation conversion.
        figure_paths: Optional list of figure filenames for \\includegraphics.
    """
    citekeys = citekeys or set()
    figure_paths = figure_paths or []

    title, abstract, rest = _extract_title_and_abstract(md_content)

    # Strip the markdown Figures section -- LaTeX figures are emitted separately
    # via \includegraphics from figure_paths, so the markdown image embeds would
    # otherwise appear as garbled literal text in the body.
    rest = re.sub(
        r"\n\n---\n\n## Figures\b.*?(?=\n\n---\n\n|\Z)",
        "",
        rest,
        flags=re.DOTALL,
    )

    # Strip the markdown References section -- BibTeX (\bibliography{references})
    # handles the reference list. Keeping the manually-formatted [1] Author... entries
    # in the body would produce a duplicate reference list in the compiled PDF.
    rest = re.sub(r"\n## References\b.*", "", rest, flags=re.DOTALL)

    preamble = r"""\documentclass[journal]{IEEEtran}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{textcomp}
\usepackage{cite}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{tabularx}
\usepackage{array}
\usepackage{hyperref}

\begin{document}
"""

    if title:
        preamble += f"\\title{{{_escape_latex(title)}}}\n"
    if author_name:
        preamble += f"\\author{{{_escape_latex(author_name)}}}\n"
    preamble += "\\maketitle\n\n"

    if abstract:
        abstract_conv = _convert_citations(abstract, citekeys, num_to_citekey)
        abstract_conv = _convert_inline_formatting(abstract_conv, citekeys, num_to_citekey)
        abstract_esc = _escape_latex(abstract_conv)
        preamble += "\\begin{abstract}\n"
        preamble += abstract_esc + "\n"
        preamble += "\\end{abstract}\n\n"
    else:
        logger.warning("markdown_to_latex: abstract block missing; LaTeX output will omit \\begin{abstract}.")

    body = _md_section_to_latex(rest, citekeys, num_to_citekey)
    body = _merge_consecutive_cites(body)

    from src.export.markdown_refs import FIGURE_DEFS

    _artifact_to_caption = {artifact_key: caption for artifact_key, caption in FIGURE_DEFS}
    _stem_to_artifact = {
        "fig_prisma_flow": "prisma_diagram",
        "fig_rob_traffic_light": "rob_traffic_light",
        "fig_rob2_traffic_light": "rob2_traffic_light",
        "fig_funnel_plot": "fig_funnel_plot",
        "fig_forest_plot": "fig_forest_plot",
        "fig_publication_timeline": "timeline",
        "fig_geographic_distribution": "geographic",
        "fig_evidence_network": "evidence_network",
        "fig_concept_taxonomy": "concept_taxonomy",
        "fig_conceptual_framework": "conceptual_framework",
        "fig_methodology_flow": "methodology_flow",
    }

    fig_section = ""
    if figure_paths:
        fig_section = "\n\\section*{Figures}\n\n"
        for i, path in enumerate(figure_paths, 1):
            name = Path(path).stem
            inc_path = f"figures/{name}" if "/" not in path else path
            artifact_key = _stem_to_artifact.get(name, "")
            caption = _artifact_to_caption.get(artifact_key, f"Figure {i}.")
            fig_section += "\\begin{figure}[htbp]\n"
            fig_section += "  \\centering\n"
            fig_section += f"  \\includegraphics[width=0.9\\columnwidth]{{{inc_path}}}\n"
            fig_section += f"  \\caption{{{_escape_latex(caption)}}}\n"
            fig_section += "\\end{figure}\n\n"

    bib_section = "\n\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n"
    return preamble + body + fig_section + bib_section + "\n\\end{document}\n"


def render_grade_sof_latex(table: GradeSoFTable) -> str:
    """Render a GradeSoFTable as a LaTeX longtable appendix section.

    The returned string is self-contained and can be appended to the IEEE
    LaTeX document before the bibliography.
    """

    _CERT_SYMBOL: dict[str, str] = {
        "high": "HIGH",
        "moderate": "MODERATE",
        "low": "LOW",
        "very_low": "VERY LOW",
    }

    # Column spec uses relative \textwidth fractions so the table adapts to
    # any page size without hardcoded centimetre values. Fractions sum to ~1.0:
    #   Outcome (0.18) + N (0.05) + Design (0.10) + RoB (0.10) +
    #   Inconsistency (0.10) + Indirectness (0.10) + Imprecision (0.10) +
    #   Other (0.10) + Certainty+Effect (0.15) = 0.98 (2% slack for colsep)
    _COL_SPEC = (
        "p{0.18\\textwidth}"
        "p{0.05\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.10\\textwidth}"
        "p{0.15\\textwidth}"
    )

    e = _escape_latex
    _HEADER_ROW = (
        "\\textbf{Outcome} & \\textbf{N} & \\textbf{Design} & \\textbf{Risk of Bias} & "
        "\\textbf{Inconsistency} & \\textbf{Indirectness} & \\textbf{Imprecision} & "
        "\\textbf{Other} & \\textbf{Certainty} \\\\"
    )
    lines: list[str] = [
        "",
        "\\section*{Appendix: GRADE Summary of Findings}",
        "",
        f"\\textbf{{Topic:}} {e(table.topic)}",
        "",
        "\\setlength{\\tabcolsep}{4pt}",
        f"\\begin{{longtable}}{{{_COL_SPEC}}}",
        "\\caption{GRADE Summary of Findings} \\label{tab:grade_sof} \\\\",
        "\\toprule",
        _HEADER_ROW,
        "\\midrule",
        "\\endfirsthead",
        "\\toprule",
        _HEADER_ROW,
        "\\midrule",
        "\\endhead",
        "\\midrule",
        "\\endfoot",
        "\\bottomrule",
        "\\endlastfoot",
    ]

    for row in table.rows:
        cert_label = _CERT_SYMBOL.get(
            row.certainty.value if hasattr(row.certainty, "value") else str(row.certainty), str(row.certainty).upper()
        )
        cells = [
            e(row.outcome_name),
            str(row.n_studies),
            e(row.study_design),
            e(row.risk_of_bias),
            e(row.inconsistency),
            e(row.indirectness),
            e(row.imprecision),
            e(row.other_considerations),
            f"\\textbf{{{cert_label}}}",
        ]
        lines.append(" & ".join(cells) + " \\\\")

    lines.append("\\end{longtable}")
    lines.append("")
    return "\n".join(lines)
