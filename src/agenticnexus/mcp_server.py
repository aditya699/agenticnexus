"""
AgenticNexus MCP Server - SSE Transport.
"""
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agenticnexus.tools import register_all_tools

load_dotenv()

mcp = FastMCP(name="agenticnexus", host="0.0.0.0", port=8000)
register_all_tools(mcp)


if __name__ == "__main__":
    mcp.run(transport="sse")
