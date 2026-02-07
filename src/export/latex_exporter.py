"""
LaTeX Exporter

Exports systematic review reports to LaTeX format for journal submission.
Supports IEEE and other journal templates.

Uses pylatexenc for proper LaTeX escaping and markdown library for conversion.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pylatexenc.latexencode import unicode_to_latex

    PYLATEXENC_AVAILABLE = True
except ImportError:
    PYLATEXENC_AVAILABLE = False

import importlib.util

MARKDOWN_AVAILABLE = importlib.util.find_spec("markdown") is not None

logger = logging.getLogger(__name__)


class LaTeXExporter:
    """Exports reports to LaTeX format."""

    def __init__(self, template: str = "ieee"):
        """
        Initialize LaTeX exporter.

        Args:
            template: Template name ("ieee", "jmir", "plos", etc.)
        """
        self.template = template
        self.templates_dir = Path(__file__).parent.parent.parent / "templates"

    def export(
        self,
        report_data: Dict[str, Any],
        output_path: str,
        journal: Optional[str] = None,
    ) -> str:
        """
        Export report to LaTeX format.

        Args:
            report_data: Dictionary containing report sections and metadata
            output_path: Path to save LaTeX file
            journal: Journal name (for template selection)

        Returns:
            Path to generated LaTeX file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Select template based on journal
        template_name = self._select_template(journal)

        # Generate LaTeX content
        latex_content = self._generate_latex(report_data, template_name, str(output_file))

        # Write to file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(latex_content)

        logger.info(f"LaTeX file generated: {output_file}")
        return str(output_file)

    def _select_template(self, journal: Optional[str]) -> str:
        """Select appropriate LaTeX template based on journal."""
        if journal:
            journal_lower = journal.lower()
            if "ieee" in journal_lower:
                return "ieee"
            elif "jmir" in journal_lower:
                return "jmir"
            elif "plos" in journal_lower:
                return "plos"
            elif "bmj" in journal_lower:
                return "bmj"

        return self.template

    def _generate_latex(
        self, report_data: Dict[str, Any], template: str, output_path: Optional[str] = None
    ) -> str:
        """Generate LaTeX content from report data."""
        if template == "ieee":
            return self._generate_ieee_latex(report_data, output_path)
        else:
            # Default to IEEE template
            return self._generate_ieee_latex(report_data, output_path)

    def _generate_ieee_latex(
        self, report_data: Dict[str, Any], output_path: Optional[str] = None
    ) -> str:
        """Generate IEEE-style LaTeX document."""
        lines = []
        output_dir = Path(output_path).parent if output_path else Path.cwd()

        # Document class and packages
        lines.append("\\documentclass[journal]{IEEEtran}")
        lines.append("")
        lines.append("% Packages")
        lines.append("\\usepackage{graphicx}")
        lines.append("\\usepackage{amsmath}")
        lines.append("\\usepackage{booktabs}")
        lines.append("\\usepackage{url}")
        lines.append("\\usepackage{hyperref}")
        lines.append("")

        # Document begin
        lines.append("\\begin{document}")
        lines.append("")

        # Title
        title = report_data.get("title", "Systematic Review")
        lines.append(f"\\title{{{self._escape_latex(title)}}}")
        lines.append("")

        # Author information (if available)
        authors = report_data.get("authors", [])
        if authors:
            author_lines = []
            for author in authors:
                author_lines.append(
                    f"\\author{{{self._escape_latex(author.get('name', 'Author'))}}}"
                )
            lines.append(
                "\\author{" + "\\and ".join([f"{a.get('name', '')}" for a in authors]) + "}"
            )
        else:
            lines.append("\\author{Anonymous Author(s)}")

        lines.append("")
        lines.append("\\maketitle")
        lines.append("")

        # Abstract
        abstract = report_data.get("abstract", "")
        if abstract:
            # For IEEE, convert structured abstract to unstructured if needed
            # IEEE requires unstructured abstract (150-250 words)
            abstract_text = self._convert_to_unstructured_abstract(abstract)
            lines.append("\\begin{abstract}")
            lines.append(self._escape_latex(abstract_text))
            lines.append("\\end{abstract}")
            lines.append("")

        # Keywords
        keywords = report_data.get("keywords", [])
        if keywords:
            keywords_str = ", ".join([self._escape_latex(kw) for kw in keywords])
            lines.append(f"\\textbf{{Index Terms}}---{keywords_str}")
            lines.append("")

        # Introduction
        introduction = report_data.get("introduction", "")
        if introduction:
            lines.append("\\section{Introduction}")
            lines.append(self._markdown_to_latex(introduction))
            lines.append("")

        # Methods
        methods = report_data.get("methods", "")
        if methods:
            lines.append("\\section{Methods}")
            lines.append(self._markdown_to_latex(methods))
            lines.append("")

        # Results
        results = report_data.get("results", "")
        if results:
            lines.append("\\section{Results}")
            lines.append(self._markdown_to_latex(results))
            lines.append("")

        # Discussion
        discussion = report_data.get("discussion", "")
        if discussion:
            lines.append("\\section{Discussion}")
            lines.append(self._markdown_to_latex(discussion))
            lines.append("")

        # Figures
        figures = report_data.get("figures", [])
        for i, figure in enumerate(figures, 1):
            fig_path = figure.get("path", "")
            caption = figure.get("caption", f"Figure {i}")
            if fig_path:
                # Copy figure to output directory if needed
                lines.append("\\begin{figure}[!t]")
                lines.append("\\centering")
                # Convert path to relative path for LaTeX
                rel_path = self._get_relative_figure_path(fig_path, output_dir)
                lines.append(f"\\includegraphics[width=\\columnwidth]{{{rel_path}}}")
                lines.append(f"\\caption{{{self._escape_latex(caption)}}}")
                lines.append(f"\\label{{fig:{i}}}")
                lines.append("\\end{figure}")
                lines.append("")

        # References
        references = report_data.get("references", [])
        if references:
            lines.append("\\section*{References}")
            lines.append("")
            lines.append("\\begin{thebibliography}{99}")
            for i, ref in enumerate(references, 1):
                ref_text = self._format_ieee_reference(ref, i)
                lines.append(f"\\bibitem{{{i}}}")
                lines.append(ref_text)
                lines.append("")
            lines.append("\\end{thebibliography}")
            lines.append("")

        # Document end
        lines.append("\\end{document}")

        return "\n".join(lines)

    def _escape_latex(self, text: str) -> str:
        """Escape special LaTeX characters using pylatexenc if available."""
        if not text:
            return ""

        # Use pylatexenc for proper Unicode and LaTeX escaping if available
        if PYLATEXENC_AVAILABLE:
            try:
                # pylatexenc handles Unicode, special chars, and LaTeX commands properly
                return unicode_to_latex(text, non_ascii_only=False)
            except Exception as e:
                logger.debug(f"pylatexenc encoding failed, using fallback: {e}")

        # Fallback to manual escaping if pylatexenc not available
        special_chars = {
            "\\": "\\textbackslash{}",
            "{": "\\{",
            "}": "\\}",
            "$": "\\$",
            "&": "\\&",
            "%": "\\%",
            "#": "\\#",
            "^": "\\textasciicircum{}",
            "_": "\\_",
            "~": "\\textasciitilde{}",
        }

        result = text
        for char, replacement in special_chars.items():
            result = result.replace(char, replacement)

        return result

    def _markdown_to_latex(self, markdown_text: str) -> str:
        """Convert markdown text to LaTeX."""
        if not markdown_text:
            return ""

        lines = markdown_text.split("\n")
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check for markdown table
            if line.startswith("|") and i + 1 < len(lines) and "---" in lines[i + 1]:
                # Parse and convert table
                table_latex = self._convert_markdown_table_to_latex(lines, i)
                if table_latex:
                    result_lines.append(table_latex)
                    # Skip table lines
                    while i < len(lines) and (lines[i].startswith("|") or "---" in lines[i]):
                        i += 1
                    continue

            # Remove markdown headers (already handled by sections)
            if line.startswith("#"):
                # Skip headers as they're handled by sections
                i += 1
                continue

            # Convert bold **text** to \textbf{text}
            line = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", line)

            # Convert italic *text* to \textit{text}
            line = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\\textit{\1}", line)

            # Convert citations [X] to \cite{X}
            line = re.sub(r"\[(\d+)\]", r"\\cite{\1}", line)

            # Escape remaining special characters
            line = self._escape_latex(line)

            result_lines.append(line)
            i += 1

        return "\n".join(result_lines)

    def _convert_markdown_table_to_latex(self, lines: List[str], start_idx: int) -> Optional[str]:
        """Convert markdown table to LaTeX table using booktabs for professional formatting."""
        if start_idx >= len(lines):
            return None

        header_line = lines[start_idx]
        if not header_line.startswith("|"):
            return None

        # Parse header
        headers = [cell.strip() for cell in header_line.split("|")[1:-1]]

        # Check separator
        if start_idx + 1 >= len(lines):
            return None
        lines[start_idx + 1]

        # Parse rows
        table_rows = []
        i = start_idx + 2
        while i < len(lines):
            row_line = lines[i]
            if not row_line.startswith("|"):
                break
            row_cells = [cell.strip() for cell in row_line.split("|")[1:-1]]
            if len(row_cells) == len(headers):
                table_rows.append(row_cells)
            i += 1

        if not table_rows:
            return None

        # Determine column alignment based on content
        # For study characteristics tables, use appropriate alignment
        alignments = []
        for col_idx in range(len(headers)):
            # Check if column contains mostly numbers (right-align) or text (left-align)
            has_numbers = False
            for row in table_rows[: min(5, len(table_rows))]:  # Sample first 5 rows
                if col_idx < len(row) and row[col_idx]:
                    # Check if cell looks like a number
                    cell = row[col_idx].strip()
                    if cell.replace(".", "").replace(",", "").isdigit() or "Study" in cell:
                        has_numbers = True
                        break
            alignments.append("r" if has_numbers else "l")

        # Generate LaTeX table with booktabs
        latex_lines = []
        latex_lines.append("\\begin{table*}[!t]")  # Use table* for full-width tables
        latex_lines.append("\\centering")
        latex_lines.append("\\begin{tabular}{" + "".join(alignments) + "}")
        latex_lines.append("\\toprule")

        # Header row
        header_cells = [self._escape_latex(h) for h in headers]
        latex_lines.append(" & ".join([f"\\textbf{{{h}}}" for h in header_cells]) + " \\\\")
        latex_lines.append("\\midrule")

        # Data rows
        for row in table_rows:
            row_cells = [self._escape_latex(cell) for cell in row]
            # Ensure all rows have same number of cells as headers
            while len(row_cells) < len(headers):
                row_cells.append("")
            latex_lines.append(" & ".join(row_cells[: len(headers)]) + " \\\\")

        latex_lines.append("\\bottomrule")
        latex_lines.append("\\end{tabular}")

        # Try to extract caption from context (if available)
        caption = "Study characteristics table"
        if "Study ID" in headers:
            caption = "Study characteristics of included studies"
        elif "Risk" in " ".join(headers) or "Bias" in " ".join(headers):
            caption = "Risk of bias assessment"
        elif "Outcome" in " ".join(headers):
            caption = "GRADE evidence profile"

        latex_lines.append(f"\\caption{{{self._escape_latex(caption)}}}")
        latex_lines.append("\\label{tab:study_characteristics}")
        latex_lines.append("\\end{table*}")

        return "\n".join(latex_lines)

    def _format_ieee_reference(self, ref: Dict[str, Any], number: int) -> str:
        """Format a single reference in IEEE style."""
        from ..citations.ieee_formatter import IEEEFormatter
        from ..search.connectors.base import Paper

        # Create a Paper object from the reference dict to use IEEEFormatter
        paper = Paper(
            title=ref.get("title", ""),
            abstract="",  # Not needed for citation
            authors=ref.get("authors", []),
            year=ref.get("year"),
            journal=ref.get("journal"),
            doi=ref.get("doi"),
            url=ref.get("url"),
        )

        # Use IEEEFormatter to format the citation
        formatted = IEEEFormatter.format_citation(paper, number)

        # Remove the citation number prefix [X] since LaTeX \bibitem handles numbering
        # IEEEFormatter returns "[X] Author, "Title," Journal, year."
        # We need: "Author, \"Title,\" Journal, year."
        formatted = re.sub(r"^\[\d+\]\s*", "", formatted)

        # Escape LaTeX special characters
        return self._escape_latex(formatted)

    def _convert_to_unstructured_abstract(self, abstract: str) -> str:
        """
        Convert structured abstract (PRISMA 2020 or other structured formats) to unstructured.

        IEEE requires unstructured abstract (150-250 words, single paragraph).
        This method extracts content from structured abstracts and converts to paragraph format.

        Args:
            abstract: Abstract text (may be structured or unstructured)

        Returns:
            Unstructured abstract text suitable for IEEE format
        """
        if not abstract:
            return ""

        # Check if abstract is structured (has labels like "Background:", "Objectives:", etc.)
        structured_patterns = [
            r"Background\s*:",
            r"Objectives?\s*:",
            r"Methods?\s*:",
            r"Results?\s*:",
            r"Conclusions?\s*:",
            r"Eligibility\s*:",
            r"Information\s*sources?\s*:",
        ]

        is_structured = any(
            re.search(pattern, abstract, re.IGNORECASE) for pattern in structured_patterns
        )

        if not is_structured:
            # Already unstructured, return as-is (but ensure single paragraph)
            return " ".join(abstract.split())

        # Convert structured to unstructured
        # Extract content after labels and combine into paragraph
        lines = abstract.split("\n")
        content_parts = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip if it's just a label
            if re.match(r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)?\s*:?\s*$", line):
                continue

            # Remove labels and extract content
            # Pattern: "Label: content" -> "content"
            match = re.match(r"^[A-Z][^:]*:\s*(.+)$", line)
            if match:
                content_parts.append(match.group(1).strip())
            else:
                # No label, just content
                content_parts.append(line)

        # Combine into single paragraph
        unstructured = " ".join(content_parts)

        # Ensure word count is reasonable (150-250 words for IEEE)
        words = unstructured.split()
        if len(words) > 250:
            # Truncate to ~250 words
            unstructured = " ".join(words[:250]) + "..."
        elif len(words) < 150 and len(content_parts) > 0:
            # If too short, try to expand from original abstract
            # For now, just return what we have
            pass

        return unstructured

    def _get_relative_figure_path(self, fig_path: str, output_dir: Path) -> str:
        """Get relative path for figure from LaTeX file location."""
        fig_file = Path(fig_path)
        if fig_file.is_absolute():
            try:
                return str(fig_file.relative_to(output_dir))
            except ValueError:
                # If not relative, just use filename
                return fig_file.name
        return fig_path
