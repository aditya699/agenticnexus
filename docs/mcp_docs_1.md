# AgenticNexus MCP Router: A Deep Dive from First Principles

**Author:** Claude (Anthropic) for Aditya Bhatt  
**Version:** 1.0  
**Date:** December 2025  
**Purpose:** Production-grade reference for implementing an MCP Router in enterprise environments

---

## Table of Contents

1. [Introduction: Why This Document Exists](#1-introduction-why-this-document-exists)
2. [Foundation: Understanding the Networking Stack](#2-foundation-understanding-the-networking-stack)
3. [What is MCP? First Principles](#3-what-is-mcp-first-principles)
4. [Transport Layer Deep Dive](#4-transport-layer-deep-dive)
5. [The MCP Protocol Layer](#5-the-mcp-protocol-layer)
6. [Server Architecture](#6-server-architecture)
7. [Client Architecture](#7-client-architecture)
8. [The Router: Dual-Identity Pattern](#8-the-router-dual-identity-pattern)
9. [Connection Lifecycle Management](#9-connection-lifecycle-management)
10. [Streaming and Progress: Bidirectional Flow](#10-streaming-and-progress-bidirectional-flow)
11. [The LLM Brain: Planning and Synthesis](#11-the-llm-brain-planning-and-synthesis)
12. [Complete Request Flow: Step by Step](#12-complete-request-flow-step-by-step)
13. [Error Handling and Edge Cases](#13-error-handling-and-edge-cases)
14. [Production Considerations](#14-production-considerations)
15. [Implementation Checklist](#15-implementation-checklist)

---

## 1. Introduction: Why This Document Exists

### The Problem We're Solving

In enterprise environments, you have multiple internal systems that could benefit from AI integration:
- HR systems with employee data
- Finance systems with budget information
- SharePoint with documents
- Custom internal APIs

The challenge: How do you expose all these to an AI client in a **unified, intelligent way**?

### What a Router Does

```
                                    ┌─────────────────┐
                                    │  HR MCP Server  │
                                    │   (Port 8000)   │
                                    └────────▲────────┘
                                             │
┌──────────────┐     ┌──────────────────┐    │
│  AI Client   │────▶│  AgenticNexus    │────┤
│  (Claude,    │     │  Router (8002)   │    │
│   GPT, etc)  │◀────│                  │────┤
└──────────────┘     │  + LLM Brain     │    │
                     └──────────────────┘    │
                                             │
                                    ┌────────▼────────┐
                                    │ Finance Server  │
                                    │   (Port 8001)   │
                                    └─────────────────┘
```

The router:
1. **Aggregates** multiple downstream servers into one interface
2. **Plans** which tools to use (via internal LLM)
3. **Orchestrates** execution across servers
4. **Synthesizes** results into coherent responses

### Why Understanding the Internals Matters

When you use a library like `mcp` or `FastMCP`, you're working with abstractions. These abstractions hide complexity, which is great for productivity but terrible for:
- Debugging production issues
- Understanding why streaming breaks
- Implementing custom behaviors
- Building something like a router

This document peels back those abstractions layer by layer.

---

## 2. Foundation: Understanding the Networking Stack

Before we understand MCP, we need to understand the networking stack it's built on.

### 2.1 The OSI Model (Simplified for Our Purposes)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 7: Application    │  MCP Protocol (JSON-RPC)        │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Presentation   │  JSON Encoding                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Session        │  SSE / Streamable HTTP          │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Transport      │  HTTP/1.1 or HTTP/2             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Network        │  TCP/IP                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 1-2: Physical     │  Ethernet / WiFi                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 HTTP: The Foundation

HTTP is a **request-response protocol**. Client sends a request, server sends a response, connection typically closes.

```
Client                          Server
  │                               │
  │─────── GET /data ────────────▶│
  │                               │
  │◀────── 200 OK + Data ─────────│
  │                               │
```

**Problem:** HTTP is inherently one-way. The server can't push data to the client without the client asking first.

### 2.3 How Do We Get Server-to-Client Communication?

Three main approaches:

**1. Polling (Bad)**
```
Client                          Server
  │                               │
  │─── GET /updates ────────────▶│
  │◀── "nothing new" ────────────│
  │                               │
  │─── GET /updates ────────────▶│  (1 second later)
  │◀── "nothing new" ────────────│
  │                               │
  │─── GET /updates ────────────▶│  (1 second later)
  │◀── "here's an update!" ──────│
```

Problems: Wastes bandwidth, high latency, hammers the server.

**2. Long Polling (Better)**
```
Client                          Server
  │                               │
  │─── GET /updates ────────────▶│
  │         (server holds connection open)
  │         (waiting for data...)
  │         (30 seconds pass...)
  │◀── "here's an update!" ──────│
  │                               │
  │─── GET /updates ────────────▶│  (immediately reconnect)
```

Problems: Still has connection overhead, timeouts are tricky.

**3. Server-Sent Events / SSE (What MCP Uses)**
```
Client                          Server
  │                               │
  │─── GET /sse ─────────────────▶│
  │◀── HTTP 200 + Keep-Alive ────│
  │                               │
  │◀── event: message            │  (server pushes whenever it wants)
  │    data: {"type": "progress"}│
  │                               │
  │◀── event: message            │  (more data)
  │    data: {"type": "result"}  │
  │                               │
```

**SSE is a single HTTP connection that stays open**, allowing the server to push data whenever it wants.

### 2.4 SSE Deep Dive

**The SSE Format:**

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: message
data: {"jsonrpc": "2.0", "method": "notifications/progress"}

event: message
data: {"jsonrpc": "2.0", "result": {"content": [...]}}

```

Key points:
- `Content-Type: text/event-stream` tells the client "this is SSE"
- Each message is `event: <type>\ndata: <payload>\n\n`
- The double newline (`\n\n`) marks the end of a message
- The connection stays open indefinitely (or until closed)

**Why SSE for MCP?**
- Server can push progress updates without client asking
- Server can push notifications (tool list changed, etc.)
- Works over standard HTTP (no WebSocket upgrade needed)
- Simpler than WebSockets for one-way server→client streaming

### 2.5 The Problem: SSE is One-Way

SSE only allows server→client communication. But MCP needs **bidirectional** communication:
- Client → Server: "Call this tool"
- Server → Client: "Here's progress at 30%"
- Server → Client: "Here's progress at 70%"
- Server → Client: "Here's the result"

**Solution: SSE + POST**

```
┌──────────────────────────────────────────────────────────────┐
│                     MCP over SSE Transport                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   CLIENT                              SERVER                 │
│      │                                   │                   │
│      │──── GET /sse ────────────────────▶│  (establish SSE) │
│      │◀─── 200 OK + session_id ──────────│                   │
│      │                                   │                   │
│      │     (SSE connection stays open)   │                   │
│      │                                   │                   │
│      │──── POST /messages?session_id ───▶│  (send request)  │
│      │◀─── 202 Accepted ─────────────────│                   │
│      │                                   │                   │
│      │◀─── [via SSE] progress ───────────│  (receive via SSE)│
│      │◀─── [via SSE] result ─────────────│                   │
│      │                                   │                   │
└──────────────────────────────────────────────────────────────┘
```

This is the "split channel" model:
- **GET /sse**: Opens a persistent connection for receiving
- **POST /messages**: Sends requests to the server
- The server matches POST requests to SSE connections via `session_id`

---

## 3. What is MCP? First Principles

### 3.1 The Core Idea

MCP (Model Context Protocol) is a **standardized way for AI applications to interact with external tools and data sources**.

Think of it like USB for AI:
- Before USB: Every device had its own cable and protocol
- After USB: One standard, everything works together

Before MCP: Every AI tool integration was custom
After MCP: One standard protocol, tools work with any AI

### 3.2 The Three Primitives

MCP defines three core primitives:

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Primitives                           │
├──────────────┬──────────────────┬───────────────────────────┤
│  TOOLS       │  RESOURCES       │  PROMPTS                  │
├──────────────┼──────────────────┼───────────────────────────┤
│  Actions     │  Data            │  Templates                │
│  Side effects│  Read-only       │  Reusable patterns        │
│  LLM invokes │  App loads       │  User selects             │
├──────────────┼──────────────────┼───────────────────────────┤
│  Example:    │  Example:        │  Example:                 │
│  web_search  │  file://doc.txt  │  "Summarize as bullets"   │
│  send_email  │  db://users/123  │  "Translate to Spanish"   │
│  calculate   │  api://weather   │  "Write formal email"     │
└──────────────┴──────────────────┴───────────────────────────┘
```

For the router, we primarily care about **Tools** - the actions that LLMs can invoke.

### 3.3 The MCP Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌─────────────┐         ┌─────────────┐                   │
│  │  MCP HOST   │         │  MCP SERVER │                   │
│  │  (Client)   │◀───────▶│             │                   │
│  │             │   MCP   │             │                   │
│  │  Claude.ai  │ Protocol│  Your Tool  │                   │
│  │  VSCode     │         │  Service    │                   │
│  │  Custom App │         │             │                   │
│  └─────────────┘         └─────────────┘                   │
│                                                             │
│  The Host:                The Server:                       │
│  - Connects to servers    - Exposes tools/resources         │
│  - Maintains sessions     - Handles requests                │
│  - Routes LLM requests    - Returns results                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Key insight: **The router is BOTH a server (to clients) AND a client (to downstream servers).**

### 3.4 JSON-RPC: The Wire Protocol

MCP uses JSON-RPC 2.0 for message encoding. Every message is one of:

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "web_search",
    "arguments": {"query": "latest news"}
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "Here are the results..."}]
  }
}
```

**Notification (no response expected):**
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/progress",
  "params": {
    "progressToken": "abc123",
    "progress": 0.5,
    "total": 1.0
  }
}
```

The `id` field links requests to responses. Notifications have no `id`.

---

## 4. Transport Layer Deep Dive

### 4.1 Available Transports in MCP

MCP supports multiple transports:

| Transport | Use Case | Characteristics |
|-----------|----------|-----------------|
| **stdio** | Local processes | Pipes, same machine only |
| **SSE** | HTTP-based | Split channel, good for browsers |
| **Streamable HTTP** | Newer HTTP | Single endpoint, bidirectional |

For enterprise web applications, **SSE** is the most common choice.

### 4.2 SSE Transport Internals

When you call `sse_client(url)`, here's what happens:

```python
# Simplified version of what the MCP SDK does

async def sse_client(url: str):
    """
    Creates bidirectional streams over SSE.
    
    Returns:
        read_stream: MemoryObjectReceiveStream - receive from server
        write_stream: MemoryObjectSendStream - send to server
    """
    
    # Step 1: Open SSE connection
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", f"{url}/sse") as response:
            # Server sends us a session_id in the first message
            session_id = await get_session_id(response)
            
            # Step 2: Create memory streams for internal communication
            # These are like in-memory pipes
            read_send, read_receive = create_memory_object_stream()
            write_send, write_receive = create_memory_object_stream()
            
            # Step 3: Start background tasks
            
            # Task 1: Read from SSE, put into read stream
            async def sse_reader():
                async for event in response.aiter_sse():
                    message = json.loads(event.data)
                    await read_send.send(message)
            
            # Task 2: Read from write stream, POST to server
            async def message_sender():
                async for message in write_receive:
                    await client.post(
                        f"{url}/messages/?session_id={session_id}",
                        json=message
                    )
            
            # Run both tasks concurrently
            async with create_task_group() as tg:
                tg.start_soon(sse_reader)
                tg.start_soon(message_sender)
                
                yield read_receive, write_send
```

**The key insight:** The SSE client creates two logical streams from one SSE connection + HTTP POSTs:
- `read_stream`: Messages from server (via SSE)
- `write_stream`: Messages to server (via POST)

### 4.3 The Session Binding Problem

When you POST a message, how does the server know which SSE connection to respond on?

**Answer: Session ID**

```
Step 1: Client opens SSE connection
        GET /sse
        
Step 2: Server generates session ID, sends it via SSE
        event: endpoint
        data: /messages/?session_id=abc123
        
Step 3: Client POSTs to that endpoint
        POST /messages/?session_id=abc123
        
Step 4: Server routes response to correct SSE connection
        (internally maps session_id → SSE stream)
```

This is critical for the router because:
- Multiple clients can connect simultaneously
- Each has its own session
- Server must route responses to correct client

### 4.4 The anyio TaskGroup Problem

This is where many people get confused, and it caused bugs in our router.

**anyio** (used by MCP SDK) uses "task groups" for concurrent operations:

```python
async with anyio.create_task_group() as tg:
    tg.start_soon(task_1)
    tg.start_soon(task_2)
    # Both tasks run concurrently
    # Block exits when all tasks complete OR any task fails
```

**The Rule:** A task group must exit in the same async context it was created in.

**The Problem:**
```python
async def bad_example():
    async with sse_client(url) as streams:
        read, write = streams
        # The SSE connection is alive here
    # Connection is DEAD here - context manager exited!
    
    # This will fail:
    await read.receive()  # RuntimeError!
```

**Why?** The `sse_client` context manager creates task groups internally. When you exit the `async with` block, those task groups try to clean up. If you're in a different async context (like a different function), you get:

```
RuntimeError: Attempted to exit cancel scope in a different task
```

This is why we need `AsyncExitStack` (covered in Section 9).

---

## 5. The MCP Protocol Layer

### 5.1 Message Types

MCP defines these message types:

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Message Types                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  INITIALIZATION                                             │
│  ├── initialize (request)                                   │
│  └── initialized (notification)                             │
│                                                             │
│  TOOL OPERATIONS                                            │
│  ├── tools/list (request)                                   │
│  └── tools/call (request)                                   │
│                                                             │
│  RESOURCE OPERATIONS                                        │
│  ├── resources/list (request)                               │
│  ├── resources/read (request)                               │
│  └── resources/subscribe (request)                          │
│                                                             │
│  NOTIFICATIONS                                              │
│  ├── notifications/progress                                 │
│  ├── notifications/tools/list_changed                       │
│  └── notifications/resources/list_changed                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 The Initialization Handshake

Before any operations, client and server must initialize:

```
Client                              Server
  │                                   │
  │─── initialize ───────────────────▶│
  │    {                              │
  │      protocolVersion: "2024-11",  │
  │      capabilities: {...},         │
  │      clientInfo: {...}            │
  │    }                              │
  │                                   │
  │◀─── initialize response ──────────│
  │    {                              │
  │      protocolVersion: "2024-11",  │
  │      capabilities: {...},         │
  │      serverInfo: {...}            │
  │    }                              │
  │                                   │
  │─── initialized ──────────────────▶│
  │    (notification, no response)    │
  │                                   │
```

**Capabilities** tell each side what features are supported:
- `tools`: Server can expose tools
- `resources`: Server can expose resources
- `prompts`: Server can expose prompts
- `logging`: Server supports logging
- `progress`: Server can report progress

### 5.3 Tool Discovery

```
Client                              Server
  │                                   │
  │─── tools/list ───────────────────▶│
  │                                   │
  │◀─── tools/list response ──────────│
  │    {                              │
  │      tools: [                     │
  │        {                          │
  │          name: "web_search",      │
  │          description: "...",      │
  │          inputSchema: {...}       │
  │        },                         │
  │        ...                        │
  │      ]                            │
  │    }                              │
  │                                   │
```

The `inputSchema` is a JSON Schema describing the tool's parameters:

```json
{
  "name": "web_search",
  "description": "Search the web for information",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query"
      },
      "max_results": {
        "type": "integer",
        "default": 10
      }
    },
    "required": ["query"]
  }
}
```

### 5.4 Tool Execution

```
Client                              Server
  │                                   │
  │─── tools/call ───────────────────▶│
  │    {                              │
  │      name: "web_search",          │
  │      arguments: {query: "AI news"}│
  │      _meta: {progressToken: "t1"} │
  │    }                              │
  │                                   │
  │◀─── notifications/progress ───────│  (optional)
  │    {progress: 0.3, total: 1.0}    │
  │                                   │
  │◀─── notifications/progress ───────│  (optional)
  │    {progress: 0.7, total: 1.0}    │
  │                                   │
  │◀─── tools/call response ──────────│
  │    {                              │
  │      content: [                   │
  │        {type: "text", text: "..."}│
  │      ]                            │
  │    }                              │
  │                                   │
```

**Progress Token:** The `_meta.progressToken` tells the server "send progress updates with this token so I can match them to this request."

### 5.5 Content Types

Tool results can contain various content types:

```python
# Text content (most common)
{
    "type": "text",
    "text": "Here are the search results..."
}

# Image content
{
    "type": "image",
    "data": "base64-encoded-image-data",
    "mimeType": "image/png"
}

# Embedded resource
{
    "type": "resource",
    "resource": {
        "uri": "file://path/to/file",
        "text": "file contents..."
    }
}
```

---

## 6. Server Architecture

### 6.1 FastMCP: The High-Level Abstraction

FastMCP is a decorator-based framework that hides the complexity:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
async def web_search(query: str) -> str:
    """Search the web."""
    results = await do_search(query)
    return results
```

**What FastMCP does under the hood:**

1. **Tool Registration:**
   - Parses function signature
   - Extracts type hints
   - Generates JSON Schema for `inputSchema`
   - Stores in internal registry

2. **Request Handling:**
   - Receives `tools/list` → Returns registered tools
   - Receives `tools/call` → Finds function, validates args, executes

3. **Transport Setup:**
   - Creates SSE endpoints (`/sse`, `/messages`)
   - Manages session→stream mapping

### 6.2 The Low-Level Server

Underneath FastMCP is the low-level `Server` class:

```python
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions

server = Server("my-server")

@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="web_search",
            description="Search the web",
            inputSchema={...}
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "web_search":
        return do_search(arguments["query"])
    raise ValueError(f"Unknown tool: {name}")
```

### 6.3 The SSE App

FastMCP exposes an `sse_app()` method that returns a Starlette/ASGI application:

```python
mcp = FastMCP("my-server")
sse_app = mcp.sse_app()

# This app handles:
# GET /sse - SSE connection endpoint
# POST /messages - Message posting endpoint

# Run with uvicorn:
uvicorn.run(sse_app, host="0.0.0.0", port=8000)
```

### 6.4 The Context Object

When a tool is called, it can receive a `Context` object:

```python
from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
async def long_task(query: str, ctx: Context) -> str:
    """A task that reports progress."""
    
    await ctx.info("Starting task...")
    
    for i in range(10):
        await ctx.report_progress(
            progress=i / 10,
            total=1.0,
            message=f"Step {i+1}/10"
        )
        await do_step(i)
    
    await ctx.info("Task complete!")
    return "Done"
```

**Context provides:**
- `ctx.report_progress(progress, total, message)` - Send progress
- `ctx.info(msg)`, `ctx.debug(msg)`, etc. - Logging
- `ctx.request_id` - Unique request identifier
- `ctx.session` - Access to underlying session

**Critically:** Progress reported via `ctx.report_progress()` is sent via SSE to the client as a `notifications/progress` message.

---

## 7. Client Architecture

### 7.1 ClientSession: The Core

The `ClientSession` class handles communication with an MCP server:

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async with sse_client("http://localhost:8000/sse") as (read, write):
    async with ClientSession(read, write) as session:
        # Initialize the connection
        await session.initialize()
        
        # List available tools
        tools = await session.list_tools()
        
        # Call a tool
        result = await session.call_tool(
            "web_search",
            {"query": "AI news"}
        )
```

### 7.2 What ClientSession Does

1. **Initialization:**
   - Sends `initialize` request
   - Waits for response
   - Sends `initialized` notification

2. **Request/Response Matching:**
   - Each request gets a unique `id`
   - Session tracks pending requests
   - When response arrives, matches by `id`

3. **Progress Handling:**
   - Can register a `progress_callback`
   - When `notifications/progress` arrives, calls the callback

```python
async def handle_progress(progress, total, message):
    print(f"Progress: {progress}/{total} - {message}")

result = await session.call_tool(
    "web_search",
    {"query": "AI news"},
    progress_callback=handle_progress
)
```

### 7.3 The Stream Abstraction

ClientSession works with two streams:
- `read_stream`: Receives messages from server
- `write_stream`: Sends messages to server

These are **abstract** - they could be:
- SSE streams (sse_client)
- Stdio streams (stdio_client)
- Streamable HTTP (streamablehttp_client)

```python
# The ClientSession doesn't care about transport!
# Just give it read and write streams

async with sse_client(url) as (read, write):
    async with ClientSession(read, write) as session:
        ...

# OR

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        ...
```

This abstraction is key to understanding the router - it can use ClientSession with any transport to talk to downstream servers.

---

## 8. The Router: Dual-Identity Pattern

### 8.1 The Core Insight

The router has TWO identities:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   UPSTREAM                     DOWNSTREAM                   │
│   (Clients connect to us)      (We connect to servers)      │
│                                                             │
│   ┌─────────────┐              ┌─────────────┐              │
│   │             │              │             │              │
│   │   Router    │              │   Router    │              │
│   │   SERVER    │              │   CLIENT    │              │
│   │             │              │             │              │
│   │  FastMCP    │              │ClientSession│              │
│   │  instance   │              │  instances  │              │
│   │             │              │             │              │
│   └─────────────┘              └─────────────┘              │
│         ▲                            │                      │
│         │                            │                      │
│         │                            ▼                      │
│   ┌─────┴─────┐              ┌───────────────┐              │
│   │  Clients  │              │   Downstream  │              │
│   │           │              │   Servers     │              │
│   └───────────┘              └───────────────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**SERVER Hat (FastMCP):**
- Listens on port 8002
- Exposes tools: `process_query`, `list_available_tools`, `health_check`
- Accepts connections from clients
- Handles tool requests

**CLIENT Hat (ClientSession):**
- Connects to downstream servers (8000, 8001, etc.)
- Maintains persistent connections
- Calls tools on downstream servers
- Receives progress updates

### 8.2 Data Structures

```python
@dataclass
class DownstreamConnection:
    """Represents a connection to one downstream server."""
    name: str                    # "search_server"
    url: str                     # "http://localhost:8000/sse"
    session: ClientSession       # The active session
    tools: list                  # Tools from this server
    connected: bool              # Is it alive?

@dataclass  
class ToolRoute:
    """Maps a tool to its origin server."""
    tool_name: str      # "web_search"
    server_name: str    # "search_server"
    server_url: str     # "http://localhost:8000/sse"
    tool_schema: dict   # The tool's inputSchema

class DownstreamManager:
    """Manages all downstream connections."""
    connections: dict[str, DownstreamConnection]
    tool_registry: dict[str, ToolRoute]
    
    async def connect_all(self):
        """Connect to all configured downstream servers."""
        ...
    
    def get_tool_route(self, tool_name: str) -> ToolRoute:
        """Find which server has this tool."""
        return self.tool_registry.get(tool_name)
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """Route tool call to correct server."""
        route = self.get_tool_route(tool_name)
        session = self.connections[route.server_name].session
        return await session.call_tool(tool_name, arguments)
```

### 8.3 The Tool Routing Table

When the router starts, it builds a routing table:

```
┌─────────────────────────────────────────────────────────────┐
│                    TOOL ROUTING TABLE                       │
├─────────────────┬──────────────────┬────────────────────────┤
│  Tool Name      │  Server          │  Server URL            │
├─────────────────┼──────────────────┼────────────────────────┤
│  web_search     │  search_server   │  http://localhost:8000 │
│  calculate      │  calculator      │  http://localhost:8001 │
│  send_email     │  email_server    │  http://localhost:8003 │
│  query_hr       │  hr_server       │  http://localhost:8004 │
└─────────────────┴──────────────────┴────────────────────────┘
```

**Building the table:**
1. Connect to each downstream server
2. Call `session.list_tools()` on each
3. For each tool, create a ToolRoute entry
4. Store in `tool_registry`

**Handling conflicts:**
If two servers have a tool with the same name, you have options:
- Last one wins (simple, but loses data)
- Namespace: `search_server.web_search`, `backup.web_search`
- Error: Refuse to start if conflicts detected

### 8.4 The Router Tools

The router exposes these tools to clients:

```python
@mcp.tool()
async def process_query(query: str, ctx: Context) -> str:
    """
    Main entry point. Accepts a natural language query,
    plans which tools to use, executes them, synthesizes response.
    """
    # 1. Plan with LLM
    plan = await plan_tool_calls(query, available_tools)
    
    # 2. Execute tools on downstream servers
    results = []
    for tool_call in plan:
        result = await downstream_manager.call_tool(
            tool_call["tool"],
            tool_call["arguments"]
        )
        results.append(result)
    
    # 3. Synthesize with LLM
    response = await synthesize_response(query, results)
    return response

@mcp.tool()
async def list_available_tools(ctx: Context) -> str:
    """
    Returns information about all downstream tools.
    Useful for clients to understand capabilities.
    """
    tools = []
    for route in downstream_manager.tool_registry.values():
        tools.append({
            "name": route.tool_name,
            "server": route.server_name,
            "schema": route.tool_schema
        })
    return json.dumps(tools, indent=2)

@mcp.tool()
async def health_check(ctx: Context) -> str:
    """
    Check connection status to all downstream servers.
    """
    status = {}
    for name, conn in downstream_manager.connections.items():
        status[name] = "connected" if conn.connected else "disconnected"
    return json.dumps(status)
```

---

## 9. Connection Lifecycle Management

### 9.1 The Problem

SSE connections are managed by async context managers:

```python
async with sse_client(url) as (read, write):
    # Connection is alive HERE
    pass
# Connection is DEAD here
```

But we need connections to stay alive for the lifetime of the router, not just a single function call.

### 9.2 The Wrong Way

```python
class BadRouter:
    async def startup(self):
        # This will break!
        async with sse_client(url) as (read, write):
            self.session = ClientSession(read, write)
            await self.session.initialize()
        # Connection is dead when startup() returns!
    
    async def call_tool(self, name, args):
        # This will fail because connection is dead
        return await self.session.call_tool(name, args)
```

### 9.3 The AsyncExitStack Solution

`AsyncExitStack` lets you accumulate context managers and keep them all alive:

```python
from contextlib import AsyncExitStack

class GoodRouter:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session = None
    
    async def startup(self):
        # Enter the exit stack first
        await self.exit_stack.__aenter__()
        
        # Now register context managers - they stay alive!
        read, write = await self.exit_stack.enter_async_context(
            sse_client(url)
        )
        
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        await self.session.initialize()
        # Connection stays alive because exit_stack is still open!
    
    async def shutdown(self):
        # Clean up everything
        await self.exit_stack.__aexit__(None, None, None)
```

### 9.4 The Correct Pattern for the Router

```python
async def run_router():
    """
    Main entry point that keeps everything alive.
    """
    async with AsyncExitStack() as exit_stack:
        # ─────────────────────────────────────────────────────
        # PHASE 1: Connect to all downstream servers
        # ─────────────────────────────────────────────────────
        
        downstream_sessions = {}
        
        for server in DOWNSTREAM_SERVERS:
            # Register SSE connection with exit_stack
            read, write = await exit_stack.enter_async_context(
                sse_client(server["url"])
            )
            
            # Register ClientSession with exit_stack
            session = await exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            # Initialize the session
            await session.initialize()
            
            # Store for later use
            downstream_sessions[server["name"]] = session
        
        # ─────────────────────────────────────────────────────
        # PHASE 2: Build tool routing table
        # ─────────────────────────────────────────────────────
        
        for name, session in downstream_sessions.items():
            tools = await session.list_tools()
            for tool in tools.tools:
                downstream_manager.register_tool(tool, name, session)
        
        # ─────────────────────────────────────────────────────
        # PHASE 3: Start the router server
        # ─────────────────────────────────────────────────────
        
        # Create the FastMCP server
        mcp = FastMCP("agenticnexus-router")
        
        # Register tools (process_query, etc.)
        register_router_tools(mcp)
        
        # Get the SSE app
        sse_app = mcp.sse_app()
        
        # Run uvicorn - this blocks until shutdown
        config = uvicorn.Config(sse_app, host="0.0.0.0", port=8002)
        server = uvicorn.Server(config)
        await server.serve()
        
        # ─────────────────────────────────────────────────────
        # PHASE 4: Cleanup (automatic when exit_stack closes)
        # ─────────────────────────────────────────────────────
        # All connections are cleaned up automatically!
```

### 9.5 Why This Works

```
Timeline of execution:
────────────────────────────────────────────────────────────────

1. Enter AsyncExitStack
   │
2. │ Enter sse_client(server1) ──────────────────────────────┐
   │ │                                                       │
3. │ │ Enter ClientSession(read1, write1) ─────────────────┐ │
   │ │ │                                                   │ │
4. │ │ │ Enter sse_client(server2) ──────────────────────┐ │ │
   │ │ │ │                                               │ │ │
5. │ │ │ │ Enter ClientSession(read2, write2) ─────────┐ │ │ │
   │ │ │ │ │                                           │ │ │ │
6. │ │ │ │ │ Run uvicorn server (blocks here) ◀────────┼─┼─┼─┼── All connections alive!
   │ │ │ │ │                                           │ │ │ │
   │ │ │ │ │ (Server running, handling requests...)    │ │ │ │
   │ │ │ │ │                                           │ │ │ │
   │ │ │ │ │ (Ctrl+C received)                         │ │ │ │
   │ │ │ │ │                                           │ │ │ │
7. │ │ │ │ Exit ClientSession(read2, write2) ──────────┘ │ │ │
   │ │ │ │                                               │ │ │
8. │ │ │ Exit sse_client(server2) ───────────────────────┘ │ │
   │ │ │                                                   │ │
9. │ │ Exit ClientSession(read1, write1) ──────────────────┘ │
   │ │                                                       │
10.│ Exit sse_client(server1) ───────────────────────────────┘
   │
11.Exit AsyncExitStack (all cleanup complete)
```

**Key insight:** All context managers stay alive until the server shuts down, because they're all registered with the same AsyncExitStack.

---

## 10. Streaming and Progress: Bidirectional Flow

### 10.1 How Progress Flows

```
┌─────────────────────────────────────────────────────────────┐
│                    PROGRESS FLOW                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   CLIENT          ROUTER              DOWNSTREAM            │
│     │               │                     │                 │
│     │──process_query──▶                   │                 │
│     │               │                     │                 │
│     │◀──progress(0.1)───                  │                 │
│     │  "Planning..."│                     │                 │
│     │               │                     │                 │
│     │               │───call web_search──▶│                 │
│     │               │                     │                 │
│     │               │◀──progress(0.3)─────│                 │
│     │◀──progress(0.35)──                  │  (forwarded)    │
│     │               │                     │                 │
│     │               │◀──progress(0.7)─────│                 │
│     │◀──progress(0.55)──                  │  (forwarded)    │
│     │               │                     │                 │
│     │               │◀──result────────────│                 │
│     │               │                     │                 │
│     │◀──progress(0.9)───                  │                 │
│     │  "Synthesizing"                     │                 │
│     │               │                     │                 │
│     │◀──result──────│                     │                 │
│     │               │                     │                 │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 Progress in the Router

The router has TWO sources of progress:
1. **Router's own progress** (planning, synthesizing)
2. **Forwarded progress** from downstream servers

```python
@mcp.tool()
async def process_query(query: str, ctx: Context) -> str:
    # Router's own progress
    await ctx.report_progress(0.1, 1.0, "Planning tool calls...")
    
    plan = await plan_tool_calls(query)
    
    await ctx.report_progress(0.2, 1.0, "Executing tools...")
    
    # For each downstream call, forward their progress
    for i, tool_call in enumerate(plan):
        base_progress = 0.2 + (0.6 * i / len(plan))
        
        # Create a callback that forwards progress
        async def forward_progress(p, t, msg):
            # Scale downstream progress to our range
            scaled = base_progress + (0.6 / len(plan)) * (p / (t or 1))
            await ctx.report_progress(scaled, 1.0, f"[{tool_call['tool']}] {msg}")
        
        result = await downstream_manager.call_tool(
            tool_call["tool"],
            tool_call["arguments"],
            progress_callback=forward_progress
        )
    
    await ctx.report_progress(0.9, 1.0, "Synthesizing response...")
    
    response = await synthesize_response(query, results)
    
    await ctx.report_progress(1.0, 1.0, "Complete!")
    
    return response
```

### 10.3 The Closure Problem (Important!)

This is a common Python bug that bit us:

```python
# BUG: All callbacks will use the LAST value of tool_call!
for tool_call in plan:
    async def forward_progress(p, t, msg):
        print(f"[{tool_call['tool']}] {msg}")  # ← tool_call is captured by reference!
    
    await call_tool(..., progress_callback=forward_progress)
```

**Why?** Python closures capture variables by **reference**, not by **value**. By the time the callback is called, the loop has moved on.

**Fix: Factory function to capture value:**

```python
def make_progress_callback(captured_tool_name, base_progress):
    async def forward_progress(p, t, msg):
        # captured_tool_name is frozen at creation time
        print(f"[{captured_tool_name}] {msg}")
    return forward_progress

for tool_call in plan:
    callback = make_progress_callback(tool_call['tool'], base_progress)
    await call_tool(..., progress_callback=callback)
```

### 10.4 SSE Message Flow

Here's what actually goes over the wire:

**Client → Router (POST):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "process_query",
    "arguments": {"query": "latest news"},
    "_meta": {"progressToken": "client-token-123"}
  }
}
```

**Router → Client (SSE):**
```
event: message
data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":"client-token-123","progress":0.1,"total":1.0,"message":"Planning..."}}

event: message
data: {"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":"client-token-123","progress":0.35,"total":1.0,"message":"[web_search] Calling API..."}}

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"Here are the latest news..."}]}}
```

---

## 11. The LLM Brain: Planning and Synthesis

### 11.1 Why an Internal LLM?

The router could just pass queries to downstream servers. But that's dumb:
- How does it know WHICH tool to call?
- How does it combine results from multiple tools?
- How does it handle complex queries that need multiple steps?

**Solution:** An internal LLM that:
1. **Plans** which tools to call
2. **Synthesizes** results into coherent responses

### 11.2 The Planning Function

```python
async def plan_tool_calls(query: str, available_tools: list) -> list:
    """
    Use LLM to decide which tools to call and with what arguments.
    
    Returns:
        List of tool calls: [{"tool": "name", "arguments": {...}}]
    """
    
    # Build the prompt
    tools_description = format_tools_for_llm(available_tools)
    
    prompt = f"""Given this user query and available tools, decide which tools to call.

USER QUERY: {query}

AVAILABLE TOOLS:
{tools_description}

Respond with a JSON array of tool calls. Each call should have:
- "tool": the tool name
- "arguments": object with the tool's parameters

Example response:
[
  {{"tool": "web_search", "arguments": {{"query": "latest AI news"}}}},
  {{"tool": "calculate", "arguments": {{"expression": "2+2"}}}}
]

If no tools are needed, respond with an empty array: []
"""

    # Call the LLM
    response = await openai_client.responses.create(
        model="gpt-5",
        input=prompt,
        # Force JSON output
    )
    
    # Parse the response
    return json.loads(response.output[0].content[0].text)
```

### 11.3 The Synthesis Function

```python
async def synthesize_response(query: str, tool_results: list) -> str:
    """
    Use LLM to combine tool results into a coherent response.
    
    Args:
        query: Original user query
        tool_results: List of {"tool": "name", "result": "...", "success": bool}
    
    Returns:
        Human-readable response
    """
    
    results_text = "\n".join([
        f"[{r['tool']}]: {r['result']}" 
        for r in tool_results
    ])
    
    prompt = f"""Based on the user's query and tool results, provide a helpful response.

USER QUERY: {query}

TOOL RESULTS:
{results_text}

Provide a clear, concise response that directly addresses the user's query.
If any tools failed, acknowledge this gracefully.
"""

    response = await openai_client.responses.create(
        model="gpt-5",
        input=prompt,
    )
    
    return response.output[0].content[0].text
```

### 11.4 LLM Choice Considerations

| LLM | Speed | Quality | Cost | Notes |
|-----|-------|---------|------|-------|
| GPT-4 | Slow | Best | High | Good for complex planning |
| GPT-5 | Fast | Excellent | Medium | Best balance for router |
| Claude | Medium | Excellent | Medium | Good for synthesis |
| Llama 3.3 70B | Fast | Good | Low | Good for simple planning |

For production, consider:
- **Fast LLM for planning** (decisions are structured, speed matters)
- **Quality LLM for synthesis** (user sees this output)

---

## 12. Complete Request Flow: Step by Step

Let's trace a complete request through the system:

### 12.1 Setup (Before Any Requests)

```
STARTUP SEQUENCE:
────────────────────────────────────────────────────────────

1. Router starts
   │
2. ├── Connect to search_server (8000)
   │   ├── GET /sse → session_id
   │   ├── initialize handshake
   │   └── list_tools() → ["web_search"]
   │
3. ├── Connect to calculator_server (8001)
   │   ├── GET /sse → session_id
   │   ├── initialize handshake
   │   └── list_tools() → ["calculate"]
   │
4. ├── Build routing table:
   │   │  web_search → search_server
   │   │  calculate → calculator_server
   │
5. ├── Start FastMCP server on port 8002
   │
6. └── Ready for clients!
```

### 12.2 Client Connection

```
CLIENT CONNECTION:
────────────────────────────────────────────────────────────

1. Client: GET http://localhost:8002/sse
   │
2. Router: 200 OK, Content-Type: text/event-stream
   │        event: endpoint
   │        data: /messages/?session_id=xyz789
   │
3. Client: Stores session_id, connection established
   │
4. Client: POST /messages/?session_id=xyz789
   │        {"jsonrpc":"2.0","id":1,"method":"initialize",...}
   │
5. Router: (via SSE)
   │        {"jsonrpc":"2.0","id":1,"result":{...}}
   │
6. Client: POST (initialized notification)
   │
7. Client: POST (tools/list request)
   │
8. Router: (via SSE)
   │        {"jsonrpc":"2.0","id":2,"result":{"tools":[
   │          {"name":"process_query",...},
   │          {"name":"list_available_tools",...},
   │          {"name":"health_check",...}
   │        ]}}
```

### 12.3 Query Execution

```
QUERY: "What's the latest AI news and what's 15% of $2500?"
────────────────────────────────────────────────────────────

1. CLIENT → ROUTER: tools/call(process_query, {query: "..."})
   │
2. ROUTER: Receives request, starts process_query handler
   │
3. ROUTER → CLIENT: progress(0.1, "Planning tool calls...")
   │
4. ROUTER → GPT-5: "Given this query and tools, what should I call?"
   │
5. GPT-5 → ROUTER: [
   │                  {"tool": "web_search", "arguments": {"query": "latest AI news"}},
   │                  {"tool": "calculate", "arguments": {"expression": "2500 * 0.15"}}
   │                ]
   │
6. ROUTER → CLIENT: progress(0.2, "Executing 2 tools...")
   │
7. ROUTER → SEARCH_SERVER: tools/call(web_search, {query: "latest AI news"})
   │
8. SEARCH_SERVER → ROUTER: progress(0.3, "Calling API...")
   │
9. ROUTER → CLIENT: progress(0.35, "[web_search] Calling API...")
   │
10. SEARCH_SERVER → ROUTER: progress(0.7, "Processing results...")
    │
11. ROUTER → CLIENT: progress(0.45, "[web_search] Processing results...")
    │
12. SEARCH_SERVER → ROUTER: result({"text": "Here are AI news..."})
    │
13. ROUTER → CALCULATOR: tools/call(calculate, {expression: "2500 * 0.15"})
    │
14. CALCULATOR → ROUTER: result({"text": "375"})
    │
15. ROUTER → CLIENT: progress(0.8, "All tools complete")
    │
16. ROUTER → CLIENT: progress(0.9, "Synthesizing response...")
    │
17. ROUTER → GPT-5: "Combine these results into a response"
    │
18. GPT-5 → ROUTER: "Here's the latest AI news: ... Also, 15% of $2500 is $375."
    │
19. ROUTER → CLIENT: progress(1.0, "Complete!")
    │
20. ROUTER → CLIENT: result({"text": "Here's the latest AI news..."})
```

### 12.4 Connection Cleanup

```
SHUTDOWN SEQUENCE:
────────────────────────────────────────────────────────────

1. Ctrl+C received
   │
2. Uvicorn begins shutdown
   │
3. Client SSE connections closed
   │
4. AsyncExitStack begins cleanup:
   │
5. ├── Close ClientSession to calculator_server
   │   └── Session sends close notification
   │
6. ├── Close sse_client to calculator_server
   │   └── HTTP connection closed
   │
7. ├── Close ClientSession to search_server
   │   └── Session sends close notification
   │
8. └── Close sse_client to search_server
       └── HTTP connection closed

9. Shutdown complete
```

---

## 13. Error Handling and Edge Cases

### 13.1 Downstream Server Unavailable

```python
async def call_tool_with_retry(tool_name: str, arguments: dict):
    """Call tool with retry logic."""
    route = downstream_manager.get_tool_route(tool_name)
    
    for attempt in range(3):
        try:
            session = downstream_manager.get_session(route.server_name)
            if not session:
                raise ConnectionError(f"No connection to {route.server_name}")
            
            return await session.call_tool(tool_name, arguments)
            
        except (ConnectionError, TimeoutError) as e:
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                await try_reconnect(route.server_name)
            else:
                # Mark server as disconnected
                downstream_manager.mark_disconnected(route.server_name)
                raise
```

### 13.2 Tool Execution Timeout

```python
async def call_tool_with_timeout(tool_name: str, arguments: dict, timeout: float = 30.0):
    """Call tool with timeout."""
    try:
        async with asyncio.timeout(timeout):
            return await downstream_manager.call_tool(tool_name, arguments)
    except asyncio.TimeoutError:
        return {
            "tool": tool_name,
            "result": f"Tool execution timed out after {timeout}s",
            "success": False
        }
```

### 13.3 LLM Planning Failure

```python
async def plan_tool_calls_safely(query: str, tools: list) -> list:
    """Plan with fallback for LLM failures."""
    try:
        return await plan_tool_calls(query, tools)
    except json.JSONDecodeError:
        # LLM returned invalid JSON
        logger.error("LLM returned invalid JSON for planning")
        return []
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        # Fallback: try to match query to tool names
        return fallback_planning(query, tools)

def fallback_planning(query: str, tools: list) -> list:
    """Simple keyword-based fallback planning."""
    calls = []
    query_lower = query.lower()
    
    if "search" in query_lower or "news" in query_lower:
        calls.append({"tool": "web_search", "arguments": {"query": query}})
    
    if "calculate" in query_lower or any(c in query for c in "+-*/"):
        # Try to extract expression
        calls.append({"tool": "calculate", "arguments": {"expression": query}})
    
    return calls
```

### 13.4 Partial Failure Handling

```python
async def execute_tools_with_partial_failure(plan: list) -> list:
    """Execute tools, continue even if some fail."""
    results = []
    
    for tool_call in plan:
        try:
            result = await call_tool_with_timeout(
                tool_call["tool"],
                tool_call["arguments"]
            )
            results.append({
                "tool": tool_call["tool"],
                "result": result,
                "success": True
            })
        except Exception as e:
            results.append({
                "tool": tool_call["tool"],
                "result": f"Error: {str(e)}",
                "success": False
            })
    
    return results
```

---

## 14. Production Considerations

### 14.1 Security

```python
# 1. API Key Authentication
@mcp.tool()
async def process_query(query: str, ctx: Context) -> str:
    # Extract API key from request metadata
    api_key = ctx.request_context.get("api_key")
    if not validate_api_key(api_key):
        raise AuthenticationError("Invalid API key")
    
    # Proceed with query...

# 2. Rate Limiting
from limits import RateLimiter

rate_limiter = RateLimiter(requests=100, period=60)  # 100 req/min

@mcp.tool()
async def process_query(query: str, ctx: Context) -> str:
    client_id = ctx.client_id
    if not rate_limiter.allow(client_id):
        raise RateLimitError("Rate limit exceeded")
    
    # Proceed...

# 3. Input Validation
def validate_query(query: str) -> str:
    if len(query) > 10000:
        raise ValueError("Query too long")
    if contains_injection_patterns(query):
        raise ValueError("Invalid query content")
    return query.strip()
```

### 14.2 Observability

```python
import logging
import time
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

@mcp.tool()
async def process_query(query: str, ctx: Context) -> str:
    with tracer.start_as_current_span("process_query") as span:
        span.set_attribute("query.length", len(query))
        
        start_time = time.time()
        
        try:
            # Planning
            with tracer.start_as_current_span("planning"):
                plan = await plan_tool_calls(query)
                span.set_attribute("plan.tool_count", len(plan))
            
            # Execution
            with tracer.start_as_current_span("execution"):
                results = await execute_tools(plan)
            
            # Synthesis
            with tracer.start_as_current_span("synthesis"):
                response = await synthesize_response(query, results)
            
            duration = time.time() - start_time
            logger.info(f"Query processed in {duration:.2f}s", extra={
                "query_length": len(query),
                "tools_called": len(plan),
                "duration_ms": duration * 1000
            })
            
            return response
            
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logger.error(f"Query failed: {e}", exc_info=True)
            raise
```

### 14.3 Scaling

```
HORIZONTAL SCALING:
────────────────────────────────────────────────────────────

                    ┌──────────────────┐
                    │   Load Balancer  │
                    │   (nginx/HAProxy)│
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Router 1 │   │ Router 2 │   │ Router 3 │
        │  (8002)  │   │  (8012)  │   │  (8022)  │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Search  │  │Calculator│  │   HR     │
        │  Server  │  │  Server  │  │  Server  │
        └──────────┘  └──────────┘  └──────────┘

Considerations:
- SSE connections are sticky (must stay on same router instance)
- Load balancer needs sticky sessions (by IP or cookie)
- Downstream connections can be shared or per-instance
```

### 14.4 Health Checks and Recovery

```python
async def health_check_loop():
    """Periodically check downstream server health."""
    while True:
        for name, conn in downstream_manager.connections.items():
            try:
                # Simple ping
                tools = await asyncio.wait_for(
                    conn.session.list_tools(),
                    timeout=5.0
                )
                conn.connected = True
                conn.last_healthy = time.time()
            except Exception as e:
                logger.warning(f"Health check failed for {name}: {e}")
                conn.connected = False
                
                # Attempt reconnection
                await try_reconnect(name)
        
        await asyncio.sleep(30)  # Check every 30 seconds
```

### 14.5 Graceful Shutdown

```python
import signal

shutdown_event = asyncio.Event()

def handle_shutdown(signum, frame):
    logger.info("Shutdown signal received")
    shutdown_event.set()

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

async def run_router():
    async with AsyncExitStack() as exit_stack:
        # ... setup code ...
        
        # Run server with shutdown handling
        config = uvicorn.Config(sse_app, host="0.0.0.0", port=8002)
        server = uvicorn.Server(config)
        
        # Start server in background
        server_task = asyncio.create_task(server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Graceful shutdown
        logger.info("Starting graceful shutdown...")
        
        # Stop accepting new connections
        server.should_exit = True
        
        # Wait for existing requests to complete (with timeout)
        try:
            await asyncio.wait_for(server_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Shutdown timeout, forcing exit")
        
        # Exit stack cleanup happens automatically
```

---

## 15. Implementation Checklist

### Phase 1: Foundation
- [ ] Understand SSE transport mechanics
- [ ] Understand JSON-RPC message format
- [ ] Understand context manager lifecycle
- [ ] Set up development environment

### Phase 2: Basic Server
- [ ] Create FastMCP server
- [ ] Implement simple tool (health_check)
- [ ] Test SSE connection with curl
- [ ] Test tool call with simple client

### Phase 3: Basic Client
- [ ] Connect to single downstream server
- [ ] List tools from downstream
- [ ] Call tool on downstream
- [ ] Handle progress callbacks

### Phase 4: Router Core
- [ ] Implement AsyncExitStack lifecycle
- [ ] Connect to multiple downstream servers
- [ ] Build tool routing table
- [ ] Implement process_query without LLM

### Phase 5: LLM Integration
- [ ] Implement planning function
- [ ] Implement synthesis function
- [ ] Handle LLM errors gracefully
- [ ] Test with complex multi-tool queries

### Phase 6: Progress Streaming
- [ ] Forward progress from downstream
- [ ] Fix closure bug in loop
- [ ] Test bidirectional streaming
- [ ] Verify progress reaches client

### Phase 7: Error Handling
- [ ] Handle downstream disconnection
- [ ] Implement retry logic
- [ ] Handle partial failures
- [ ] Add timeout handling

### Phase 8: Production Hardening
- [ ] Add authentication
- [ ] Add rate limiting
- [ ] Add logging/tracing
- [ ] Add health checks
- [ ] Test graceful shutdown

---

## Appendix A: Key Code Patterns

### A.1 The AsyncExitStack Pattern

```python
from contextlib import AsyncExitStack

async def main():
    async with AsyncExitStack() as stack:
        # Register context managers
        resource1 = await stack.enter_async_context(get_resource1())
        resource2 = await stack.enter_async_context(get_resource2())
        
        # Both resources stay alive until stack exits
        await do_work(resource1, resource2)
        
    # Both resources automatically cleaned up here
```

### A.2 The Progress Callback Factory

```python
def make_progress_callback(tool_name: str, base: float, range_size: float, ctx: Context):
    """Factory to avoid closure bugs."""
    async def callback(progress: float, total: float | None, message: str | None):
        scaled = base + range_size * (progress / (total or 1.0))
        await ctx.report_progress(scaled, 1.0, f"[{tool_name}] {message}")
    return callback

# Usage:
for i, tool in enumerate(tools):
    base = 0.2 + (0.6 * i / len(tools))
    callback = make_progress_callback(tool["name"], base, 0.6/len(tools), ctx)
    await call_tool(..., progress_callback=callback)
```

### A.3 The Tool Routing Pattern

```python
@dataclass
class ToolRoute:
    tool_name: str
    server_name: str
    session: ClientSession
    schema: dict

class ToolRouter:
    def __init__(self):
        self.routes: dict[str, ToolRoute] = {}
    
    def register(self, tool_name: str, server_name: str, session: ClientSession, schema: dict):
        self.routes[tool_name] = ToolRoute(tool_name, server_name, session, schema)
    
    async def call(self, tool_name: str, arguments: dict, **kwargs) -> Any:
        route = self.routes.get(tool_name)
        if not route:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await route.session.call_tool(tool_name, arguments, **kwargs)
```

---

## Appendix B: Debugging Tips

### B.1 SSE Connection Issues

```bash
# Test SSE endpoint directly
curl -N -H "Accept: text/event-stream" http://localhost:8002/sse

# Should see:
# event: endpoint
# data: /messages/?session_id=xxx
```

### B.2 Message Flow Debugging

```python
# Add logging to see all messages
import logging
logging.getLogger("mcp").setLevel(logging.DEBUG)

# Or wrap the streams
class DebugStream:
    def __init__(self, stream, name):
        self.stream = stream
        self.name = name
    
    async def send(self, message):
        print(f"[{self.name}] SEND: {message}")
        await self.stream.send(message)
    
    async def receive(self):
        message = await self.stream.receive()
        print(f"[{self.name}] RECV: {message}")
        return message
```

### B.3 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `RuntimeError: cancel scope in different task` | Context manager exited in wrong task | Use AsyncExitStack |
| `404 Not Found` on `/messages` | Wrong routing or session expired | Check session_id, verify endpoint |
| `Connection refused` | Downstream server not running | Start all servers first |
| Progress not received | Missing progressToken | Include `_meta.progressToken` |
| Tool not found | Routing table not built | Ensure `list_tools()` called |

---

## Appendix C: Quick Reference

### C.1 MCP Message Types

```
Initialize:     Client → Server, start session
Initialized:    Client → Server, session ready (notification)
tools/list:     List available tools
tools/call:     Execute a tool
progress:       Progress notification (notification)
```

### C.2 SSE Event Format

```
event: message
data: {"jsonrpc":"2.0","method":"...","params":{...}}

event: endpoint  
data: /messages/?session_id=xxx
```

### C.3 JSON-RPC Format

```json
// Request (has id)
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}

// Response (has id)
{"jsonrpc":"2.0","id":1,"result":{...}}

// Notification (no id)
{"jsonrpc":"2.0","method":"notifications/progress","params":{...}}
```

---

## Appendix D: File Structure for Production Router

```
agenticnexus/
├── router/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration
│   ├── server.py            # FastMCP server setup
│   ├── downstream.py        # Downstream connection management
│   ├── routing.py           # Tool routing table
│   ├── planning.py          # LLM planning functions
│   ├── synthesis.py         # LLM synthesis functions
│   └── middleware/
│       ├── auth.py          # Authentication
│       ├── rate_limit.py    # Rate limiting
│       └── logging.py       # Request logging
├── tests/
│   ├── test_routing.py
│   ├── test_planning.py
│   └── test_e2e.py
├── config/
│   ├── servers.yaml         # Downstream server config
│   └── settings.yaml        # Router settings
└── Dockerfile
```

---

## Conclusion

This document has covered the MCP Router architecture from first principles:

1. **Networking foundations** - HTTP, SSE, bidirectional communication
2. **MCP protocol** - JSON-RPC, message types, tool execution
3. **Server architecture** - FastMCP, Context, progress reporting
4. **Client architecture** - ClientSession, streams, callbacks
5. **Router pattern** - Dual identity, connection lifecycle, tool routing
6. **Streaming** - Progress forwarding, closure bugs, SSE flow
7. **LLM integration** - Planning, synthesis, error handling
8. **Production concerns** - Security, observability, scaling

With this foundation, you can:
- Debug issues at any layer
- Extend the router with new capabilities
- Build production-grade systems
- Teach others how it works

The key insight: **The router is just a translator sitting between two worlds** - it speaks "MCP server" to clients and "MCP client" to downstream servers, while using an LLM brain to make intelligent decisions about what to do.

---

*"The best way to understand a system is to build it from scratch. The second best way is to read a document like this."*

---

**Document Version History:**
- v1.0 (December 2025): Initial comprehensive version