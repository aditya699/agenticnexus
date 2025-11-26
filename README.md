# AgenticNexus

A template for building your own MCP (Model Context Protocol) server. Use this as a starting point to create custom tools that AI assistants can use.

## What is MCP?

MCP (Model Context Protocol) is an open protocol that standardizes how AI applications connect to external tools and data sources. Built on JSON-RPC 2.0, it enables LLM hosts like Claude and ChatGPT to discover and invoke tools exposed by servers.

### How it works

```
┌─────────────────┐     JSON-RPC 2.0      ┌─────────────────┐
│   AI Assistant  │ ◄──────────────────► │   MCP Server    │
│  (Claude, GPT)  │    SSE Transport      │  (Your Tools)   │
└─────────────────┘                       └─────────────────┘
        │                                         │
        │  1. tools/list                          │
        │ ──────────────────────────────────────► │
        │                                         │
        │  2. Returns available tools             │
        │ ◄────────────────────────────────────── │
        │                                         │
        │  3. tools/call (with arguments)         │
        │ ──────────────────────────────────────► │
        │                                         │
        │  4. Returns result                      │
        │ ◄────────────────────────────────────── │
```

### Key concepts

- **Tools**: Functions the AI can call (e.g., `web_search`, `get_writing_guidelines`)
- **Transport**: Communication layer (SSE for remote servers, STDIO for local)
- **JSON Schema**: Tools define their parameters using JSON Schema for validation

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the server
python src/agenticnexus/mcp_server.py
```

Server runs at `http://localhost:8000` with SSE transport.

## Project Structure

```
src/agenticnexus/
├── mcp_server.py          # Server entry point
├── tools/
│   ├── __init__.py        # Tool registry
│   ├── search/            # Web search tool (example)
│   │   ├── __init__.py
│   │   └── utils.py
│   └── writing_style/     # Writing guidelines tool (example)
│       └── __init__.py
```

## Adding Your Own Tools

1. Create a new folder under `tools/`:
```
tools/
└── my_tool/
    └── __init__.py
```

2. Define your tool with `@mcp.tool()`:
```python
from mcp.server.fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def my_tool(param1: str, param2: int = 10) -> dict:
        """Description of what the tool does."""
        # Your logic here
        return {"result": "..."}
```

3. Register in `tools/__init__.py`:
```python
from . import search, writing_style, my_tool

def register_all_tools(mcp: FastMCP) -> None:
    search.register(mcp)
    writing_style.register(mcp)
    my_tool.register(mcp)
```

## Included Example Tools

| Tool | Description |
|------|-------------|
| `web_search` | Search the web using Parallel API |
| `get_writing_guidelines` | Get corporate writing style guide |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PARALLEL_API_KEY` | API key for Parallel web search |

## Connecting Clients

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "agenticnexus": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### OpenAI API

```python
response = client.responses.create(
    model="gpt-4.1",
    tools=[{
        "type": "mcp",
        "server_label": "agenticnexus",
        "server_url": "http://localhost:8000/sse",
        "require_approval": "never"
    }],
    input="Search for latest AI news"
)
```

### Anthropic API

```python
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    mcp_servers=[{
        "type": "url",
        "url": "http://localhost:8000/sse",
        "name": "agenticnexus"
    }],
    messages=[{"role": "user", "content": "Search for latest AI news"}]
)
```

## Learn More

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)

## License

MIT
