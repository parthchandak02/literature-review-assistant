"""
Citation Management Module

Handles citation extraction, mapping, and IEEE formatting for systematic reviews.
"""

from .citation_manager import CitationManager
from .ieee_formatter import IEEEFormatter

__all__ = ["CitationManager", "IEEEFormatter"]
