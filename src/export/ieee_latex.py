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
    """Convert [citekey] or [N] to \\cite{citekey} when valid."""
    num_to_citekey = num_to_citekey or {}

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in citekeys:
            return f"\\cite{{{key}}}"
        if key in num_to_citekey:
            return f"\\cite{{{num_to_citekey[key]}}}"
        return m.group(0)

    return re.sub(r"\[([A-Za-z0-9_]+)\]", repl, text)


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
            if "**Objectives:**" in ln or ln.strip() == "**Objectives:**":
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


def _md_section_to_latex(
    rest: str,
    citekeys: set[str],
    num_to_citekey: dict[str, str] | None = None,
) -> str:
    """Convert markdown body to LaTeX sections."""
    num_to_citekey = num_to_citekey or {}
    parts: list[str] = []
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

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("#### "):
            flush_list()
            title = stripped[5:].strip()
            parts.append(f"\\subsubsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("### "):
            flush_list()
            title = stripped[4:].strip()
            parts.append(f"\\subsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("## "):
            flush_list()
            title = stripped[3:].strip()
            parts.append(f"\\section{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("# "):
            # Top-level title is already in \title{}; skip to avoid duplication.
            # The _extract_title_and_abstract fallback strips the header block, but
            # if any # heading survives (e.g. in appendices), emit as \section.
            flush_list()
            title = stripped[2:].strip()
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

    body = _md_section_to_latex(rest, citekeys, num_to_citekey)
    body = _merge_consecutive_cites(body)

    _FIGURE_CAPTIONS: dict[str, str] = {
        "fig_prisma_flow": "PRISMA 2020 flow diagram illustrating the systematic search and screening process.",
        "fig_rob_traffic_light": "Risk-of-bias traffic-light summary across included studies.",
        "fig_rob2_traffic_light": "Risk-of-bias traffic-light summary (ROBINS-I) across included non-randomized studies.",
        "fig_funnel_plot": "Funnel plot assessing publication bias across pooled effect estimates.",
        "fig_forest_plot": "Forest plot of pooled effect estimates with 95% confidence intervals.",
        "fig_publication_timeline": "Publication timeline of included studies.",
        "fig_geographic_distribution": "Geographic distribution of included studies by country.",
        "fig_evidence_network": (
            "Evidence network of included studies. Nodes represent papers, colored by research cluster. "
            "Edge color denotes relationship type (teal = shared outcome, gold = shared population, "
            "blue = shared intervention, purple = embedding similarity). "
            "Amber rings indicate papers related to identified research gaps."
        ),
        "fig_concept_taxonomy": "Conceptual taxonomy of key constructs across included studies.",
        "fig_conceptual_framework": "Conceptual framework derived from included studies.",
        "fig_methodology_flow": "Methodology flow diagram.",
    }

    fig_section = ""
    if figure_paths:
        fig_section = "\n\\section*{Figures}\n\n"
        for i, path in enumerate(figure_paths, 1):
            name = Path(path).stem
            inc_path = f"figures/{name}" if "/" not in path else path
            caption = _FIGURE_CAPTIONS.get(name, f"Figure {i}.")
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
