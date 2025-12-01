"""
Writing style prompt for AgenticNexus MCP Server.
Provides NovaTech Solutions corporate writing style template.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register writing style prompt with the MCP server."""

    @mcp.prompt() # You can use a prompt also in an mcp server not always tool
    def novatech_writing_style(content: str) -> str:
        """Rewrite content in NovaTech Solutions corporate style.
        
        Use this prompt to transform any text into NovaTech's professional,
        innovative, and approachable corporate voice.
        
        Args:
            content: The text content to rewrite in NovaTech style
        """
        return f"""Please rewrite the following content using NovaTech Solutions writing style:

STYLE GUIDELINES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPANY: NovaTech Solutions

TONE: Professional yet approachable, innovative, forward-thinking

CORE PRINCIPLES:
- Lead with value and impact
- Use active voice
- Keep sentences concise (max 20 words ideal)
- Avoid jargon unless industry-standard
- Include data/metrics when possible

VOCABULARY:
✓ PREFERRED: innovative, streamlined, scalable, data-driven, seamless
✗ AVOID: synergy, leverage, circle back, touch base, bandwidth

FORMATTING:
- Headers: Title Case
- Bullets: Start with action verbs
- Paragraphs: Max 3-4 sentences

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTENT TO REWRITE:
{content}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please rewrite the above content following all NovaTech style guidelines. Ensure the rewritten version:
1. Maintains the original meaning and key information
2. Applies NovaTech's professional yet approachable tone
3. Uses preferred vocabulary and avoids discouraged terms
4. Follows formatting guidelines
5. Leads with value and impact"""