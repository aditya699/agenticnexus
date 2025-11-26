"""
Search tools for AgenticNexus MCP Server.
"""
from mcp.server.fastmcp import FastMCP

from .utils import search_web


def register(mcp: FastMCP) -> None:
    """Register search tools with the MCP server."""

    @mcp.tool()
    async def web_search(
        objective: str,
        search_queries: list[str],
        max_results: int = 5,
        max_chars_per_result: int = 500
    ) -> dict:
        """Search the web for information using multiple search queries to achieve an objective.

        Args:
            objective: High-level goal (e.g., "Latest news in India")
            search_queries: List of specific search queries
            max_results: Maximum number of results to return
            max_chars_per_result: Maximum characters per result excerpt
        """
        return await search_web(
            objective=objective,
            search_queries=search_queries,
            max_results=max_results,
            max_chars_per_result=max_chars_per_result
        )
