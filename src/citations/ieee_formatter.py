"""
IEEE Citation Formatter

Formats citations according to IEEE style guidelines.
"""

import re
from typing import List
from ..search.database_connectors import Paper


class IEEEFormatter:
    """Formats citations in IEEE style."""

    @staticmethod
    def format_citation(paper: Paper, citation_number: int) -> str:
        """
        Format a single citation in IEEE style.

        Args:
            paper: Paper object to format
            citation_number: Citation number (1-indexed)

        Returns:
            Formatted citation string
        """
        # Format authors
        authors_str = IEEEFormatter._format_authors(paper.authors)

        # Format title (with quotes)
        title_str = f'"{paper.title}"' if paper.title else ""

        # Determine paper type and format accordingly
        if IEEEFormatter._is_preprint(paper):
            return IEEEFormatter._format_preprint(paper, citation_number, authors_str, title_str)
        elif IEEEFormatter._is_conference(paper):
            return IEEEFormatter._format_conference(paper, citation_number, authors_str, title_str)
        else:
            return IEEEFormatter._format_journal(paper, citation_number, authors_str, title_str)

    @staticmethod
    def _format_authors(authors: List[str]) -> str:
        """Format author list according to IEEE style."""
        if not authors:
            return "[No authors]"

        # IEEE: Use "et al." for 6+ authors
        if len(authors) >= 6:
            # Format first author
            first_author = IEEEFormatter._format_author_name(authors[0])
            return f"{first_author} et al."
        elif len(authors) == 1:
            return IEEEFormatter._format_author_name(authors[0])
        elif len(authors) == 2:
            author1 = IEEEFormatter._format_author_name(authors[0])
            author2 = IEEEFormatter._format_author_name(authors[1])
            return f"{author1} and {author2}"
        else:
            # 3-5 authors: "Author1, Author2, Author3, and Author4"
            formatted = [IEEEFormatter._format_author_name(a) for a in authors[:-1]]
            last_author = IEEEFormatter._format_author_name(authors[-1])
            return ", ".join(formatted) + f", and {last_author}"

    @staticmethod
    def _format_author_name(name: str) -> str:
        """Format a single author name (IEEE: Last, First Initial)."""
        name = name.strip()
        if not name:
            return ""

        # If already in "Last, First" format, use as-is
        if "," in name:
            parts = name.split(",", 1)
            last = parts[0].strip()
            first = parts[1].strip()
            # Extract initials
            initials = "".join([part[0].upper() + "." for part in first.split() if part])
            return f"{last}, {initials}" if initials else last

        # Try to parse "First Last" format
        parts = name.split()
        if len(parts) >= 2:
            # Assume last word is last name, rest is first name
            last = parts[-1]
            first_parts = parts[:-1]
            initials = "".join([p[0].upper() + "." for p in first_parts if p])
            return f"{last}, {initials}" if initials else last

        # Single word - assume it's last name
        return name

    @staticmethod
    def _is_preprint(paper: Paper) -> bool:
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

    @staticmethod
    def _is_conference(paper: Paper) -> bool:
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
        ]
        return any(keyword in journal_lower for keyword in conference_keywords)

    @staticmethod
    def _format_preprint(
        paper: Paper, citation_number: int, authors_str: str, title_str: str
    ) -> str:
        """Format preprint citation."""
        parts = [f"[{citation_number}] {authors_str}"]

        if title_str:
            parts.append(title_str)

        # Extract arXiv ID if available
        arxiv_id = None
        if paper.doi and "arxiv" in paper.doi.lower():
            arxiv_id = paper.doi
        elif paper.url and "arxiv" in paper.url.lower():
            # Extract arXiv ID from URL
            match = re.search(r"arxiv\.org/(?:abs/)?(\d{4}\.\d{4,5})", paper.url.lower())
            if match:
                arxiv_id = match.group(1)

        if arxiv_id:
            parts.append(f"arXiv preprint arXiv:{arxiv_id}")
        else:
            parts.append("Preprint")

        if paper.year:
            parts.append(f"{paper.year}")

        if paper.doi and not arxiv_id:
            parts.append(f"doi: {paper.doi}")

        return ", ".join(parts) + "."

    @staticmethod
    def _format_conference(
        paper: Paper, citation_number: int, authors_str: str, title_str: str
    ) -> str:
        """Format conference paper citation."""
        parts = [f"[{citation_number}] {authors_str}"]

        if title_str:
            parts.append(title_str)

        if paper.journal:
            parts.append(f"in {paper.journal}")

        if paper.year:
            parts.append(f"{paper.year}")

        if paper.doi:
            parts.append(f"doi: {paper.doi}")

        return ", ".join(parts) + "."

    @staticmethod
    def _format_journal(
        paper: Paper, citation_number: int, authors_str: str, title_str: str
    ) -> str:
        """Format journal article citation."""
        parts = [f"[{citation_number}] {authors_str}"]

        if title_str:
            parts.append(title_str)

        if paper.journal:
            parts.append(paper.journal)

        # Note: Volume, number, pages not typically available in our Paper dataclass
        # Would need to be extracted from full metadata if available

        if paper.year:
            parts.append(f"{paper.year}")

        if paper.doi:
            parts.append(f"doi: {paper.doi}")

        return ", ".join(parts) + "."
