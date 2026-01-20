"""
Citation Manager

Extracts citations from text, maps them to papers, and generates References section.
"""

import re
from typing import Dict, List, Set, Any
from ..search.database_connectors import Paper
from .ieee_formatter import IEEEFormatter


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

    def extract_and_map_citations(self, text: str) -> str:
        """
        Extract citations from text and replace with numbered citations.

        Args:
            text: Text containing [Citation X] placeholders or already [X] format

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
                if cit_num <= len(self.papers) and cit_num > 0:
                    paper_idx = cit_num - 1  # Convert to 0-indexed
                    self.citation_map[cit_num] = paper_idx
                    self.used_citations.add(cit_num)
            
            # Return unchanged (already in correct format)
            return bracket_content
        
        # Pattern to match [X] or [X, Y, Z] where X, Y, Z are numbers
        # Only match if it looks like a citation (not part of a code block or URL)
        existing_citation_pattern = r"\[(\d+(?:\s*,\s*\d+)*)\]"
        
        # Replace to track citations (but keep format unchanged)
        result = re.sub(existing_citation_pattern, track_existing_citations, result)

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
                    references.append({
                        "authors": paper.authors or [],
                        "title": paper.title or "",
                        "journal": paper.journal,
                        "year": paper.year,
                        "doi": paper.doi,
                        "url": paper.url,
                    })
        
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
