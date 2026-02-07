"""
Citation Management Module

Handles citation extraction, mapping, and IEEE formatting for systematic reviews.
"""

from .bibtex_formatter import BibTeXFormatter
from .citation_manager import CitationManager
from .csl_formatter import CSLFormatter
from .ieee_formatter import IEEEFormatter
from .manubot_resolver import ManubotCitationResolver
from .ris_formatter import RISFormatter

__all__ = [
    "BibTeXFormatter",
    "CSLFormatter",
    "CitationManager",
    "IEEEFormatter",
    "ManubotCitationResolver",
    "RISFormatter",
]
