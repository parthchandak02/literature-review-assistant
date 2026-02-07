"""
Citation Manager

Extracts citations from text, maps them to papers, and generates References section.
"""

import logging
import re
from typing import Any, Dict, List, Set

from ..search.database_connectors import Paper
from .ieee_formatter import IEEEFormatter

logger = logging.getLogger(__name__)


class CitationManager:
    """Manages citation extraction and formatting."""

    def __init__(self, papers: List[Paper]):
        """
        Initialize citation manager.

        Args:
            papers: List of included papers to cite
        """
        self.papers = papers
        self.citation_map: Dict[int, int] = {}  # citation_number -> paper_index
        self.used_citations: Set[int] = set()  # Track which citations are used

        # Initialize Manubot resolver (optional)
        try:
            from .manubot_resolver import ManubotCitationResolver

            self.manubot_resolver = ManubotCitationResolver()
        except ImportError:
            self.manubot_resolver = None
            logger.debug("Manubot resolver not available")

    def add_citation_from_identifier(self, identifier: str) -> int:
        """
        Add citation by resolving from identifier (DOI, PMID, arXiv, etc.).

        Args:
            identifier: Identifier string (DOI, PMID, arXiv ID, or citekey)

        Returns:
            Citation number (1-based index)

        Raises:
            ImportError: If Manubot is not installed
            ValueError: If identifier resolution fails
        """
        if not self.manubot_resolver:
            raise ImportError("Manubot resolver not available. Install with: pip install manubot")

        # Resolve citation
        csl_item = self.manubot_resolver.resolve_from_identifier(identifier)

        # Convert to Paper object
        paper = self.manubot_resolver.csl_to_paper(csl_item)

        # Add to papers list
        self.papers.append(paper)
        paper_index = len(self.papers) - 1

        # Assign citation number
        citation_number = len(self.papers)
        self.citation_map[citation_number] = paper_index
        self.used_citations.add(citation_number)

        logger.info(f"Added citation from identifier {identifier}: {paper.title[:50]}...")
        return citation_number

    def extract_and_map_citations(self, text: str, auto_resolve: bool = False) -> str:
        """
        Extract citations from text and replace with numbered citations.

        Supports multiple citation formats:
        - [Citation X] - Placeholder format
        - [X] - Numbered citations
        - [@doi:10.1038/...] - Manubot DOI format (if auto_resolve=True)
        - [@pmid:12345678] - Manubot PMID format (if auto_resolve=True)
        - [@arxiv:1407.3561] - Manubot arXiv format (if auto_resolve=True)

        Args:
            text: Text containing citation placeholders
            auto_resolve: If True, automatically resolve Manubot-style citations

        Returns:
            Text with citations replaced as [X]
        """

        # First, handle [Citation X] format and convert to [X]
        def replace_citation_placeholder(match):
            """Replace citation placeholder with numbered citation."""
            bracket_content = match.group(0)
            # Extract all citation numbers from the bracket
            citation_numbers = []
            number_pattern = r"Citation\s+(\d+)"
            for num_match in re.finditer(number_pattern, bracket_content):
                citation_numbers.append(int(num_match.group(1)))

            # Map citation numbers to paper indices
            # For now, use simple mapping: Citation 1 -> Paper 0, etc.
            # In a more sophisticated system, we'd use LLM to match citations to papers
            mapped_numbers = []
            for cit_num in citation_numbers:
                if cit_num <= len(self.papers):
                    paper_idx = cit_num - 1  # Convert to 0-indexed
                    self.citation_map[cit_num] = paper_idx
                    self.used_citations.add(cit_num)
                    mapped_numbers.append(str(cit_num))
                else:
                    # Citation number exceeds available papers - keep original
                    mapped_numbers.append(str(cit_num))

            # Format as [1, 2, 3] for multiple citations
            if len(mapped_numbers) == 1:
                return f"[{mapped_numbers[0]}]"
            else:
                return f"[{', '.join(mapped_numbers)}]"

        # Pattern to match [Citation X] or [Citation X, Citation Y, ...]
        pattern = r"\[Citation\s+\d+(?:\s*,\s*Citation\s+\d+)*\]"

        # Replace all citation placeholder patterns
        result = re.sub(pattern, replace_citation_placeholder, text)

        # Now, also extract and track already-converted [X] or [X, Y, Z] citations
        # This handles cases where LLM generates [1], [2] directly instead of [Citation 1]
        def track_existing_citations(match):
            """Track citations that are already in [X] format."""
            bracket_content = match.group(0)
            # Extract all numbers from [1], [2, 3], etc.
            citation_numbers = []
            number_pattern = r"(\d+)"
            for num_match in re.finditer(number_pattern, bracket_content):
                cit_num = int(num_match.group(1))
                citation_numbers.append(cit_num)

                # Track citation if it's within valid range
                # Also track citations even if papers list is empty (for placeholder citations)
                if cit_num > 0:
                    if cit_num <= len(self.papers):
                        paper_idx = cit_num - 1  # Convert to 0-indexed
                        self.citation_map[cit_num] = paper_idx
                    # Always track used citations, even if paper doesn't exist
                    # This allows References section to show citations were used
                    self.used_citations.add(cit_num)

            # Return unchanged (already in correct format)
            return bracket_content

        # Pattern to match [X] or [X, Y, Z] where X, Y, Z are numbers
        # Only match if it looks like a citation (not part of a code block or URL)
        existing_citation_pattern = r"\[(\d+(?:\s*,\s*\d+)*)\]"

        # Replace to track citations (but keep format unchanged)
        result = re.sub(existing_citation_pattern, track_existing_citations, result)

        # Handle Manubot-style citations if auto_resolve is enabled
        if auto_resolve and self.manubot_resolver:

            def resolve_manubot_citation(match):
                """Resolve Manubot-style citation and replace with numbered citation."""
                citekey = match.group(1)  # Extract citekey from [@citekey]
                try:
                    citation_number = self.add_citation_from_identifier(citekey)
                    return f"[{citation_number}]"
                except Exception as e:
                    logger.warning(f"Failed to resolve citation {citekey}: {e}")
                    return match.group(0)  # Keep original if resolution fails

            # Pattern for Manubot citations: [@doi:...], [@pmid:...], [@arxiv:...], etc.
            manubot_pattern = r"\[@([^\]]+)\]"
            result = re.sub(manubot_pattern, resolve_manubot_citation, result)

        return result

    def generate_references_section(self) -> str:
        """
        Generate References section in IEEE format.

        Returns:
            Formatted References section as markdown
        """
        if not self.used_citations:
            return "## References\n\nNo citations found in the document.\n"

        # Sort citations by number
        sorted_citations = sorted(self.used_citations)

        # Generate formatted citations
        references = []
        references.append("## References\n")

        for cit_num in sorted_citations:
            if cit_num in self.citation_map:
                paper_idx = self.citation_map[cit_num]
                if 0 <= paper_idx < len(self.papers):
                    paper = self.papers[paper_idx]
                    formatted = IEEEFormatter.format_citation(paper, cit_num)
                    references.append(formatted)
                else:
                    # Citation referenced but paper not available (e.g., placeholder citation)
                    # Still include it in references with a note
                    references.append(
                        f"[{cit_num}] Citation referenced but paper data not available."
                    )
            else:
                # Citation used but not mapped (citation number exceeds available papers)
                # This can happen when writing agents generate citations for papers that don't exist
                references.append(f"[{cit_num}] Citation referenced but paper data not available.")

        references.append("")  # Empty line at end

        return "\n".join(references)

    def get_citation_count(self) -> int:
        """Get number of unique citations used."""
        return len(self.used_citations)

    def get_references(self) -> List[Dict[str, Any]]:
        """
        Get references as list of dictionaries for LaTeX export.

        Returns:
            List of reference dictionaries with paper metadata
        """
        if not self.used_citations:
            return []

        # Sort citations by number
        sorted_citations = sorted(self.used_citations)

        references = []
        for cit_num in sorted_citations:
            if cit_num in self.citation_map:
                paper_idx = self.citation_map[cit_num]
                if 0 <= paper_idx < len(self.papers):
                    paper = self.papers[paper_idx]
                    references.append(
                        {
                            "authors": paper.authors or [],
                            "title": paper.title or "",
                            "journal": paper.journal,
                            "year": paper.year,
                            "doi": paper.doi,
                            "url": paper.url,
                        }
                    )

        return references

    def generate_bibtex_references(self) -> str:
        """
        Generate BibTeX references section.

        Returns:
            BibTeX file content as string
        """
        from .bibtex_formatter import BibTeXFormatter

        if not self.used_citations:
            return ""

        formatter = BibTeXFormatter()
        entries = []

        for cit_num in sorted(self.used_citations):
            if cit_num in self.citation_map:
                paper_idx = self.citation_map[cit_num]
                if 0 <= paper_idx < len(self.papers):
                    paper = self.papers[paper_idx]
                    citation_key = formatter.generate_citation_key(paper, cit_num)
                    entry = formatter.format_citation(paper, citation_key)
                    entries.append(entry)

        return "\n\n".join(entries) + "\n"

    def export_bibtex(self, output_path: str) -> str:
        """
        Export BibTeX references to a file.

        Args:
            output_path: Path to output BibTeX file

        Returns:
            Path to generated BibTeX file
        """
        from pathlib import Path

        bibtex_content = self.generate_bibtex_references()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(bibtex_content)

        return str(output_file)

    def generate_ris_references(self) -> str:
        """
        Generate RIS references section.

        Returns:
            RIS file content as string
        """
        from .ris_formatter import RISFormatter

        formatter = RISFormatter()
        return formatter.format_papers(self.papers)

    def export_ris(self, output_path: str) -> str:
        """
        Export RIS references to a file.

        Args:
            output_path: Path to output RIS file

        Returns:
            Path to generated RIS file
        """
        from pathlib import Path

        from .ris_formatter import RISFormatter

        formatter = RISFormatter()
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        formatter.export_to_file(self.papers, str(output_file))

        return str(output_file)
