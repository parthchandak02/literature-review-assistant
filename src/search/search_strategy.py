"""
Search Strategy Builder

Builds Boolean search queries with MeSH terms and keyword combinations
for systematic literature reviews.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SearchTerm:
    """Represents a search term with its variations."""

    main_term: str
    synonyms: List[str]
    mesh_terms: Optional[List[str]] = None

    def to_query(self, database: str = "generic") -> str:
        """Convert to database-specific query format."""
        all_terms = [self.main_term] + self.synonyms
        if self.mesh_terms:
            all_terms.extend(self.mesh_terms)

        # Format for Boolean search
        if database.lower() == "pubmed":
            # PubMed uses [MeSH Terms] or [Title/Abstract]
            query_parts = [f'"{term}"' for term in all_terms]
            if self.mesh_terms:
                mesh_parts = [f"{term}[MeSH Terms]" for term in self.mesh_terms]
                query_parts.extend(mesh_parts)
            return " OR ".join(query_parts)
        else:
            # Generic format with quotes and OR
            return " OR ".join([f'"{term}"' for term in all_terms])


class SearchStrategyBuilder:
    """Builds comprehensive search strategies for systematic reviews."""

    def __init__(self):
        self.term_groups: List[SearchTerm] = []
        self.inclusion_criteria: List[str] = []
        self.exclusion_criteria: List[str] = []
        self.date_range: Optional[tuple] = None
        self.language: str = "English"

    def add_term_group(
        self,
        main_term: str,
        synonyms: List[str],
        mesh_terms: Optional[List[str]] = None,
    ):
        """Add a group of related search terms."""
        term = SearchTerm(main_term, synonyms, mesh_terms)
        self.term_groups.append(term)
        return self

    def set_date_range(self, start_year: Optional[int] = None, end_year: Optional[int] = None):
        """Set publication date range."""
        self.date_range = (start_year, end_year)
        return self

    def set_language(self, language: str = "English"):
        """Set language filter."""
        self.language = language
        return self

    def build_query(self, database: str = "generic") -> str:
        """
        Build Boolean search query combining all term groups.

        Args:
            database: Target database ('pubmed', 'scopus', 'wos', 'ieee', 'generic')

        Returns:
            Complete Boolean search query string
        """
        # Build query for each term group
        group_queries = [group.to_query(database) for group in self.term_groups]

        # Combine groups with AND
        combined_query = " AND ".join([f"({q})" for q in group_queries])

        # Add filters
        if self.date_range:
            start, end = self.date_range
            if start:
                combined_query += f" AND (year >= {start})"
            if end:
                combined_query += f" AND (year <= {end})"

        if self.language.lower() != "all":
            combined_query += f' AND (language: "{self.language}")'

        return combined_query

    def build_database_specific_query(self, database: str) -> str:
        """Build query optimized for specific database."""
        db_lower = database.lower()

        if db_lower == "pubmed":
            return self._build_pubmed_query()
        elif db_lower == "scopus":
            return self._build_scopus_query()
        elif db_lower == "wos" or db_lower == "webofscience":
            return self._build_wos_query()
        elif db_lower == "ieee":
            return self._build_ieee_query()
        elif db_lower == "arxiv":
            return self._build_arxiv_query()
        elif db_lower == "semantic scholar" or db_lower == "semanticscholar":
            return self._build_semantic_scholar_query()
        elif db_lower == "crossref":
            return self._build_crossref_query()
        else:
            return self.build_query("generic")

    def _build_pubmed_query(self) -> str:
        """Build PubMed-specific query with MeSH terms."""
        queries = []
        for group in self.term_groups:
            terms = [f'"{term}"[Title/Abstract]' for term in [group.main_term] + group.synonyms]
            if group.mesh_terms:
                mesh_terms = [f"{term}[MeSH Terms]" for term in group.mesh_terms]
                terms.extend(mesh_terms)
            queries.append("(" + " OR ".join(terms) + ")")

        combined = " AND ".join(queries)

        if self.date_range:
            start, end = self.date_range
            if start:
                combined += f" AND ({start}:{end or 3000}[Publication Date])"

        return combined

    def _build_scopus_query(self) -> str:
        """Build Scopus-specific query."""
        queries = []
        for group in self.term_groups:
            terms = [f'"{term}"' for term in [group.main_term] + group.synonyms]
            queries.append("(" + " OR ".join(terms) + ")")

        combined = " AND ".join(queries)

        if self.date_range:
            start, end = self.date_range
            if start:
                combined += f" AND PUBYEAR > {start - 1}"
            if end:
                combined += f" AND PUBYEAR < {end + 1}"

        return combined

    def _build_wos_query(self) -> str:
        """Build Web of Science-specific query."""
        queries = []
        for group in self.term_groups:
            terms = [f'"{term}"' for term in [group.main_term] + group.synonyms]
            queries.append("(" + " OR ".join(terms) + ")")

        combined = " AND ".join(queries)

        if self.date_range:
            start, end = self.date_range
            if start:
                combined += f" AND PY=({start}-{end or 3000})"

        return combined

    def _build_ieee_query(self) -> str:
        """Build IEEE Xplore-specific query."""
        queries = []
        for group in self.term_groups:
            terms = [f'"{term}"' for term in [group.main_term] + group.synonyms]
            queries.append("(" + " OR ".join(terms) + ")")

        combined = " AND ".join(queries)

        if self.date_range:
            start, end = self.date_range
            if start:
                combined += f" AND Year >= {start}"
            if end:
                combined += f" AND Year <= {end}"

        return combined

    def _build_arxiv_query(self) -> str:
        """Build arXiv-specific query with category filters."""
        queries = []
        for group in self.term_groups:
            # arXiv supports field-specific searches
            # Format: ti:title OR abs:abstract OR au:author
            terms = []
            for term in [group.main_term] + group.synonyms:
                # Search in title and abstract
                terms.append(f'ti:"{term}"')
                terms.append(f'abs:"{term}"')
            queries.append("(" + " OR ".join(terms) + ")")

        combined = " AND ".join(queries)

        # arXiv date filtering uses submittedDate
        if self.date_range:
            start, end = self.date_range
            if start:
                combined += f" AND submittedDate:[{start}0101* TO {end or 3000}1231*]"

        return combined

    def _build_semantic_scholar_query(self) -> str:
        """Build Semantic Scholar-specific query."""
        # Semantic Scholar uses simple text search, supports field-specific queries
        queries = []
        for group in self.term_groups:
            # Combine all terms with OR
            terms = [group.main_term] + group.synonyms
            # Semantic Scholar supports field queries like title:term, abstract:term
            term_parts = [f'"{term}"' for term in terms]
            queries.append("(" + " OR ".join(term_parts) + ")")

        combined = " AND ".join(queries)

        # Semantic Scholar date filtering uses year parameter in API, not query
        # But we can add it as a note in the query string
        if self.date_range:
            start, end = self.date_range
            # Note: Semantic Scholar API handles year filtering separately
            # This is just for documentation
            combined += f" [year: {start or 'any'} to {end or 'present'}]"

        return combined

    def _build_crossref_query(self) -> str:
        """Build Crossref-specific query with filter syntax."""
        # Crossref uses simple query strings, filters are applied via API parameters
        queries = []
        for group in self.term_groups:
            terms = [group.main_term] + group.synonyms
            term_parts = [f'"{term}"' for term in terms]
            queries.append("(" + " OR ".join(term_parts) + ")")

        combined = " AND ".join(queries)

        # Crossref date filtering is done via API filters, not query string
        # This query string is for the query.bibliographic parameter
        return combined

    def get_strategy_description(self) -> str:
        """Get human-readable description of search strategy."""
        desc = "Search Strategy:\n\n"
        desc += "Term Groups:\n"
        for i, group in enumerate(self.term_groups, 1):
            desc += f"{i}. {group.main_term}: {', '.join(group.synonyms)}\n"
            if group.mesh_terms:
                desc += f"   MeSH Terms: {', '.join(group.mesh_terms)}\n"

        if self.date_range:
            start, end = self.date_range
            desc += f"\nDate Range: {start or 'Any'} to {end or 'Present'}\n"

        desc += f"\nLanguage: {self.language}\n"

        return desc

    def get_database_queries(self) -> Dict[str, str]:
        """
        Get optimized queries for all supported databases.

        Returns:
            Dictionary mapping database names to their optimized queries
        """
        databases = [
            "PubMed",
            "Scopus",
            "Web of Science",
            "IEEE",
            "arXiv",
            "Semantic Scholar",
            "Crossref",
        ]

        queries = {}
        for db in databases:
            queries[db] = self.build_database_specific_query(db)

        return queries


def create_example_strategy() -> SearchStrategyBuilder:
    """Create example search strategy based on example-task-list.md."""
    builder = SearchStrategyBuilder()

    # Telemedicine terms
    builder.add_term_group(
        main_term="telemedicine",
        synonyms=["remote healthcare", "digital health", "telehealth"],
        mesh_terms=["Telemedicine"],
    )

    # UX Design terms
    builder.add_term_group(
        main_term="user experience",
        synonyms=["UX", "interface design", "user-centered design", "usability"],
        mesh_terms=["User-Computer Interface"],
    )

    # Adaptivity terms
    builder.add_term_group(
        main_term="adaptive interface",
        synonyms=["personalized design", "responsive systems", "adaptive systems"],
    )

    # Diversity terms
    builder.add_term_group(
        main_term="diverse populations",
        synonyms=["health disparities", "equity", "accessibility", "inclusive design"],
        mesh_terms=["Health Status Disparities", "Healthcare Disparities"],
    )

    builder.set_date_range(end_year=2022)
    builder.set_language("English")

    return builder
