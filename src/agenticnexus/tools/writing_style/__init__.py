"""
Writing style tool for AgenticNexus MCP Server.
Mimics NovaTech Solutions corporate writing style.
"""
from mcp.server.fastmcp import FastMCP


# NovaTech Solutions Writing Style Guide
NOVATECH_STYLE = {
    "company": "NovaTech Solutions",
    "tone": "Professional yet approachable, innovative, forward-thinking",
    "principles": [
        "Lead with value and impact",
        "Use active voice",
        "Keep sentences concise (max 20 words ideal)",
        "Avoid jargon unless industry-standard",
        "Include data/metrics when possible",
    ],
    "vocabulary": {
        "preferred": ["innovative", "streamlined", "scalable", "data-driven", "seamless"],
        "avoid": ["synergy", "leverage", "circle back", "touch base", "bandwidth"],
    },
    "formatting": {
        "headers": "Title Case",
        "bullets": "Start with action verbs",
        "paragraphs": "Max 3-4 sentences",
    },
}


def register(mcp: FastMCP) -> None:
    """Register writing style tools with the MCP server."""

    @mcp.tool()
    async def get_writing_guidelines() -> dict:
        """Get NovaTech Solutions writing style guidelines. Use this before drafting any document to ensure consistent corporate voice and formatting."""
        return NOVATECH_STYLE
