"""
AgenticNexus Tools Registry.

This module provides centralized tool registration for the MCP server.
"""
from mcp.server.fastmcp import FastMCP

from . import search, writing_style


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tools with the MCP server.

    Args:
        mcp: The FastMCP server instance
    """
    search.register(mcp)
    writing_style.register(mcp)
