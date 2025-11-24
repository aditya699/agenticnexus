# AgenticNexus

MCP and A2A backend for AI agent integration. Self-hosted.

## Stack
- Python 3.13.7, FastAPI 0.121.3, Pydantic 2.12.4, uv

## Structure
```
src/agenticnexus/
├── main.py              # FastAPI entry point
├── config.py            # Settings
├── mcp/
│   ├── models.py        # MCP request/response schemas
│   └── server.py        # MCP endpoints
└── tools/
    ├── schemas.py       # ToolSchema (MCP), ToolDefinition (internal)
    ├── base.py          # TOOL_REGISTRY, @tool decorator
    ├── core/            # Built-in tools
    └── custom/          # Company tools
```

## Commands
```bash
.venv\Scripts\activate
uv pip install -r requirements-dev.txt
python -m uvicorn src.agenticnexus.main:app --reload
```

## Status
- [x] tools/schemas.py
- [x] tools/base.py
- [ ] tools/core/search/
- [ ] mcp/models.py
- [ ] mcp/server.py
- [ ] main.py