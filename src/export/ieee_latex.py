"""Convert Markdown manuscript to IEEE LaTeX."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.quality import GradeSoFTable


def _escape_latex(s: str) -> str:
    """Escape LaTeX special characters in plain text. Preserves \\cite, \\textbf, \\textit."""
    for old, new in [
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
    ]:
        s = s.replace(old, new)
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
    """Convert **bold** and *italic* to LaTeX. Citations already converted."""

    def bold_repl(m: re.Match) -> str:
        inner = m.group(1)
        return f"\\textbf{{{_escape_latex(inner)}}}"

    def italic_repl(m: re.Match) -> str:
        inner = m.group(1)
        return f"\\textit{{{_escape_latex(inner)}}}"

    text = re.sub(r"\*\*(.+?)\*\*", bold_repl, text)
    text = re.sub(r"\*(.+?)\*", italic_repl, text)
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
        if fallback_abstract_start >= 0 and fallback_abstract_end >= fallback_abstract_start and abstract is None:
            abstract = "\n".join(fallback_lines[fallback_abstract_start : fallback_abstract_end + 1]).strip()
        if abstract and first_h2_idx >= 0 and rest == md:
            rest = "\n".join(fallback_lines[first_h2_idx:])

    return title, abstract, rest


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

        if stripped.startswith("### "):
            flush_list()
            title = stripped[4:].strip()
            parts.append(f"\\subsubsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("## "):
            flush_list()
            title = stripped[3:].strip()
            parts.append(f"\\subsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("# "):
            flush_list()
            title = stripped[2:].strip()
            parts.append(f"\\section{{{_escape_latex(title)}}}")
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


def markdown_to_latex(
    md_content: str,
    citekeys: set[str] | None = None,
    figure_paths: list[str] | None = None,
    num_to_citekey: dict[str, str] | None = None,
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

    preamble = r"""\documentclass[journal]{IEEEtran}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{url}

\begin{document}
"""

    if title:
        preamble += f"\\title{{{_escape_latex(title)}}}\n"
    preamble += "\\maketitle\n\n"

    if abstract:
        abstract_conv = _convert_citations(abstract, citekeys, num_to_citekey)
        abstract_conv = _convert_inline_formatting(abstract_conv, citekeys, num_to_citekey)
        abstract_esc = _escape_latex(abstract_conv)
        preamble += "\\begin{abstract}\n"
        preamble += abstract_esc + "\n"
        preamble += "\\end{abstract}\n\n"

    body = _md_section_to_latex(rest, citekeys, num_to_citekey)

    _FIGURE_CAPTIONS: dict[str, str] = {
        "fig_prisma_flow": "PRISMA 2020 flow diagram illustrating the systematic search and screening process.",
        "fig_rob_traffic_light": "Risk-of-bias traffic-light summary across included studies.",
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

    e = _escape_latex
    lines: list[str] = [
        "",
        "\\section*{Appendix: GRADE Summary of Findings}",
        "",
        f"\\textbf{{Topic:}} {e(table.topic)}",
        "",
        "\\begin{longtable}{p{2.8cm}p{0.6cm}p{1.4cm}p{1.4cm}p{1.4cm}p{1.4cm}p{1.4cm}p{1.4cm}p{2.0cm}}",
        "\\caption{GRADE Summary of Findings} \\label{tab:grade_sof} \\\\",
        "\\hline",
        "\\textbf{Outcome} & \\textbf{N} & \\textbf{Design} & \\textbf{Risk of Bias} & "
        "\\textbf{Inconsistency} & \\textbf{Indirectness} & \\textbf{Imprecision} & "
        "\\textbf{Other} & \\textbf{Certainty} \\\\",
        "\\hline",
        "\\endfirsthead",
        "\\hline",
        "\\textbf{Outcome} & \\textbf{N} & \\textbf{Design} & \\textbf{Risk of Bias} & "
        "\\textbf{Inconsistency} & \\textbf{Indirectness} & \\textbf{Imprecision} & "
        "\\textbf{Other} & \\textbf{Certainty} \\\\",
        "\\hline",
        "\\endhead",
        "\\hline",
        "\\endfoot",
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
        lines.append("\\hline")

    lines.append("\\end{longtable}")
    lines.append("")
    return "\n".join(lines)
