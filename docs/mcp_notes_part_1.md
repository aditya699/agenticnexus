# MCP (Model Context Protocol) - Complete Production Guide

**From First Principles to Production Implementation - Enhanced Edition**

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
15. [Authentication](#15-authentication)
16. [Production Configuration](#16-production-configuration)
17. [Writing MCP Clients](#17-writing-mcp-clients)
18. [Advanced Features](#18-advanced-features)
19. [Common Issues and Debugging](#19-common-issues-and-debugging)

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
    instructions="Server description for clients",
    website_url="https://example.com",
    icons=[Icon(src="icon.png", mimeType="image/png", sizes="64x64")]
)
```

---

## 5. Tools

### What are Tools?

Tools are functions that LLMs can invoke. They perform actions and have side effects.

**Control:** Model-controlled (LLM decides when to call)

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

### Tools with Context

```python
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

mcp = FastMCP(name="Progress Example")

@mcp.tool()
async def long_running_task(
    task_name: str, 
    ctx: Context[ServerSession, None], 
    steps: int = 5
) -> str:
    """Execute a task with progress updates."""
    await ctx.info(f"Starting: {task_name}")

    for i in range(steps):
        progress = (i + 1) / steps
        await ctx.report_progress(
            progress=progress,
            total=1.0,
            message=f"Step {i + 1}/{steps}",
        )
        await ctx.debug(f"Completed step {i + 1}")

    return f"Task '{task_name}' completed"
```

### Tool Icons

```python
from mcp.server.fastmcp import FastMCP, Icon

icon = Icon(src="tool-icon.png", mimeType="image/png", sizes="32x32")

@mcp.tool(icons=[icon])
def my_tool() -> str:
    """Tool with an icon for UI display."""
    return "result"
```

---

## 6. Resources

### What are Resources?

Resources expose data to LLMs. Like GET endpoints - read-only, no side effects.

**Control:** Application-controlled (client manages when to load)

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

@mcp.resource("api://data/{category}/{item_id}")
def get_data(category: str, item_id: str) -> str:
    """Get data from API."""
    return fetch_from_api(category, item_id)
```

### Resource Notifications

Notify clients when resources change:

```python
from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP(name="Resource Updates")

@mcp.tool()
async def update_data(resource_uri: str, ctx: Context) -> str:
    """Update data and notify clients."""
    # Perform update
    update_database(resource_uri)
    
    # Notify about specific resource
    await ctx.session.send_resource_updated(AnyUrl(resource_uri))
    
    # Or notify about list changes
    await ctx.session.send_resource_list_changed()
    
    return f"Updated {resource_uri}"
```

### Resource Subscriptions

Resources support subscriptions for real-time updates:

```python
@mcp.resource("logs://realtime")
def get_logs() -> str:
    """Get current logs (clients can subscribe for updates)."""
    return get_latest_logs()
```

---

## 7. Prompts

### What are Prompts?

Reusable templates for LLM interactions. User-controlled.

**Control:** User-controlled (user selects from menu/slash commands)

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

### Prompts with Message Structure

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

mcp = FastMCP(name="Structured Prompts")

@mcp.prompt(title="Debug Assistant")
def debug_error(error: str) -> list[base.Message]:
    """Multi-turn debugging conversation."""
    return [
        base.UserMessage("I'm seeing this error:"),
        base.UserMessage(error),
        base.AssistantMessage("I'll help debug that. What have you tried so far?"),
    ]
```

### Prompt Metadata

```python
@mcp.prompt(
    title="Professional Code Review",
    description="Get detailed code review with best practices"
)
def detailed_review(code: str, language: str) -> str:
    """Comprehensive code review prompt."""
    return f"""Please review this {language} code following these criteria:
    
1. Code quality and style
2. Performance considerations
3. Security issues
4. Best practices
5. Suggested improvements

Code:
```{language}
{code}
```
"""
```

---

## 8. Context Object

### What is Context?

Context is automatically injected into tools and resources. Provides access to MCP capabilities.

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
await ctx.log(level="critical", message="Critical issue", logger_name="my_tool")
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

### FastMCP Properties (via ctx.fastmcp)

```python
@mcp.tool()
def server_info(ctx: Context) -> dict:
    """Get information about the current server."""
    return {
        "name": ctx.fastmcp.name,
        "instructions": ctx.fastmcp.instructions,
        "debug_mode": ctx.fastmcp.settings.debug,
        "log_level": ctx.fastmcp.settings.log_level,
        "host": ctx.fastmcp.settings.host,
        "port": ctx.fastmcp.settings.port,
    }
```

### Session Properties (via ctx.session)

```python
@mcp.tool()
async def notify_changes(ctx: Context) -> str:
    """Access advanced session features."""
    # Get client capabilities
    capabilities = ctx.session.client_params
    
    # Send notifications
    await ctx.session.send_resource_list_changed()
    await ctx.session.send_tool_list_changed()
    await ctx.session.send_prompt_list_changed()
    
    # Request LLM sampling
    result = await ctx.session.create_message(
        messages=[...],
        max_tokens=100
    )
    
    return "Notifications sent"
```

### Request Context Properties (via ctx.request_context)

```python
@mcp.tool()
def use_lifespan_resources(ctx: Context) -> str:
    """Access lifespan-initialized resources."""
    # Access typed lifespan context
    app_ctx = ctx.request_context.lifespan_context
    db = app_ctx.db
    config = app_ctx.config
    
    # Access request metadata
    progress_token = ctx.request_context.meta.get("progressToken")
    
    # Access original request
    original_request = ctx.request_context.request
    
    return f"Using DB: {db}, Config: {config}"
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

### Multiple Resources

```python
@dataclass
class AppContext:
    db: Database
    redis: RedisClient
    http_client: httpx.AsyncClient
    config: AppConfig

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    # Initialize all resources
    db = await Database.connect()
    redis = await RedisClient.connect()
    http_client = httpx.AsyncClient()
    config = load_config()
    
    try:
        yield AppContext(
            db=db,
            redis=redis,
            http_client=http_client,
            config=config
        )
    finally:
        # Clean up in reverse order
        await http_client.aclose()
        await redis.disconnect()
        await db.disconnect()
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

| Type | Structured? | Notes |
|------|-------------|-------|
| `str`, `int`, `float` | No | Wrapped in `{"result": value}` |
| `BaseModel` | Yes | Pydantic models |
| `TypedDict` | Yes | Typed dictionaries |
| `@dataclass` | Yes | Python dataclasses |
| `dict[str, T]` | Yes | Generic dicts |
| Classes with type hints | Yes | Must have annotated attributes |
| Classes without hints | No | Cannot be serialized |

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

### Complex Structured Types

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class User(BaseModel):
    id: int
    name: str
    email: str
    tags: List[str] = Field(default_factory=list)
    metadata: Optional[dict] = None

class SearchResult(BaseModel):
    users: List[User]
    total: int
    page: int

@mcp.tool()
def search_users(query: str, page: int = 1) -> SearchResult:
    """Search users with structured output."""
    users = [
        User(id=1, name="Alice", email="alice@example.com", tags=["admin"]),
        User(id=2, name="Bob", email="bob@example.com", tags=["user"])
    ]
    return SearchResult(users=users, total=2, page=page)
```

### Direct CallToolResult

For full control including `_meta` field:

```python
from mcp.types import CallToolResult, TextContent

@mcp.tool()
def advanced_tool() -> CallToolResult:
    """Return CallToolResult directly for full control."""
    return CallToolResult(
        content=[TextContent(type="text", text="Response visible to model")],
        structuredContent={"status": "success", "data": {"result": 42}},
        _meta={"hidden": "data for client applications only"},
    )
```

### Suppressing Structured Output

```python
@mcp.tool(structured_output=False)
def unstructured_tool() -> dict:
    """Force unstructured output even with type hint."""
    return {"status": "ok"}
```

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

### Throw Error Pattern

For operations that cannot proceed without authorization:

```python
import uuid
from mcp.shared.exceptions import UrlElicitationRequiredError
from mcp.types import ElicitRequestURLParams

@mcp.tool()
async def connect_service(service_name: str, ctx: Context) -> str:
    """Connect to service requiring OAuth."""
    elicitation_id = str(uuid.uuid4())
    
    raise UrlElicitationRequiredError([
        ElicitRequestURLParams(
            mode="url",
            message=f"Authorization required for {service_name}",
            url=f"https://{service_name}.com/oauth?id={elicitation_id}",
            elicitationId=elicitation_id,
        )
    ])
```

### Response Actions

```python
result = await ctx.elicit(...)

result.action  # "accept" | "decline" | "cancel"
result.data    # User's form data (if accepted)
result.validation_error  # Any validation error message
```

### Default Values

Elicitation schemas support default values:

```python
class Preferences(BaseModel):
    theme: str = Field(default="dark", description="UI theme")
    notifications: bool = Field(default=True, description="Enable notifications")
    language: str = Field(default="en", description="Language code")
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

### Basic Completion

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Completion Example")

@mcp.resource("github://{owner}/{repo}")
def get_repo(owner: str, repo: str) -> str:
    """Get GitHub repository content."""
    return fetch_github(owner, repo)

# Clients can request completions for 'owner' and 'repo' parameters
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

### Prompt Argument Completions

```python
@mcp.prompt()
def styled_greeting(name: str, style: str) -> str:
    """Generate styled greeting."""
    return f"{style} greeting for {name}"

# Clients can request completions for 'style' parameter
# Server can provide: ["friendly", "formal", "casual"]
```

---

## 13. Sampling

### What is Sampling?

Tool asks client's LLM to generate text.

### When to Use

Your tool needs text generation but doesn't have LLM access.

```python
from mcp.types import SamplingMessage, TextContent

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

### Multi-Turn Sampling

```python
@mcp.tool()
async def interactive_brainstorm(idea: str, ctx: Context) -> str:
    """Multi-turn brainstorming with LLM."""
    messages = [
        SamplingMessage(
            role="user",
            content=TextContent(type="text", text=f"Let's brainstorm: {idea}")
        )
    ]
    
    # First round
    result1 = await ctx.session.create_message(messages=messages, max_tokens=100)
    messages.append(SamplingMessage(role="assistant", content=result1.content))
    
    # Follow-up
    messages.append(SamplingMessage(
        role="user",
        content=TextContent(type="text", text="Expand on the best idea")
    ))
    
    result2 = await ctx.session.create_message(messages=messages, max_tokens=150)
    
    return result2.content.text
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

@mcp.resource("data://item", icons=[icon])
def my_resource():
    return "content"

@mcp.prompt(icons=[icon])
def my_prompt():
    return "prompt text"
```

### Image Content in Tool Results

```python
from mcp.types import ImageContent
import base64

@mcp.tool()
def generate_chart(data: list[int]) -> ImageContent:
    """Generate chart as image."""
    # Generate chart using matplotlib or similar
    image_bytes = generate_chart_bytes(data)
    
    return ImageContent(
        type="image",
        data=base64.b64encode(image_bytes).decode(),
        mimeType="image/png"
    )
```

---

## 15. Authentication

### OAuth 2.1 Resource Server

MCP servers can act as OAuth Resource Servers (RS):

```python
from pydantic import AnyHttpUrl
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

class MyTokenVerifier(TokenVerifier):
    """Custom token verification."""
    
    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify JWT token and return access token."""
        # Decode JWT
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        
        # Validate scopes
        if "user" not in payload.get("scope", "").split():
            return None
        
        return AccessToken(
            access_token=token,
            token_type="Bearer",
            scope=payload["scope"]
        )

mcp = FastMCP(
    "Protected Service",
    json_response=True,
    token_verifier=MyTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://auth.example.com"),
        resource_server_url=AnyHttpUrl("http://localhost:8000"),
        required_scopes=["user", "admin"],
    ),
)

@mcp.tool()
async def protected_action() -> str:
    """This tool requires authentication."""
    return "Success"
```

### Protected Resource Metadata (RFC 9728)

MCP servers expose metadata at `/.well-known/oauth-protected-resource`:

```json
{
  "resource": "http://localhost:8000",
  "authorization_servers": ["https://auth.example.com"]
}
```

Clients discover the Authorization Server (AS) from this metadata.

### Token Verification Flow

```
1. Client requests protected resource
2. MCP server calls TokenVerifier.verify_token()
3. If valid, request proceeds
4. If invalid, return 401 Unauthorized
```

### Required Scopes

```python
# Require specific scopes
auth=AuthSettings(
    issuer_url=...,
    resource_server_url=...,
    required_scopes=["read", "write", "admin"]
)
```

### Complete Auth Example

See `examples/servers/simple-auth/` for:
- Authorization Server implementation
- Resource Server (MCP) implementation
- Client with OAuth flow

---

## 16. Production Configuration

### Recommended Setup

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="ProductionServer",
    host="0.0.0.0",              # Listen on all interfaces
    port=8000,                    # Port number
    stateless_http=True,          # Better scaling
    json_response=True,           # Simpler responses
    instructions="Server description",
    website_url="https://example.com",
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
    allow_origins=["*"],  # Configure for production
    allow_methods=["GET", "POST", "DELETE"],
    expose_headers=["Mcp-Session-Id"],  # Critical for session management
    allow_headers=["Content-Type", "Authorization"],
)
```

**Why expose Mcp-Session-Id?**
- MCP streamable HTTP uses this header for session management
- Browsers restrict header access unless explicitly exposed
- Without this, browser clients can't read session IDs

### Path Configuration

```python
# Configure during initialization
mcp = FastMCP(
    "Server",
    streamable_http_path="/",  # Mount at root
    sse_path="/events",        # Custom SSE path
)

# Or configure via settings
mcp.settings.streamable_http_path = "/api/mcp"
mcp.settings.mount_path = "/mcp"
```

### Host-Based Routing

```python
from starlette.routing import Host

app = Starlette(
    routes=[
        Host("api.example.com", app=api_mcp.streamable_http_app()),
        Host("mcp.example.com", app=mcp_server.streamable_http_app()),
    ],
    lifespan=lifespan,
)
```

### Environment Configuration

```python
import os

mcp = FastMCP(
    name=os.getenv("MCP_SERVER_NAME", "DefaultServer"),
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    stateless_http=os.getenv("MCP_STATELESS", "true").lower() == "true",
    json_response=os.getenv("MCP_JSON_RESPONSE", "true").lower() == "true",
)
```

### Health Checks

```python
from starlette.responses import JSONResponse
from starlette.routing import Route

async def health_check(request):
    return JSONResponse({"status": "healthy"})

app = Starlette(
    routes=[
        Route("/health", health_check),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ]
)
```

---

## 17. Writing MCP Clients

### Basic stdio Client

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["server.py"],
)

async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print(f"Tools: {[t.name for t in tools.tools]}")
            
            # Call tool
            result = await session.call_tool("add", {"a": 5, "b": 3})
            print(f"Result: {result}")

asyncio.run(run())
```

### Streamable HTTP Client

```python
from mcp.client.streamable_http import streamablehttp_client

async def run():
    async with streamablehttp_client("http://localhost:8000/mcp") as (
        read, write, _
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List resources
            resources = await session.list_resources()
            
            # Read resource
            content = await session.read_resource(resources.resources[0].uri)
```

### SSE Client

```python
from mcp.client.sse import sse_client

async def run():
    async with sse_client("http://localhost:8000/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Use session...
```

### Sampling Callback

```python
from mcp.types import CreateMessageRequestParams, CreateMessageResult

async def handle_sampling(
    context: RequestContext[ClientSession, None],
    params: CreateMessageRequestParams
) -> CreateMessageResult:
    """Handle LLM sampling requests from server."""
    # Call your LLM
    response = await call_llm(params.messages)
    
    return CreateMessageResult(
        role="assistant",
        content=TextContent(type="text", text=response),
        model="gpt-4",
        stopReason="endTurn",
    )

async with ClientSession(read, write, sampling_callback=handle_sampling) as session:
    # Server tools can now request LLM generations
    pass
```

### Display Utilities

```python
from mcp.shared.metadata_utils import get_display_name

async def display_tools(session: ClientSession):
    """Show tools with proper display names."""
    tools_response = await session.list_tools()
    
    for tool in tools_response.tools:
        # Precedence: title > annotations.title > name
        display_name = get_display_name(tool)
        print(f"Tool: {display_name}")
        if tool.description:
            print(f"   {tool.description}")
```

### OAuth Client

```python
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientMetadata

class MyTokenStorage(TokenStorage):
    """Store tokens persistently."""
    async def get_tokens(self) -> OAuthToken | None:
        # Load from file/database
        pass
    
    async def set_tokens(self, tokens: OAuthToken) -> None:
        # Save to file/database
        pass

oauth_auth = OAuthClientProvider(
    server_url="http://localhost:8001",
    client_metadata=OAuthClientMetadata(
        client_name="My Client",
        redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        grant_types=["authorization_code", "refresh_token"],
        scope="user admin",
    ),
    storage=MyTokenStorage(),
)

async with streamablehttp_client(
    "http://localhost:8001/mcp",
    auth=oauth_auth
) as (read, write, _):
    # Client handles OAuth flow automatically
    pass
```

### Parsing Tool Results

```python
from mcp.types import TextContent, ImageContent, EmbeddedResource

result = await session.call_tool("my_tool", {})

# Parse content
for content in result.content:
    if isinstance(content, TextContent):
        print(f"Text: {content.text}")
    elif isinstance(content, ImageContent):
        print(f"Image: {len(content.data)} bytes")
    elif isinstance(content, EmbeddedResource):
        print(f"Resource: {content.resource.uri}")

# Parse structured content
if result.structuredContent:
    data = result.structuredContent
    print(f"Structured: {data}")

# Check for errors
if result.isError:
    print("Tool execution failed!")
```

### Completions in Clients

```python
from mcp.types import ResourceTemplateReference

# Complete resource template argument
result = await session.complete(
    ref=ResourceTemplateReference(
        type="ref/resource",
        uri="github://{owner}/{repo}"
    ),
    argument={"name": "owner", "value": "mod"},
)

completions = result.completion.values
# ["modelcontextprotocol", "modular", ...]
```

### Pagination in Clients

```python
from mcp.types import PaginatedRequestParams

all_resources = []
cursor = None

while True:
    result = await session.list_resources(
        params=PaginatedRequestParams(cursor=cursor)
    )
    
    all_resources.extend(result.resources)
    
    if result.nextCursor:
        cursor = result.nextCursor
    else:
        break

print(f"Total resources: {len(all_resources)}")
```

---

## 18. Advanced Features

### Low-Level Server

For full protocol control:

```python
import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions

server = Server("low-level-server")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="my_tool",
            description="A tool",
            inputSchema={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "my_tool":
        return [types.TextContent(type="text", text=f"Result: {arguments['x']}")]
    raise ValueError(f"Unknown tool: {name}")

async def run():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read, write,
            InitializationOptions(
                server_name="low-level",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
```

### Pagination (Server-Side)

```python
@server.list_resources()
async def list_resources_paginated(
    request: types.ListResourcesRequest
) -> types.ListResourcesResult:
    """List resources with pagination."""
    page_size = 10
    
    # Parse cursor
    cursor = request.params.cursor if request.params else None
    start = 0 if cursor is None else int(cursor)
    end = start + page_size
    
    # Get page
    page_items = [
        types.Resource(
            uri=AnyUrl(f"resource://items/{item}"),
            name=item
        )
        for item in ALL_ITEMS[start:end]
    ]
    
    # Next cursor
    next_cursor = str(end) if end < len(ALL_ITEMS) else None
    
    return types.ListResourcesResult(
        resources=page_items,
        nextCursor=next_cursor
    )
```

### Structured Output (Low-Level)

```python
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_data",
            description="Get data",
            inputSchema={...},
            outputSchema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "count": {"type": "integer"}
                },
                "required": ["result", "count"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> dict:
    """Return structured data - validated against outputSchema."""
    return {"result": "success", "count": 42}
```

### Direct CallToolResult (Low-Level)

```python
@server.call_tool()
async def handle_tool(name: str, arguments: dict) -> types.CallToolResult:
    """Full control over response."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text="Response")],
        structuredContent={"data": "structured"},
        _meta={"internal": "metadata"}
    )
```

### Event Stores for Resumability

Stateless servers with event stores:

```python
# Server maintains event log
# Clients can reconnect and replay from last position

mcp = FastMCP(
    "Resumable Server",
    stateless_http=True,
    json_response=True,
    # Event store configuration...
)
```

### Custom Transports

Implement custom transport layer:

```python
from mcp.shared.session import BaseSession

class CustomTransport:
    async def connect(self) -> tuple[ReadStream, WriteStream]:
        # Implement custom connection logic
        pass

# Use with client or server
```

---

## 19. Common Issues and Debugging

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
2. Or add CORS middleware:
```python
from starlette.middleware.cors import CORSMiddleware

app = CORSMiddleware(
    app,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```
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

### Issue: Session ID Not Accessible

**Symptom:** Browser client can't read Mcp-Session-Id header

**Cause:** CORS not exposing the header

**Fix:**
```python
app = CORSMiddleware(
    app,
    expose_headers=["Mcp-Session-Id"],  # Critical!
)
```

### Issue: Tool Not Found

**Symptom:**
```json
{"error": {"code": -32601, "message": "Method not found"}}
```

**Cause:** Tool not registered or name mismatch

**Debug:**
```python
# List all registered tools
tools = await session.list_tools()
print([t.name for t in tools.tools])

# Check server logs
mcp.settings.debug = True
mcp.settings.log_level = "DEBUG"
```

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

| Mode | Path | Works? | Use When |
|------|------|--------|----------|
| Direct | Browser → Server | May fail (CORS) | Local development |
| Via Proxy | Browser → Inspector → Server | ✓ Works | Production testing |

### Debugging Lifespan Issues

```python
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    print("STARTUP: Initializing resources")
    db = await Database.connect()
    print(f"STARTUP: DB connected: {db}")
    
    try:
        yield AppContext(db=db)
    finally:
        print("SHUTDOWN: Cleaning up")
        await db.disconnect()
        print("SHUTDOWN: Complete")
```

### Debugging Structured Output

```python
# Check if tool returns structured output
@mcp.tool()
def test_structured() -> dict[str, str]:
    return {"status": "ok"}

# Call and inspect
result = await session.call_tool("test_structured", {})
print(f"Structured: {result.structuredContent}")
print(f"Unstructured: {result.content}")
```

### Common Type Errors

**Problem:** Class without type hints won't work for structured output

```python
# ❌ Won't work
class Config:
    def __init__(self, x, y):
        self.x = x
        self.y = y

# ✓ Works
class Config:
    x: str
    y: int
    
    def __init__(self, x: str, y: int):
        self.x = x
        self.y = y
```

### Debug Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or configure FastMCP
mcp = FastMCP("Server", debug=True, log_level="DEBUG")
```

---

## Quick Reference

### Message Types

| Type | Has ID? | Expects Response? | Used For |
|------|---------|-------------------|----------|
| Request | Yes | Yes | Tool calls, resource reads |
| Response | Yes (matches request) | No | Answers to requests |
| Notification | No | No | Progress, logs, updates |

### Three Primitives

| Primitive | Control | Purpose | Example |
|-----------|---------|---------|---------|
| Tools | Model-controlled (LLM) | Actions with side effects | API calls, database updates |
| Resources | App-controlled | Read-only data | File contents, configuration |
| Prompts | User-controlled | Reusable templates | Slash commands, menu items |

### Context Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `ctx.debug/info/warning/error()` | Logging | None |
| `ctx.report_progress()` | Progress updates | None |
| `ctx.read_resource()` | Read other resources | Resource content |
| `ctx.elicit()` | Ask user for input | ElicitationResult |
| `ctx.session.create_message()` | Request LLM sampling | CreateMessageResult |
| `ctx.fastmcp.name` | Server name | str |
| `ctx.request_context.lifespan_context` | Lifespan resources | Your context type |

### Transport Comparison

| Transport | Endpoints | Complexity | Scaling | Use Case |
|-----------|-----------|------------|---------|----------|
| stdio | stdin/stdout | Low | Single process | Local, CLI |
| SSE | /sse + /messages | Medium | Limited | Browser, real-time |
| Streamable HTTP | /mcp | Low | ✓ Excellent | Production, scalable |

### Server Capabilities

| Capability | Feature | Purpose |
|-----------|---------|---------|
| tools | listChanged | Tool management, execution |
| resources | subscribe, listChanged | Resource exposure, updates |
| prompts | listChanged | Prompt templates |
| logging | - | Server logging |
| completions | - | Argument suggestions |
| sampling | - | LLM text generation |

### Structured Output Types

| Type | Structured? | Validation | Example |
|------|-------------|------------|---------|
| Pydantic BaseModel | ✓ Yes | Full | `class Data(BaseModel): x: int` |
| TypedDict | ✓ Yes | Full | `class Data(TypedDict): x: int` |
| Dataclass | ✓ Yes | Full | `@dataclass\nclass Data: x: int` |
| dict[str, T] | ✓ Yes | Basic | `dict[str, int]` |
| Primitives | No | None | `str`, `int`, `float` |
| Generic types | No | None | `list`, `tuple`, `Optional` |

### Authentication Components

| Component | Role | Responsibility |
|-----------|------|----------------|
| Authorization Server (AS) | Token issuer | User authentication, token generation |
| Resource Server (RS) | MCP Server | Token validation, resource protection |
| Client | Application | Token acquisition, API calls |

---

## Installation Guide

### Using uv (Recommended)

```bash
# Create new project
uv init mcp-server
cd mcp-server

# Add MCP
uv add "mcp[cli]"

# Run MCP commands
uv run mcp dev server.py
uv run mcp install server.py
```

### Using pip

```bash
pip install "mcp[cli]"
```

### Claude Desktop Integration

```bash
# Install server in Claude Desktop
uv run mcp install server.py --name "My Server"

# With environment variables
uv run mcp install server.py -v API_KEY=xxx -v DB_URL=yyy

# From .env file
uv run mcp install server.py -f .env

# Add to Claude Code
claude mcp add --transport http my-server http://localhost:8000/mcp
```

### Development Tools

```bash
# MCP Inspector (browser-based testing)
npx @modelcontextprotocol/inspector

# Connect to server
# Direct: http://localhost:8000/mcp
# Via Proxy: (use inspector's proxy)

# Development mode with auto-reload
uv run mcp dev server.py
```

---

## Server Capabilities Matrix

| Feature | FastMCP | Low-Level | Notes |
|---------|---------|-----------|-------|
| Tools | ✓ | ✓ | Function decorators vs manual handlers |
| Resources | ✓ | ✓ | URI templates supported |
| Prompts | ✓ | ✓ | Template generation |
| Structured Output | ✓ Auto | Manual | FastMCP auto-generates schemas |
| Context Injection | ✓ | ✗ | FastMCP provides ctx parameter |
| Lifespan | ✓ | ✓ | Resource initialization |
| Progress | ✓ | ✓ | Real-time updates |
| Elicitation | ✓ | ✓ | User input requests |
| Sampling | ✓ | ✓ | LLM text generation |
| Authentication | ✓ | ✓ | OAuth 2.1 support |
| Type Safety | ✓ High | Medium | FastMCP uses Pydantic |

---

## MCP Protocol Versions

### Current Version: 2024-11-05

**Major Features:**
- Structured output support
- OAuth 2.1 authentication
- Streamable HTTP transport
- Elicitation (user input)
- Resource subscriptions

### Spec Revision: 2025-06-18

**Additions:**
- Structured output in tool responses
- `outputSchema` field for tools
- Backward compatibility with content-only responses

---

## Best Practices

### Server Design

1. **Use Streamable HTTP for production**
   ```python
   mcp = FastMCP("Server", stateless_http=True, json_response=True)
   mcp.run(transport="streamable-http")
   ```

2. **Implement proper error handling**
   ```python
   @mcp.tool()
   async def safe_tool(x: str, ctx: Context) -> str:
       try:
           result = await risky_operation(x)
           await ctx.info("Success")
           return result
       except Exception as e:
           await ctx.error(f"Failed: {e}")
           raise
   ```

3. **Use lifespan for shared resources**
   ```python
   @asynccontextmanager
   async def app_lifespan(server: FastMCP):
       db = await Database.connect()
       try:
           yield AppContext(db=db)
       finally:
           await db.disconnect()
   ```

4. **Provide detailed descriptions**
   ```python
   @mcp.tool()
   def search(query: str, limit: int = 10) -> list[Result]:
       """Search with pagination.
       
       Args:
           query: Search query string (supports wildcards)
           limit: Maximum results (1-100, default 10)
           
       Returns:
           List of search results with title, url, snippet
       """
   ```

### Client Development

1. **Handle all content types**
   ```python
   for content in result.content:
       if isinstance(content, TextContent):
           handle_text(content.text)
       elif isinstance(content, ImageContent):
           handle_image(content.data)
   ```

2. **Use display utilities**
   ```python
   from mcp.shared.metadata_utils import get_display_name
   
   display_name = get_display_name(tool)  # title > name
   ```

3. **Implement token storage for OAuth**
   ```python
   class PersistentTokenStorage(TokenStorage):
       async def get_tokens(self) -> OAuthToken | None:
           # Load from secure storage
           pass
   ```

### Security

1. **Validate all inputs**
   ```python
   @mcp.tool()
   def process_data(data: str, ctx: Context) -> str:
       if len(data) > 1000000:
           raise ValueError("Data too large")
       return process(data)
   ```

2. **Use environment variables for secrets**
   ```python
   import os
   
   API_KEY = os.getenv("API_KEY")
   if not API_KEY:
       raise ValueError("API_KEY not set")
   ```

3. **Implement rate limiting**
   ```python
   from datetime import datetime, timedelta
   
   rate_limits = {}
   
   @mcp.tool()
   async def rate_limited_tool(ctx: Context) -> str:
       client_id = ctx.client_id
       now = datetime.now()
       
       if client_id in rate_limits:
           if now - rate_limits[client_id] < timedelta(seconds=1):
               raise Exception("Rate limit exceeded")
       
       rate_limits[client_id] = now
       return "Success"
   ```

---

## Troubleshooting Guide

### Server Won't Start

**Check 1: Port availability**
```bash
lsof -i :8000  # Check if port is in use
```

**Check 2: Import errors**
```python
# Verify MCP installation
python -c "import mcp; print(mcp.__version__)"
```

**Check 3: Configuration**
```python
# Enable debug mode
mcp = FastMCP("Server", debug=True, log_level="DEBUG")
```

### Client Can't Connect

**Check 1: Network connectivity**
```bash
curl http://localhost:8000/mcp
```

**Check 2: CORS headers**
```python
# Inspect response headers
curl -I http://localhost:8000/mcp
```

**Check 3: Transport mismatch**
```python
# Client and server must use same transport
# Server: mcp.run(transport="streamable-http")
# Client: streamablehttp_client("http://...")
```

### Tools Not Working

**Check 1: Registration**
```python
# List all tools
tools = await session.list_tools()
print([t.name for t in tools.tools])
```

**Check 2: Arguments**
```python
# Inspect tool schema
tool = tools.tools[0]
print(tool.inputSchema)
```

**Check 3: Execution errors**
```python
# Check server logs
# Look for exceptions in tool execution
```

---

## Performance Optimization

### Server-Side

1. **Use async operations**
   ```python
   @mcp.tool()
   async def fast_tool() -> str:
       results = await asyncio.gather(
           fetch_data_1(),
           fetch_data_2(),
           fetch_data_3()
       )
       return combine(results)
   ```

2. **Implement caching**
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=100)
   def expensive_computation(x: str) -> str:
       # Cached results
       return compute(x)
   ```

3. **Use stateless mode for scaling**
   ```python
   mcp = FastMCP("Server", stateless_http=True, json_response=True)
   ```

### Client-Side

1. **Connection pooling**
   ```python
   # Reuse client sessions
   async with streamablehttp_client(url) as (read, write, _):
       async with ClientSession(read, write) as session:
           # Multiple operations on same session
           pass
   ```

2. **Batch requests where possible**
   ```python
   # Better: Single request returning multiple items
   results = await session.call_tool("batch_process", {"items": [...]})
   
   # Avoid: Multiple sequential requests
   for item in items:
       result = await session.call_tool("process", {"item": item})
   ```

---

## Resources

### Official Documentation
- [MCP Protocol Specification](https://modelcontextprotocol.io/specification)
- [Python SDK Documentation](https://modelcontextprotocol.github.io/python-sdk/)
- [GitHub Repository](https://github.com/modelcontextprotocol/python-sdk)

### Examples
- [Official Servers](https://github.com/modelcontextprotocol/servers)
- [FastMCP Examples](https://github.com/modelcontextprotocol/python-sdk/tree/main/examples)
- [Authentication Example](https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth)

### Community
- [GitHub Discussions](https://github.com/modelcontextprotocol/python-sdk/discussions)
- [Issue Tracker](https://github.com/modelcontextprotocol/python-sdk/issues)
- [Contributing Guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/CONTRIBUTING.md)

---

## Glossary

**Application-Controlled**: Client application decides when to invoke (Resources)

**Authorization Server (AS)**: OAuth server that issues tokens

**CallToolResult**: Response object from tool execution

**Completions**: Autocomplete suggestions for arguments

**Context**: Injected object providing MCP capabilities to tools

**Elicitation**: Requesting user input mid-execution

**FastMCP**: High-level MCP server implementation

**JSON-RPC**: Protocol for remote procedure calls using JSON

**Lifespan**: Server lifecycle management for resource initialization

**Model-Controlled**: LLM decides when to invoke (Tools)

**MCP**: Model Context Protocol

**Notification**: One-way message without response

**OAuth 2.1**: Authentication and authorization protocol

**Prompt**: Reusable template for LLM interactions

**Resource**: Read-only data exposed to LLMs

**Resource Server (RS)**: Server that validates tokens and serves resources

**RPC**: Remote Procedure Call

**Sampling**: Requesting LLM to generate text

**Session**: Communication session between client and server

**SSE**: Server-Sent Events (HTTP streaming)

**Stateless**: Server doesn't maintain session state between requests

**stdio**: Standard input/output streams

**Streamable HTTP**: MCP transport using single HTTP endpoint

**Structured Output**: Type-safe, validated tool responses

**Tool**: Function that LLMs can invoke to take actions

**Transport**: Communication layer (stdio, SSE, HTTP)

**URI Template**: Resource identifier with parameters (e.g., `file://{path}`)

**User-Controlled**: User selects from menu/UI (Prompts)

---

*Document Version: 2.0 Enhanced*
*Last Updated: December 2025*
*Based on MCP Python SDK v1.23.3*