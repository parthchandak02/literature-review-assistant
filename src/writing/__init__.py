"""Manuscript section writing with citation lineage."""

from src.writing.section_writer import SectionWriter
from src.writing.style_extractor import StylePatterns, extract_style_patterns

__all__ = [
    "SectionWriter",
    "StylePatterns",
    "extract_style_patterns",
]
