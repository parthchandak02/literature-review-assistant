"""
LaTeX Exporter

Exports systematic review reports to LaTeX format for journal submission.
Supports IEEE and other journal templates.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

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

    def _generate_latex(self, report_data: Dict[str, Any], template: str, output_path: Optional[str] = None) -> str:
        """Generate LaTeX content from report data."""
        if template == "ieee":
            return self._generate_ieee_latex(report_data, output_path)
        else:
            # Default to IEEE template
            return self._generate_ieee_latex(report_data, output_path)

    def _generate_ieee_latex(self, report_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
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
                author_lines.append(f"\\author{{{self._escape_latex(author.get('name', 'Author'))}}}")
            lines.append("\\author{" + "\\and ".join([f"{a.get('name', '')}" for a in authors]) + "}")
        else:
            lines.append("\\author{Anonymous Author(s)}")

        lines.append("")
        lines.append("\\maketitle")
        lines.append("")

        # Abstract
        abstract = report_data.get("abstract", "")
        if abstract:
            lines.append("\\begin{abstract}")
            lines.append(self._escape_latex(abstract))
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
        """Escape special LaTeX characters."""
        if not text:
            return ""
        
        # LaTeX special characters that need escaping
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
        
        # Remove markdown headers (already handled by sections)
        text = re.sub(r"^#+\s+(.+)$", r"\\textbf{\1}", markdown_text, flags=re.MULTILINE)
        
        # Convert bold **text** to \textbf{text}
        text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
        
        # Convert italic *text* to \textit{text}
        text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\\textit{\1}", text)
        
        # Convert citations [X] to \cite{X}
        text = re.sub(r"\[(\d+)\]", r"\\cite{\1}", text)
        
        # Convert line breaks to LaTeX line breaks
        text = text.replace("\n\n", "\n\n")
        
        # Escape remaining special characters
        text = self._escape_latex(text)
        
        return text

    def _format_ieee_reference(self, ref: Dict[str, Any], number: int) -> str:
        """Format a single reference in IEEE style."""
        # This will use the existing IEEEFormatter logic
        # For now, create basic format
        authors = ref.get("authors", [])
        title = ref.get("title", "")
        journal = ref.get("journal", "")
        year = ref.get("year", "")
        doi = ref.get("doi", "")
        
        # Format authors
        if authors:
            if len(authors) >= 6:
                author_str = f"{authors[0]} et al."
            elif len(authors) == 1:
                author_str = authors[0]
            elif len(authors) == 2:
                author_str = f"{authors[0]} and {authors[1]}"
            else:
                author_str = ", ".join(authors[:-1]) + f", and {authors[-1]}"
        else:
            author_str = "[No authors]"
        
        parts = [author_str]
        if title:
            parts.append(f'"{self._escape_latex(title)}"')
        if journal:
            parts.append(self._escape_latex(journal))
        if year:
            parts.append(str(year))
        if doi:
            parts.append(f"doi: {doi}")
        
        return ", ".join(parts) + "."

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
