"""
Style Reference Data Structure

Defines the data structure for storing writing style patterns extracted from papers.
"""

from typing import Dict, List, Optional


class StylePatterns:
    """Data structure for storing writing style patterns."""

    def __init__(self):
        """Initialize empty style patterns."""
        self.patterns: Dict[str, Dict[str, List[str]]] = {
            "introduction": {
                "sentence_openings": [],
                "citation_patterns": [],
                "transitions": [],
                "vocabulary": [],
            },
            "methods": {
                "sentence_openings": [],
                "citation_patterns": [],
                "transitions": [],
                "vocabulary": [],
            },
            "results": {
                "sentence_openings": [],
                "citation_patterns": [],
                "transitions": [],
                "vocabulary": [],
            },
            "discussion": {
                "sentence_openings": [],
                "citation_patterns": [],
                "transitions": [],
                "vocabulary": [],
            },
        }

    def add_pattern(
        self,
        section_type: str,
        pattern_type: str,
        pattern: str,
    ):
        """
        Add a pattern to the collection.

        Args:
            section_type: Section type (introduction, methods, results, discussion)
            pattern_type: Pattern type (sentence_openings, citation_patterns, transitions, vocabulary)
            pattern: Pattern string to add
        """
        if section_type not in self.patterns:
            self.patterns[section_type] = {
                "sentence_openings": [],
                "citation_patterns": [],
                "transitions": [],
                "vocabulary": [],
            }

        if pattern_type not in self.patterns[section_type]:
            self.patterns[section_type][pattern_type] = []

        if pattern and pattern not in self.patterns[section_type][pattern_type]:
            self.patterns[section_type][pattern_type].append(pattern)

    def get_patterns(
        self, section_type: str, pattern_type: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Get patterns for a section type.

        Args:
            section_type: Section type to get patterns for
            pattern_type: Optional specific pattern type to get

        Returns:
            Dictionary of patterns or list if pattern_type specified
        """
        if section_type not in self.patterns:
            return {} if not pattern_type else []

        if pattern_type:
            return self.patterns[section_type].get(pattern_type, [])

        return self.patterns[section_type]

    def to_dict(self) -> Dict[str, Dict[str, List[str]]]:
        """Convert to dictionary."""
        return self.patterns

    @classmethod
    def from_dict(cls, data: Dict[str, Dict[str, List[str]]]) -> "StylePatterns":
        """Create from dictionary."""
        instance = cls()
        instance.patterns = data
        return instance
