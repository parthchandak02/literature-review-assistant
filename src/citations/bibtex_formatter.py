"""
BibTeX Citation Formatter

Formats citations according to BibTeX format for LaTeX bibliography files.
"""

import re
from typing import List, Set

from ..search.connectors.base import Paper


class BibTeXFormatter:
    """Formats citations in BibTeX format."""

    def __init__(self):
        """Initialize BibTeX formatter."""
        self._used_keys: Set[str] = set()

    def format_citation(self, paper: Paper, citation_key: str) -> str:
        """
        Format a single BibTeX entry.

        Args:
            paper: Paper object to format
            citation_key: Citation key for the entry

        Returns:
            Formatted BibTeX entry string
        """
        entry_type = self.determine_entry_type(paper)
        fields = []

        # Title
        if paper.title:
            fields.append(f"  title = {{{self.escape_bibtex(paper.title)}}}")

        # Authors
        if paper.authors:
            authors_str = self.format_authors(paper.authors)
            fields.append(f"  author = {{{authors_str}}}")

        # Year
        if paper.year:
            fields.append(f"  year = {{{paper.year}}}")

        # Journal or Booktitle
        if entry_type == "inproceedings" and paper.journal:
            fields.append(f"  booktitle = {{{self.escape_bibtex(paper.journal)}}}")
        elif entry_type == "article" and paper.journal:
            fields.append(f"  journal = {{{self.escape_bibtex(paper.journal)}}}")

        # DOI
        if paper.doi:
            fields.append(f"  doi = {{{paper.doi}}}")

        # URL
        if paper.url:
            fields.append(f"  url = {{{paper.url}}}")

        # Abstract (optional but useful)
        if paper.abstract:
            # Truncate very long abstracts
            abstract = paper.abstract[:500] if len(paper.abstract) > 500 else paper.abstract
            fields.append(f"  abstract = {{{self.escape_bibtex(abstract)}}}")

        # Build entry
        entry_lines = [f"@{entry_type}{{{citation_key},"]
        entry_lines.extend(fields)
        entry_lines.append("}")

        return "\n".join(entry_lines)

    def generate_citation_key(self, paper: Paper, index: int) -> str:
        """
        Generate a unique citation key for a paper.

        Pattern: {lastname}{year}{shorttitle}
        Example: Smith2023Machine

        Args:
            paper: Paper object
            index: Index number (for fallback)

        Returns:
            Unique citation key
        """
        # Extract last name from first author
        lastname = ""
        if paper.authors and len(paper.authors) > 0:
            first_author = paper.authors[0].strip()
            if "," in first_author:
                # Format: "Last, First"
                lastname = first_author.split(",")[0].strip()
            else:
                # Format: "First Last"
                parts = first_author.split()
                if len(parts) > 0:
                    lastname = parts[-1]

        # Clean lastname (remove special chars, keep alphanumeric)
        lastname = re.sub(r"[^a-zA-Z0-9]", "", lastname)
        if not lastname:
            lastname = "Author"

        # Extract year
        year = str(paper.year) if paper.year else "0000"

        # Extract short title (first 3 words, alphanumeric only)
        shorttitle = ""
        if paper.title:
            words = paper.title.split()[:3]
            shorttitle = "".join([re.sub(r"[^a-zA-Z0-9]", "", w) for w in words])
            shorttitle = shorttitle[:20]  # Limit length

        if not shorttitle:
            shorttitle = "Paper"

        # Generate base key
        base_key = f"{lastname}{year}{shorttitle}"

        # Ensure uniqueness
        key = base_key
        suffix = ""
        counter = 0
        while key in self._used_keys:
            counter += 1
            if counter == 1:
                suffix = "b"
            else:
                suffix = chr(ord("b") + counter - 1)
            key = f"{base_key}{suffix}"

        self._used_keys.add(key)
        return key

    def determine_entry_type(self, paper: Paper) -> str:
        """
        Determine BibTeX entry type based on paper metadata.

        Returns:
            Entry type: "article", "inproceedings", "misc", etc.
        """
        # Check if preprint
        if self._is_preprint(paper):
            return "misc"

        # Check if conference
        if self._is_conference(paper):
            return "inproceedings"

        # Default to article for journal papers
        if paper.journal:
            return "article"

        # Fallback to misc
        return "misc"

    def format_authors(self, authors: List[str]) -> str:
        """
        Format authors for BibTeX (Last, First format).

        Args:
            authors: List of author names

        Returns:
            Formatted author string
        """
        if not authors:
            return ""

        formatted_authors = []
        for author in authors:
            formatted = self._format_single_author(author)
            if formatted:
                formatted_authors.append(formatted)

        if not formatted_authors:
            return ""

        # Join with " and "
        return " and ".join(formatted_authors)

    def _format_single_author(self, name: str) -> str:
        """
        Format a single author name to "Last, First" format.

        Args:
            name: Author name (can be "First Last" or "Last, First")

        Returns:
            Formatted name in "Last, First" format
        """
        name = name.strip()
        if not name:
            return ""

        # If already in "Last, First" format
        if "," in name:
            parts = name.split(",", 1)
            last = parts[0].strip()
            first = parts[1].strip()
            return f"{last}, {first}"

        # Try to parse "First Last" format
        parts = name.split()
        if len(parts) >= 2:
            # Assume last word is last name, rest is first name
            last = parts[-1]
            first = " ".join(parts[:-1])
            return f"{last}, {first}"

        # Single word - assume it's last name
        return name

    def escape_bibtex(self, text: str) -> str:
        """
        Escape special BibTeX characters.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        if not text:
            return ""

        # Escape special characters
        # { and } need to be escaped as \{ and \}
        # & needs to be escaped as \&
        # $ needs to be escaped as \$
        # % needs to be escaped as \%
        # _ needs to be escaped as \_
        # # needs to be escaped as \#
        # ^ needs to be escaped as \^{}
        # ~ needs to be escaped as \~{} or \textasciitilde
        # \ needs to be escaped as \textbackslash

        # Replace backslash first (to avoid double-escaping)
        text = text.replace("\\", "\\textbackslash{}")

        # Replace other special characters
        text = text.replace("{", "\\{")
        text = text.replace("}", "\\}")
        text = text.replace("&", "\\&")
        text = text.replace("$", "\\$")
        text = text.replace("%", "\\%")
        text = text.replace("_", "\\_")
        text = text.replace("#", "\\#")
        text = text.replace("^", "\\^{}")
        text = text.replace("~", "\\~{}")

        return text

    def _is_preprint(self, paper: Paper) -> bool:
        """Check if paper is a preprint."""
        if not paper.journal:
            return False
        journal_lower = paper.journal.lower()
        return (
            "preprint" in journal_lower
            or "arxiv" in journal_lower
            or paper.database == "arXiv"
            or (paper.url and "arxiv" in paper.url.lower())
        )

    def _is_conference(self, paper: Paper) -> bool:
        """Check if paper is from a conference."""
        if not paper.journal:
            return False
        journal_lower = paper.journal.lower()
        conference_keywords = [
            "conference",
            "proceedings",
            "workshop",
            "symposium",
            "iccv",
            "cvpr",
            "neurips",
            "icml",
            "acl",
            "emnlp",
            "sigir",
            "kdd",
            "icdm",
            "www",
            "chi",
            "uist",
        ]
        return any(keyword in journal_lower for keyword in conference_keywords)
