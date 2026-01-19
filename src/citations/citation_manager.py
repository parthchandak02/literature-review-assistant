"""
Citation Manager

Extracts citations from text, maps them to papers, and generates References section.
"""

import re
from typing import Dict, List, Set
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
            text: Text containing [Citation X] placeholders

        Returns:
            Text with citations replaced as [X]
        """
        # Pattern to match [Citation X] or [Citation X, Citation Y, ...]
        # Use findall to get all citation numbers, then replace the whole bracket
        def replace_citation(match):
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
        
        # Replace all citation patterns
        result = re.sub(pattern, replace_citation, text)

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
