"""
PRISMA Counter Stub

Minimal implementation to track workflow counts without generating diagrams.
Replaces the deleted src.prisma module functionality.
"""

from typing import Dict, Optional


class PRISMACounter:
    """Stub for tracking PRISMA workflow counts without diagram generation."""
    
    def __init__(self):
        self._counts = {
            "found": 0,
            "found_other": 0,
            "no_dupes": 0,
            "screened": 0,
            "screen_exclusions": 0,
            "full_text_sought": 0,
            "full_text_not_retrieved": 0,
            "full_text_assessed": 0,
            "full_text_exclusions": 0,
            "qualitative": 0,
            "quantitative": 0,
        }
        self._database_breakdown = {}
    
    def set_found(self, count: int, database_breakdown: Optional[Dict[str, int]] = None):
        """Set number of papers found."""
        self._counts["found"] = count
        if database_breakdown:
            self._database_breakdown = database_breakdown
    
    def set_found_other(self, count: int):
        """Set number of papers found from other sources."""
        self._counts["found_other"] = count
    
    def set_no_dupes(self, count: int):
        """Set number of unique papers after deduplication."""
        self._counts["no_dupes"] = count
    
    def set_screened(self, count: int):
        """Set number of papers that passed title/abstract screening."""
        self._counts["screened"] = count
    
    def set_screen_exclusions(self, count: int):
        """Set number of papers excluded at title/abstract screening."""
        self._counts["screen_exclusions"] = count
    
    def set_full_text_sought(self, count: int):
        """Set number of papers for which full text was sought."""
        self._counts["full_text_sought"] = count
    
    def set_full_text_not_retrieved(self, count: int):
        """Set number of papers for which full text could not be retrieved."""
        self._counts["full_text_not_retrieved"] = count
    
    def set_full_text_assessed(self, count: int):
        """Set number of papers assessed for eligibility."""
        self._counts["full_text_assessed"] = count
    
    def set_full_text_exclusions(self, count: int):
        """Set number of papers excluded at full-text screening."""
        self._counts["full_text_exclusions"] = count
    
    def set_qualitative(self, count: int):
        """Set number of studies included in qualitative synthesis."""
        self._counts["qualitative"] = count
    
    def set_quantitative(self, count: int):
        """Set number of studies included in quantitative synthesis."""
        self._counts["quantitative"] = count
    
    def get_counts(self) -> Dict[str, int]:
        """Get all PRISMA counts."""
        return self._counts.copy()
    
    def get_database_breakdown(self) -> Dict[str, int]:
        """Get database breakdown of found papers."""
        return self._database_breakdown.copy()
