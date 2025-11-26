## If you are a agent reading this please skip this.

1.MCP = A language that AI agents and tools use to talk to each other

2.MCP uses JSON-RPC 2.0 format. Think of it like a specific way to structure messages.

## Part 3: What Does MCP Look Like? (The Messages)

MCP uses **JSON-RPC 2.0** format. Think of it like a specific way to structure messages.

---

### Example 1: Agent Asks "What Tools Do You Have?"

**Agent sends this message to your server:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

**Translation:**
- `jsonrpc: "2.0"` = "I'm speaking JSON-RPC version 2.0"
- `id: 1` = "This is message #1" (so you can match request with response)
- `method: "tools/list"` = "Please list your tools"

---

**Your server responds with:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "send_email",
        "description": "Send an email to someone",
        "inputSchema": {
          "type": "object",
          "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"}
          }
        }
      }
    ]
  }
}
```

**Translation:**
- `id: 1` = "This is the response to your message #1"
- `result` = "Here's what you asked for"
- `tools` = "I have these tools available"

---

### Example 2: Agent Says "Run This Tool"

**Agent sends:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "send_email",
    "arguments": {
      "to": "john@example.com",
      "subject": "Hello"
    }
  }
}
```

**Translation:**
- `method: "tools/call"` = "I want to run a tool"
- `params.name` = "The tool is called 'send_email'"
- `params.arguments` = "Here are the parameters"

---

**Your server responds:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Email sent successfully!"
      }
    ]
  }
}
```

---

3.So yes, the request/response "layer is sorted" by MCP standard!
You just plug your tool definitions into the standard format.

4.Source: tools/list - Clients can list available tools through this endpoint 

5.A decorator is basically a function that wraps another function and adds extra stuff to it. Instead of modifying the original function, you wrap it with @decorator_name and it does extra work before, after, or around that function.

6.Decorators reduce boilerplate and make your code cleaner. For tool definitions, they let developers focus on writing the logic without worrying about metadata and registration.Retry

7.Why Two Classes?

ToolSchema: Clean, JSON-safe, LLM-friendly (no functions, just metadata)
ToolDefinition: Executable, Python-based, backend-only (includes the actual function)

8.Anthropic designed MCP to use JSON-RPC 2.0. All MCP clients (Claude, ChatGPT, etc.) send requests in this format.

9.Key Difference
| Aspect            | REST                          | JSON-RPC (MCP)                |
|-------------------|------------------------------|-------------------------------|
| Endpoint          | Many (/search, /tools, /execute) | One (/mcp)                    |
| Action determined by | HTTP path + method          | method field in JSON           |
| Request format    | Custom (your choice)          | Standard JSON-RPC format       |
| Response format   | Custom (your choice)          | Standard JSON-RPC format       |

10.Simple command to start the server venv\Scripts\python.exe src\agenticnexus\mcp_server.py
