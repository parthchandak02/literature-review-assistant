"""
Tavily Search Tool

Wrapper for Tavily API to provide search capabilities as a tool.
"""

import os
from typing import Dict, Any, Optional, List
import logging

from .tool_registry import Tool, ToolParameter

logger = logging.getLogger(__name__)


class TavilySearchTool:
    """Tool wrapper for Tavily search API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Tavily search tool.

        Args:
            api_key: Tavily API key (defaults to TAVILY_API_KEY env var)
        """
        try:
            from tavily import TavilyClient

            self.client = TavilyClient(api_key=api_key or os.getenv("TAVILY_API_KEY"))
        except ImportError:
            raise ImportError(
                "tavily-python library not installed. Install with: pip install tavily-python"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Tavily client: {e}")
            raise

    def search(self, query: str, max_results: int = 10, **kwargs) -> Dict[str, Any]:
        """
        Web search with real-time results.

        Args:
            query: Search query
            max_results: Maximum number of results
            **kwargs: Additional search parameters

        Returns:
            Search results
        """
        return self.client.search(query, max_results=max_results, **kwargs)

    def extract(self, urls: List[str], **kwargs) -> Dict[str, Any]:
        """
        Extract content from URLs.

        Args:
            urls: List of URLs to extract
            **kwargs: Additional parameters

        Returns:
            Extracted content
        """
        return self.client.extract(urls=urls, **kwargs)

    def crawl(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Crawl website starting from URL.

        Args:
            url: Starting URL
            **kwargs: Additional crawl parameters

        Returns:
            Crawl results
        """
        return self.client.crawl(url=url, **kwargs)

    def map(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Map website structure (sitemap).

        Args:
            url: Base URL to map
            **kwargs: Additional mapping parameters

        Returns:
            Site map results
        """
        return self.client.map(url=url, **kwargs)

    def research(self, input_query: str, model: str = "pro", stream: bool = False, **kwargs) -> Any:
        """
        Deep research with streaming support.

        Args:
            input_query: Research query
            model: Research model to use
            stream: Whether to stream results
            **kwargs: Additional parameters

        Returns:
            Research results
        """
        return self.client.research(input=input_query, model=model, stream=stream, **kwargs)


def create_tavily_search_tool(api_key: Optional[str] = None) -> Tool:
    """
    Create Tavily search tool for tool registry.

    Args:
        api_key: Tavily API key

    Returns:
        Tool instance
    """
    tavily_client = TavilySearchTool(api_key=api_key)

    def execute_search(query: str, max_results: int = 10) -> Dict[str, Any]:
        """Execute Tavily search."""
        try:
            results = tavily_client.search(query, max_results=max_results)
            return {
                "results": results.get("results", []) if isinstance(results, dict) else results,
                "query": query,
            }
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            raise

    return Tool(
        name="tavily_search",
        description="Search the web using Tavily AI search engine. Returns real-time, accurate search results.",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Search query string",
                required=True,
            ),
            ToolParameter(
                name="max_results",
                type="number",
                description="Maximum number of results to return (default: 10)",
                required=False,
            ),
        ],
        execute_fn=execute_search,
    )


def create_tavily_extract_tool(api_key: Optional[str] = None) -> Tool:
    """
    Create Tavily extract tool for tool registry.

    Args:
        api_key: Tavily API key

    Returns:
        Tool instance
    """
    tavily_client = TavilySearchTool(api_key=api_key)

    def execute_extract(urls: List[str]) -> Dict[str, Any]:
        """Execute Tavily extract."""
        try:
            return tavily_client.extract(urls=urls)
        except Exception as e:
            logger.error(f"Tavily extract failed: {e}")
            raise

    return Tool(
        name="tavily_extract",
        description="Extract content from web pages using Tavily. Efficiently retrieves text content from URLs.",
        parameters=[
            ToolParameter(
                name="urls",
                type="array",
                description="List of URLs to extract content from",
                required=True,
            )
        ],
        execute_fn=execute_extract,
    )
