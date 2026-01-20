"""
Citation Management Module

Handles citation extraction, mapping, and IEEE formatting for systematic reviews.
"""

from .citation_manager import CitationManager
from .ieee_formatter import IEEEFormatter
from .bibtex_formatter import BibTeXFormatter
from .ris_formatter import RISFormatter

__all__ = ["CitationManager", "IEEEFormatter", "BibTeXFormatter", "RISFormatter"]
