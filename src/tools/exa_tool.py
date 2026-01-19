"""
Exa Search Tool

Wrapper for Exa API to provide search capabilities as a tool.
"""

import os
from typing import Dict, Any, Optional
import logging

from .tool_registry import Tool, ToolParameter

logger = logging.getLogger(__name__)


class ExaSearchTool:
    """Tool wrapper for Exa search API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Exa search tool.

        Args:
            api_key: Exa API key (defaults to EXA_API_KEY env var)
        """
        try:
            from exa_py import Exa

            self.client = Exa(api_key=api_key or os.getenv("EXA_API_KEY"))
        except ImportError:
            raise ImportError("exa_py library not installed. Install with: pip install exa_py")
        except Exception as e:
            logger.error(f"Failed to initialize Exa client: {e}")
            raise

    def search(self, query: str, num_results: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Basic search.

        Args:
            query: Search query
            num_results: Number of results to return
            **kwargs: Additional search parameters

        Returns:
            Search results
        """
        return self.client.search(query, num_results=num_results, **kwargs)

    def search_with_contents(self, query: str, num_results: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Search with text content.

        Args:
            query: Search query
            num_results: Number of results to return
            **kwargs: Additional search parameters

        Returns:
            Search results with content
        """
        return self.client.search_and_contents(query, num_results=num_results, text=True, **kwargs)

    def answer(self, query: str, **kwargs) -> str:
        """
        Generate answer from search results.

        Args:
            query: Query to answer
            **kwargs: Additional parameters

        Returns:
            Answer text
        """
        response = self.client.answer(query, **kwargs)
        return response if isinstance(response, str) else str(response)

    def research(
        self,
        instructions: str,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Deep research with structured output.

        Args:
            instructions: Research instructions
            output_schema: Optional output schema
            **kwargs: Additional parameters

        Returns:
            Research results
        """
        return self.client.research.create_task(
            instructions=instructions, output_schema=output_schema, **kwargs
        )


def create_exa_search_tool(api_key: Optional[str] = None) -> Tool:
    """
    Create Exa search tool for tool registry.

    Args:
        api_key: Exa API key

    Returns:
        Tool instance
    """
    exa_client = ExaSearchTool(api_key=api_key)

    def execute_search(query: str, num_results: int = 10) -> Dict[str, Any]:
        """Execute Exa search."""
        try:
            results = exa_client.search(query, num_results=num_results)
            return {
                "results": results.results if hasattr(results, "results") else results,
                "query": query,
            }
        except Exception as e:
            logger.error(f"Exa search failed: {e}")
            raise

    return Tool(
        name="exa_search",
        description="Search the web using Exa AI search engine. Returns ranked search results with metadata.",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Search query string",
                required=True,
            ),
            ToolParameter(
                name="num_results",
                type="number",
                description="Number of results to return (default: 10)",
                required=False,
            ),
        ],
        execute_fn=execute_search,
    )


def create_exa_answer_tool(api_key: Optional[str] = None) -> Tool:
    """
    Create Exa answer tool for tool registry.

    Args:
        api_key: Exa API key

    Returns:
        Tool instance
    """
    exa_client = ExaSearchTool(api_key=api_key)

    def execute_answer(query: str) -> str:
        """Execute Exa answer."""
        try:
            return exa_client.answer(query)
        except Exception as e:
            logger.error(f"Exa answer failed: {e}")
            raise

    return Tool(
        name="exa_answer",
        description="Get a natural language answer to a question using Exa AI search engine.",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Question to answer",
                required=True,
            )
        ],
        execute_fn=execute_answer,
    )
