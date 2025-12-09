# MCP (Model Context Protocol) - Complete Production Guide

**From First Principles to Production Implementation**

---

## Table of Contents

1. [Foundation: What is a Protocol?](#1-foundation-what-is-a-protocol)
2. [JSON-RPC: The Wire Protocol](#2-json-rpc-the-wire-protocol)
3. [Transport Layer](#3-transport-layer)
4. [MCP Server Basics](#4-mcp-server-basics)
5. [Tools](#5-tools)
6. [Resources](#6-resources)
7. [Prompts](#7-prompts)
8. [Context Object](#8-context-object)
9. [Lifespan Management](#9-lifespan-management)
10. [Structured Output](#10-structured-output)
11. [Elicitation](#11-elicitation)
12. [Completions](#12-completions)
13. [Sampling](#13-sampling)
14. [Images and Icons](#14-images-and-icons)
15. [Production Configuration](#15-production-configuration)
16. [Common Issues and Debugging](#16-common-issues-and-debugging)

---

## 1. Foundation: What is a Protocol?

### Definition

A **protocol** is an agreed-upon set of rules for communication between two parties.

Human example:
- Phone rings → you say "Hello"
- Other person identifies themselves
- Conversation happens
- Someone says "Bye" → call ends

Both parties know the rules. Communication works.

### What a Protocol Defines

1. **Request schema** - what client sends
2. **Response schema** - what server returns
3. **Order** - who speaks when
4. **Error handling** - what happens when things fail

### Protocol Layers

Protocols stack on top of each other:

```
┌─────────────────────────────────────────┐
│  Layer 7: APPLICATION                   │
│  "What does the message MEAN?"          │
│  Example: MCP, HTTP, FTP, SMTP          │
├─────────────────────────────────────────┤
│  Layer 6: PRESENTATION                  │
│  "How is data ENCODED?"                 │
│  Example: JSON, XML, Protobuf           │
├─────────────────────────────────────────┤
│  Layer 5: SESSION                       │
│  "How do we maintain CONVERSATION?"     │
│  Example: Sessions, cookies             │
├─────────────────────────────────────────┤
│  Layer 4: TRANSPORT                     │
│  "How do we ensure DELIVERY?"           │
│  Example: TCP (reliable), UDP (fast)    │
├─────────────────────────────────────────┤
│  Layer 3: NETWORK                       │
│  "How do we ROUTE to destination?"      │
│  Example: IP addresses                  │
└─────────────────────────────────────────┘
```

### Where MCP Fits

```
┌─────────────────────────────────────────┐
│  MCP Protocol (Application semantics)   │  ← "call tool X"
├─────────────────────────────────────────┤
│  JSON-RPC 2.0 (Message format)          │  ← "id:1, method:..."
├─────────────────────────────────────────┤
│  JSON (Data encoding)                   │  ← {"key": "value"}
├─────────────────────────────────────────┤
│  SSE / HTTP (Transport)                 │  ← GET, POST, streams
├─────────────────────────────────────────┤
│  TCP/IP (Network delivery)              │  ← packets, routing
└─────────────────────────────────────────┘
```

---

## 2. JSON-RPC: The Wire Protocol

### What is RPC?

**RPC = Remote Procedure Call** - calling a function on another machine as if it were local.

```python
# Local function call
result = add(2, 3)  # Runs in same process

# RPC: same semantics, different machine
result = remote_server.add(2, 3)  # Runs on different machine
```

### What Happens Behind the Scenes

1. **Serialize**: Convert `2, 3` into JSON
2. **Transport**: Send over network
3. **Deserialize**: Other machine converts back to numbers
4. **Execute**: Function runs
5. **Return path**: Result goes back the same way

### JSON-RPC Message Types

**1. Request (expects response):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "web_search",
    "arguments": {"query": "MCP protocol"}
  }
}
```

**2. Response (answers a request):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "Results..."}]
  }
}
```

**3. Notification (no response expected, no `id`):**
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/progress",
  "params": {"progress": 0.5, "total": 1.0}
}
```

### Why Request IDs Matter

Multiple requests can be in-flight simultaneously:

```
Client                          Server
  │                               │
  │─── {id:1, "search foo"} ─────▶│
  │─── {id:2, "search bar"} ─────▶│  (sent before id:1 returns)
  │─── {id:3, "calculate"} ──────▶│
  │                               │
  │◀── {id:3, result:42} ─────────│  (id:3 finishes first!)
  │◀── {id:1, result:"..."} ──────│
  │◀── {id:2, result:"..."} ──────│
```

Without IDs, client can't match responses to requests.

### Error Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": {"details": "..."}
  }
}
```

Standard error codes:
- `-32700` Parse error
- `-32600` Invalid request
- `-32601` Method not found
- `-32602` Invalid params

---

## 3. Transport Layer

### Available Transports

| Transport | How it works | Use case |
|-----------|--------------|----------|
| **stdio** | stdin/stdout pipes | Local, client launches server |
| **SSE** | GET /sse + POST /messages | Network, browser clients |
| **Streamable HTTP** | Single POST /mcp endpoint | Production, scalable |

### stdio Transport

Every program has three streams:
- **stdin** - input
- **stdout** - output
- **stderr** - errors

MCP over stdio:
```
┌────────────┐  JSON-RPC   ┌────────────┐
│ MCP Client │ ──────────▶ │ MCP Server │
│            │   (stdin)   │            │
│            │ ◀────────── │            │
│            │  (stdout)   │            │
└────────────┘             └────────────┘
```

**When to use:** Local tools, Claude Desktop integration.

### SSE Transport (Server-Sent Events)

HTTP connection that stays open. Server pushes whenever it wants.

```
Client                     Server
  │                          │
  │── GET /sse ─────────────▶│
  │◀─── connection open ─────│
  │                          │
  │◀─── event: progress ─────│  (server pushes)
  │◀─── event: result ───────│  (server pushes)
```

**Problem:** SSE is server→client only.

**Solution:** Use two channels:
- `GET /sse` - receive messages
- `POST /messages` - send messages

**Session ID:** Links POST requests to correct SSE connection.

```
1. Client: GET /sse
2. Server: Returns session_id in first message
3. Client: POST /messages?session_id=abc123
4. Server: Routes response to correct SSE connection
```

### Streamable HTTP Transport

Single endpoint handles everything:

```
POST /mcp → Send request, get response
```

**Advantages:**
- Simpler than SSE (one endpoint)
- Supports stateless mode (better scaling)
- Recommended for production

**Configuration:**
```python
# Stateless with JSON responses (recommended for production)
mcp = FastMCP("Server", stateless_http=True, json_response=True)

# Stateful with session persistence
mcp = FastMCP("Server")
```

### When to Use Which

| Use Case | Transport |
|----------|-----------|
| Local CLI tool | stdio |
| Claude Desktop | stdio |
| Browser client | SSE or Streamable HTTP |
| Production API | Streamable HTTP (stateless) |
| Need real-time progress | SSE |

---

## 4. MCP Server Basics

### Minimal Server

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyServer")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

### Running the Server

```bash
# Default (stdio)
python server.py

# With SSE transport
python server.py  # if mcp.run(transport="sse")

# With streamable HTTP
python server.py  # if mcp.run(transport="streamable-http")

# Using MCP CLI
uv run mcp run server.py
uv run mcp dev server.py  # Development mode with inspector
```

### Server Configuration

```python
mcp = FastMCP(
    name="MyServer",
    host="0.0.0.0",           # Listen on all interfaces
    port=8000,                 # Port number
    stateless_http=True,       # Stateless mode (for scaling)
    json_response=True,        # JSON instead of SSE streaming
)
```

---

## 5. Tools

### What are Tools?

Tools are functions that LLMs can invoke. They perform actions and have side effects.

### Basic Tool

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="Tool Example")

@mcp.tool()
def calculate(expression: str) -> float:
    """Evaluate a math expression."""
    return eval(expression)

@mcp.tool()
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get weather for a city."""
    # Call weather API...
    return f"Weather in {city}: 22°{unit[0].upper()}"
```

### Type Hints Generate Schema

```python
@mcp.tool()
def search(query: str, max_results: int = 10) -> str:
    ...
```

Becomes:
```json
{
  "name": "search",
  "description": "...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "max_results": {"type": "integer", "default": 10}
    },
    "required": ["query"]
  }
}
```

### Async Tools

```python
@mcp.tool()
async def fetch_data(url: str) -> str:
    """Fetch data from URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
```

---

## 6. Resources

### What are Resources?

Resources expose data to LLMs. Like GET endpoints - read-only, no side effects.

### Basic Resource

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="Resource Example")

@mcp.resource("config://settings")
def get_settings() -> str:
    """Get application settings."""
    return '{"theme": "dark", "language": "en"}'

@mcp.resource("file://documents/{name}")
def read_document(name: str) -> str:
    """Read a document by name."""
    return f"Content of {name}"
```

### Resource URI Templates

```python
@mcp.resource("db://users/{user_id}")
def get_user(user_id: str) -> str:
    """Get user by ID."""
    user = database.get(user_id)
    return json.dumps(user)
```

---

## 7. Prompts

### What are Prompts?

Reusable templates for LLM interactions. User-controlled.

### Basic Prompt

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="Prompt Example")

@mcp.prompt()
def code_review(code: str, language: str = "python") -> str:
    """Generate a code review prompt."""
    return f"Please review this {language} code:\n\n{code}"

@mcp.prompt()
def summarize(text: str, style: str = "brief") -> str:
    """Generate a summarization prompt."""
    styles = {
        "brief": "Summarize in 2-3 sentences",
        "detailed": "Provide a detailed summary",
        "bullets": "Summarize as bullet points"
    }
    return f"{styles[style]}:\n\n{text}"
```

---

## 8. Context Object

### What is Context?

Context is automatically injected into tools. Provides access to MCP capabilities.

### Getting Context

```python
from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP(name="Context Example")

@mcp.tool()
async def my_tool(query: str, ctx: Context) -> str:
    """Tool with context access."""
    # ctx is automatically injected
    await ctx.info(f"Processing: {query}")
    return "Done"
```

### Context Capabilities

**Logging:**
```python
await ctx.debug("Debug message")
await ctx.info("Info message")
await ctx.warning("Warning message")
await ctx.error("Error message")
```

**Progress Reporting:**
```python
@mcp.tool()
async def long_task(ctx: Context) -> str:
    for i in range(10):
        await ctx.report_progress(
            progress=i/10,
            total=1.0,
            message=f"Step {i+1}/10"
        )
        await do_step(i)
    return "Complete"
```

**Resource Reading:**
```python
content = await ctx.read_resource("file://config.json")
```

**Request Metadata:**
```python
request_id = ctx.request_id
client_id = ctx.client_id
```

---

## 9. Lifespan Management

### The Problem

You need resources (database, HTTP client) that:
- Initialize once at startup
- Are reused across requests
- Clean up at shutdown

### The Solution

```python
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP

class Database:
    @classmethod
    async def connect(cls):
        # Connect to database
        return cls()
    
    async def disconnect(self):
        # Clean up
        pass
    
    def query(self, sql: str):
        return "results"

@dataclass
class AppContext:
    db: Database

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    # Startup
    db = await Database.connect()
    try:
        yield AppContext(db=db)
    finally:
        # Shutdown
        await db.disconnect()

mcp = FastMCP("My App", lifespan=app_lifespan)

@mcp.tool()
def query_db(sql: str, ctx: Context) -> str:
    """Query the database."""
    db = ctx.request_context.lifespan_context.db
    return db.query(sql)
```

### How It Works

```
Server starts
    │
    ▼
┌─────────────────┐
│ Lifespan START  │ ← db = Database.connect()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Server running  │ ← Handle requests (use db)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Lifespan END    │ ← db.disconnect()
└─────────────────┘
```

---

## 10. Structured Output

### Unstructured vs Structured

**Unstructured:**
```python
@mcp.tool()
def get_weather(city: str) -> str:
    return "Temperature: 22.5, Humidity: 45%"
```

**Structured:**
```python
from pydantic import BaseModel

class WeatherData(BaseModel):
    temperature: float
    humidity: float
    condition: str

@mcp.tool()
def get_weather(city: str) -> WeatherData:
    return WeatherData(
        temperature=22.5,
        humidity=45.0,
        condition="sunny"
    )
```

### Supported Return Types

| Type | Structured? |
|------|-------------|
| `str`, `int`, `float` | No (wrapped in `{"result": value}`) |
| `BaseModel` | Yes |
| `TypedDict` | Yes |
| `@dataclass` | Yes |
| `dict[str, T]` | Yes |

### How Constrained Decoding Works

LLMs generate tokens with probabilities. Structured output **masks invalid tokens**.

```
Schema: {"name": string}

Step 1: Must start with "{"
        Valid tokens: ["{"]  → Output: "{"

Step 2: Must have key
        Valid tokens: ['"name"']  → Output: '"name"'

Step 3: Must have colon
        Valid tokens: [":"]  → Output: ":"

Step 4: Must have string value
        Model chooses content: "Alice"
```

Structure is enforced. Content is model's choice.

---

## 11. Elicitation

### What is Elicitation?

Ask user for input mid-tool-execution.

### Form Mode

```python
from pydantic import BaseModel, Field

class BookingPreferences(BaseModel):
    confirm: bool = Field(description="Confirm booking?")
    date: str = Field(default="2024-12-26")

@mcp.tool()
async def book_table(date: str, ctx: Context) -> str:
    if not is_available(date):
        result = await ctx.elicit(
            message=f"Date {date} unavailable. Try another?",
            schema=BookingPreferences
        )
        
        if result.action == "accept" and result.data.confirm:
            return f"Booked for {result.data.date}"
        return "Cancelled"
    
    return f"Booked for {date}"
```

### URL Mode

For sensitive operations (payments, OAuth):

```python
@mcp.tool()
async def make_payment(amount: float, ctx: Context) -> str:
    result = await ctx.elicit_url(
        message=f"Confirm payment of ${amount}",
        url=f"https://payment.com/pay?amount={amount}"
    )
    
    if result.action == "accept":
        return "Payment initiated"
    return "Payment cancelled"
```

### Response Actions

```python
result = await ctx.elicit(...)

result.action  # "accept" | "decline" | "cancel"
result.data    # User's form data (if accepted)
```

---

## 12. Completions

### What are Completions?

Autocomplete suggestions for prompt arguments and resource templates.

### How It Works

```
User types: "mod"

Client asks server: "What matches 'mod' for owner field?"

Server responds: ["modelcontextprotocol", "modelsource", "modular"]

Client shows dropdown.
```

### Context-Aware Completions

```python
# User picked owner = "modelcontextprotocol"
# Now completing "repo"

result = await session.complete(
    ref=ResourceTemplateReference(uri="github://{owner}/{repo}"),
    argument={"name": "repo", "value": ""},
    context_arguments={"owner": "modelcontextprotocol"}
)
# Returns: ["python-sdk", "typescript-sdk", "servers"]
```

---

## 13. Sampling

### What is Sampling?

Tool asks client's LLM to generate text.

### When to Use

Your tool needs text generation but doesn't have LLM access.

```python
@mcp.tool()
async def generate_poem(topic: str, ctx: Context) -> str:
    """Generate a poem using client's LLM."""
    result = await ctx.session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(type="text", text=f"Write a poem about {topic}")
            )
        ],
        max_tokens=100
    )
    return result.content.text
```

### Flow

```
LLM → calls your tool → tool asks LLM to generate → tool returns result
```

---

## 14. Images and Icons

### Returning Images

```python
from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

@mcp.tool()
def create_thumbnail(image_path: str) -> Image:
    """Create a thumbnail."""
    img = PILImage.open(image_path)
    img.thumbnail((100, 100))
    return Image(data=img.tobytes(), format="png")
```

### Server Icons

```python
from mcp.server.fastmcp import FastMCP, Icon

icon = Icon(src="icon.png", mimeType="image/png", sizes="64x64")

mcp = FastMCP("My Server", icons=[icon])

@mcp.tool(icons=[icon])
def my_tool():
    return "result"
```

---

## 15. Production Configuration

### Recommended Setup

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="ProductionServer",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,    # Better scaling
    json_response=True,     # Simpler responses
)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Mounting Multiple Servers

```python
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount

api_mcp = FastMCP("API", stateless_http=True, json_response=True)
chat_mcp = FastMCP("Chat", stateless_http=True, json_response=True)

@api_mcp.tool()
def api_status() -> str:
    return "API running"

@chat_mcp.tool()
def send_message(msg: str) -> str:
    return f"Sent: {msg}"

@contextlib.asynccontextmanager
async def lifespan(app):
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(api_mcp.session_manager.run())
        await stack.enter_async_context(chat_mcp.session_manager.run())
        yield

app = Starlette(
    routes=[
        Mount("/api", app=api_mcp.streamable_http_app()),
        Mount("/chat", app=chat_mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)
```

### CORS Configuration

For browser-based clients:

```python
from starlette.middleware.cors import CORSMiddleware

app = CORSMiddleware(
    app,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    expose_headers=["Mcp-Session-Id"],
)
```

---

## 16. Common Issues and Debugging

### Issue: Connection Refused

**Symptom:**
```
ECONNREFUSED ::1:8000
```

**Cause:** IPv6 vs IPv4 mismatch.

**Fix:** Use `127.0.0.1` instead of `localhost`:
```
http://127.0.0.1:8000/sse
```

### Issue: OPTIONS 405 Method Not Allowed

**Symptom:**
```
OPTIONS /sse HTTP/1.1" 405 Method Not Allowed
```

**Cause:** CORS preflight failing. Server doesn't handle OPTIONS.

**Fix:** 
1. Use "Via Proxy" mode in MCP Inspector
2. Or add CORS middleware
3. Or use streamable-http transport

### Issue: 404 on Root

**Symptom:**
```
GET / HTTP/1.1" 404 Not Found
```

**Cause:** MCP doesn't serve at `/`.

**Fix:** Use correct endpoint:
- SSE: `/sse`
- Streamable HTTP: `/mcp`

### Testing SSE Endpoint

```bash
curl -N http://localhost:8000/sse
```

Should see:
```
event: endpoint
data: /messages/?session_id=xxx

: ping - 2025-12-09 ...
```

### MCP Inspector Connection Modes

| Mode | Path | Works? |
|------|------|--------|
| Direct | Browser → Server | May fail (CORS) |
| Via Proxy | Browser → Inspector Backend → Server | Works |

---

## Quick Reference

### Message Types

| Type | Has ID? | Expects Response? |
|------|---------|-------------------|
| Request | Yes | Yes |
| Response | Yes (matches request) | No |
| Notification | No | No |

### Three Primitives

| Primitive | Control | Purpose |
|-----------|---------|---------|
| Tools | LLM decides | Actions with side effects |
| Resources | App loads | Read-only data |
| Prompts | User selects | Reusable templates |

### Context Methods

| Method | Purpose |
|--------|---------|
| `ctx.debug/info/warning/error` | Logging |
| `ctx.report_progress` | Progress updates |
| `ctx.read_resource` | Read other resources |
| `ctx.elicit` | Ask user for input |

### Transport Comparison

| Transport | Endpoints | Use Case |
|-----------|-----------|----------|
| stdio | stdin/stdout | Local, CLI |
| SSE | /sse + /messages | Browser, real-time |
| Streamable HTTP | /mcp | Production, scalable |

---

## Next Steps

1. **Build MCP Client** - Connect to servers programmatically
2. **Router Pattern** - Aggregate multiple MCP servers
3. **Authentication** - OAuth for protected resources
4. **Low-level Server** - Full protocol control

---

*Document Version: 1.0*
*Last Updated: December 2025*