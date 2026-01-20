"""
RIS Formatter

Formats papers in RIS (Research Information Systems) format.
RIS is used by reference managers like EndNote, Zotero, Mendeley, etc.
"""

from typing import List, Optional
from datetime import datetime

from ..search.connectors.base import Paper


class RISFormatter:
    """
    Formats Paper objects in RIS format.
    
    RIS format is a text-based format with tags like:
    TY  - Type (JOUR for journal, CONF for conference, etc.)
    TI  - Title
    AU  - Author
    PY  - Publication Year
    DO  - DOI
    ER  - End of Record
    """

    TYPE_MAPPING = {
        "journal": "JOUR",
        "conference": "CONF",
        "book": "BOOK",
        "thesis": "THES",
        "report": "RPRT",
        "webpage": "WEB",
        "default": "JOUR",
    }

    def __init__(self):
        """Initialize RIS formatter."""
        pass

    def format_paper(self, paper: Paper, paper_type: Optional[str] = None) -> str:
        """
        Format a single paper in RIS format.

        Args:
            paper: Paper object to format
            paper_type: Type of paper (journal, conference, etc.) - defaults to "journal"

        Returns:
            RIS-formatted string
        """
        if paper_type is None:
            paper_type = self._infer_type(paper)
        
        ris_type = self.TYPE_MAPPING.get(paper_type.lower(), self.TYPE_MAPPING["default"])
        
        lines = []
        
        # Type
        lines.append(f"TY  - {ris_type}")
        
        # Title
        if paper.title:
            lines.append(f"TI  - {paper.title}")
        
        # Authors
        if paper.authors:
            for author in paper.authors:
                lines.append(f"AU  - {author}")
        
        # Year
        if paper.year:
            lines.append(f"PY  - {paper.year}")
        
        # DOI
        if paper.doi:
            lines.append(f"DO  - {paper.doi}")
        
        # Journal/Venue
        if paper.journal:
            lines.append(f"JO  - {paper.journal}")
            lines.append(f"T2  - {paper.journal}")  # Secondary title (also journal)
        
        # Abstract
        if paper.abstract:
            # RIS abstracts can be long, so we keep them as-is
            lines.append(f"AB  - {paper.abstract}")
        
        # URL
        if paper.url:
            lines.append(f"UR  - {paper.url}")
        
        # Keywords
        if paper.keywords:
            for keyword in paper.keywords:
                lines.append(f"KW  - {keyword}")
        
        # Database
        if paper.database:
            lines.append(f"DB  - {paper.database}")
        
        # Date added (current date)
        lines.append(f"DA  - {datetime.now().strftime('%Y/%m/%d')}")
        
        # End of record
        lines.append("ER  -")
        lines.append("")  # Empty line between records
        
        return "\n".join(lines)

    def format_papers(self, papers: List[Paper]) -> str:
        """
        Format multiple papers in RIS format.

        Args:
            papers: List of Paper objects

        Returns:
            RIS-formatted string with all papers
        """
        ris_lines = []
        
        for paper in papers:
            ris_lines.append(self.format_paper(paper))
        
        return "\n".join(ris_lines)

    def _infer_type(self, paper: Paper) -> str:
        """
        Infer paper type from paper metadata.

        Args:
            paper: Paper object

        Returns:
            Inferred type string
        """
        # Check journal field
        if paper.journal:
            journal_lower = paper.journal.lower()
            if "conference" in journal_lower or "proceedings" in journal_lower:
                return "conference"
            elif "workshop" in journal_lower:
                return "conference"
            else:
                return "journal"
        
        # Check database
        if paper.database:
            db_lower = paper.database.lower()
            if "arxiv" in db_lower:
                return "report"  # Preprints are often treated as reports
            elif "acm" in db_lower:
                return "conference"  # ACM often has conferences
        
        # Default to journal
        return "journal"

    def export_to_file(self, papers: List[Paper], filepath: str):
        """
        Export papers to RIS file.

        Args:
            papers: List of Paper objects
            filepath: Path to output file
        """
        ris_content = self.format_papers(papers)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(ris_content)
