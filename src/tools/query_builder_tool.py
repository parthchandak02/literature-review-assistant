"""
Query Builder Tool

Tool for building search queries.
"""

from typing import Dict, Any, List
from .tool_registry import Tool, ToolParameter
from ..search.search_strategy import SearchStrategyBuilder


def create_query_builder_tool() -> Tool:
    """
    Create query builder tool.

    Returns:
        Tool instance
    """

    def execute_build_query(
        term_groups: List[Dict[str, Any]],
        database: str = "generic",
        date_range: Dict[str, Any] = None,
        language: str = "English",
    ) -> Dict[str, Any]:
        """
        Build search query from term groups.

        Args:
            term_groups: List of term group dictionaries with 'main_term' and 'synonyms'
            database: Target database name
            date_range: Optional date range dict with 'start' and 'end'
            language: Language filter

        Returns:
            Query dictionary with 'query' and 'description'
        """
        builder = SearchStrategyBuilder()

        # Add term groups
        for group in term_groups:
            main_term = group.get("main_term", "")
            synonyms = group.get("synonyms", [])
            mesh_terms = group.get("mesh_terms")
            builder.add_term_group(main_term, synonyms, mesh_terms)

        # Set date range
        if date_range:
            start = date_range.get("start")
            end = date_range.get("end")
            builder.set_date_range(start, end)

        # Set language
        builder.set_language(language)

        # Build query
        query = builder.build_query(database)
        description = builder.get_strategy_description()

        return {"query": query, "description": description, "database": database}

    return Tool(
        name="build_search_query",
        description="Build Boolean search query from term groups for academic databases",
        parameters=[
            ToolParameter(
                name="term_groups",
                type="array",
                description="List of term group objects with 'main_term', 'synonyms', and optional 'mesh_terms'",
                required=True,
            ),
            ToolParameter(
                name="database",
                type="string",
                description="Target database: 'pubmed', 'scopus', 'wos', 'ieee', or 'generic'",
                required=False,
                enum=["pubmed", "scopus", "wos", "ieee", "generic"],
            ),
            ToolParameter(
                name="date_range",
                type="object",
                description="Optional date range with 'start' and 'end' years",
                required=False,
            ),
            ToolParameter(
                name="language",
                type="string",
                description="Language filter (default: 'English')",
                required=False,
            ),
        ],
        execute_fn=execute_build_query,
    )


class QueryBuilderTool:
    """Wrapper class for query builder tool."""

    def __init__(self):
        self.tool = create_query_builder_tool()

    def get_tool(self) -> Tool:
        """Get the tool instance."""
        return self.tool
