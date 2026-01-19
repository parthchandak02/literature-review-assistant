"""
Database Search Tool

Tool for searching academic databases.
"""

from typing import Dict, Any, List
from .tool_registry import Tool, ToolParameter
from ..search.database_connectors import MultiDatabaseSearcher, MockConnector


def create_database_search_tool(searcher: MultiDatabaseSearcher) -> Tool:
    """
    Create database search tool.

    Args:
        searcher: MultiDatabaseSearcher instance

    Returns:
        Tool instance
    """

    def execute_search(query: str, databases: List[str], max_results: int = 100) -> Dict[str, Any]:
        """
        Execute database search.

        Args:
            query: Search query
            databases: List of database names to search
            max_results: Maximum results per database

        Returns:
            Search results dictionary
        """
        # Add connectors if not already added
        for db_name in databases:
            connector = MockConnector(db_name)
            searcher.add_connector(connector)

        papers = searcher.search_all_combined(query, max_results)

        return {
            "total_results": len(papers),
            "papers": [
                {
                    "title": p.title,
                    "abstract": p.abstract[:200] if p.abstract else "",
                    "authors": p.authors,
                    "year": p.year,
                    "doi": p.doi,
                    "database": p.database,
                }
                for p in papers[:max_results]
            ],
        }

    return Tool(
        name="database_search",
        description="Search academic databases (PubMed, Scopus, Web of Science, etc.) for research papers",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Search query string",
                required=True,
            ),
            ToolParameter(
                name="databases",
                type="array",
                description="List of databases to search (e.g., ['PubMed', 'Scopus'])",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type="number",
                description="Maximum number of results per database",
                required=False,
            ),
        ],
        execute_fn=execute_search,
    )


class DatabaseSearchTool:
    """Wrapper class for database search tool."""

    def __init__(self, searcher: MultiDatabaseSearcher):
        self.searcher = searcher
        self.tool = create_database_search_tool(searcher)

    def get_tool(self) -> Tool:
        """Get the tool instance."""
        return self.tool
