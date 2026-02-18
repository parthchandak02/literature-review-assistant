"""Convert Markdown manuscript to IEEE LaTeX."""

from __future__ import annotations

import re
from pathlib import Path


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


def _convert_citations(text: str, citekeys: set[str]) -> str:
    """Convert [citekey] to \\cite{citekey} when citekey is valid."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in citekeys:
            return f"\\cite{{{key}}}"
        return m.group(0)

    return re.sub(r"\[([A-Za-z0-9_]+)\]", repl, text)


def _convert_inline_formatting(text: str, citekeys: set[str]) -> str:
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
    """Extract title and abstract, return (title, abstract, rest)."""
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
    return title, abstract, rest


def _md_section_to_latex(rest: str, citekeys: set[str]) -> str:
    """Convert markdown body to LaTeX sections."""
    parts: list[str] = []
    lines = rest.split("\n")
    i = 0
    in_list = False
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_items, parts
        if list_items:
            parts.append("\\begin{itemize}")
            for item in list_items:
                item_conv = _convert_inline_formatting(
                    _convert_citations(item.strip(), citekeys), citekeys
                )
                parts.append(f"  \\item {_escape_latex(item_conv)}")
            parts.append("\\end{itemize}")
            list_items = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("### "):
            flush_list()
            in_list = False
            title = stripped[4:].strip()
            parts.append(f"\\subsubsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("## "):
            flush_list()
            in_list = False
            title = stripped[3:].strip()
            parts.append(f"\\subsection{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("# "):
            flush_list()
            in_list = False
            title = stripped[2:].strip()
            parts.append(f"\\section{{{_escape_latex(title)}}}")
            parts.append("")
        elif stripped.startswith("*   ") or stripped.startswith("-   "):
            in_list = True
            content = stripped[4:].strip()
            list_items.append(content)
        elif stripped.startswith("* ") or stripped.startswith("- "):
            in_list = True
            content = stripped[2:].strip()
            list_items.append(content)
        elif stripped == "":
            flush_list()
            in_list = False
            if parts and parts[-1] != "":
                parts.append("")
        else:
            flush_list()
            in_list = False
            conv = _convert_inline_formatting(
                _convert_citations(stripped, citekeys), citekeys
            )
            parts.append(_escape_latex(conv))
        i += 1

    flush_list()
    return "\n".join(parts)


def markdown_to_latex(
    md_content: str,
    citekeys: set[str] | None = None,
    figure_paths: list[str] | None = None,
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
        abstract_esc = _escape_latex(abstract)
        preamble += "\\begin{abstract}\n"
        preamble += abstract_esc + "\n"
        preamble += "\\end{abstract}\n\n"

    body = _md_section_to_latex(rest, citekeys)

    fig_section = ""
    if figure_paths:
        fig_section = "\n\\section*{Figures}\n\n"
        for i, path in enumerate(figure_paths, 1):
            name = Path(path).stem
            inc_path = f"figures/{name}" if "/" not in path else path
            fig_section += f"\\begin{{figure}}[htbp]\n"
            fig_section += f"  \\centering\n"
            fig_section += f"  \\includegraphics[width=0.9\\columnwidth]{{{inc_path}}}\n"
            fig_section += f"  \\caption{{Figure {i}.}}\n"
            fig_section += f"\\end{{figure}}\n\n"

    bib_section = "\n\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n"
    return preamble + body + fig_section + bib_section + "\n\\end{document}\n"
