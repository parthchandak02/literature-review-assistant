"""
Paper Enrichment Module

Enriches existing Paper objects with missing metadata (affiliations, countries, etc.)
by fetching data from external APIs like Crossref.
"""

from .paper_enricher import PaperEnricher

__all__ = ["PaperEnricher"]
