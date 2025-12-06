# MCP Router: Real Talk Notes

**Date**: November 30, 2025  
**Project**: AgenticNexus - MCP Router with Internal LLM Routing  
**Verdict**: It works... but should it exist? 🤔

---

## What We Actually Built

An MCP server that sits between enterprise LLMs and actual tools, using an internal GPT-5 to decide which downstream MCP server to call. Instead of exposing 10 tools directly, we expose 1 tool (`delegate_task`) and let GPT-5 figure out the routing.

```
Enterprise LLM → Router (MCP Server) 
                   ↓
              Internal GPT-5 (routing brain)
                   ↓
              Downstream MCP Servers (actual tools)
```

**Why?** To avoid token overhead from loading all tool definitions upfront.  
**Trade-off?** Added latency, complexity, and a whole new class of problems.

---

## The Journey (Speedrun Edition)

### Day 1: "This Should Be Easy"
- Set up MCP router with FastMCP ✓
- Exposed via ngrok ✓
- Connected downstream servers ✓
- First test... timeout. 💀

### Day 2: "Why Is Everything Timing Out?"

**Problem**: 60-second MCP timeout killing requests

**Things We Tried**:
1. Progress notifications (kept connection alive, didn't help)
2. Reading MCP protocol specs
3. Debugging for hours
4. More debugging
5. Even more debugging

**The Real Issue**: Tools had `"require_approval": "always"` 🤦

Tools were being called but stuck waiting for approval. Once we set `"require_approval": "never"`, they actually executed. Classic config issue that cost us 6 hours.

### Day 3: "It Works But..."

**New Problem**: `anyio.ClosedResourceError`

The flow:
1. Router gets request ✓
2. Internal GPT-5 calls downstream tools ✓  
3. Tools execute (6+ searches sometimes) ✓
4. GPT-5 processes results ✓
5. Response ready to send ✓
6. MCP session already closed 💥

**Why?** Large responses took 80+ seconds to generate. By the time we tried to send back, the 60-second timeout already killed the connection.

**Solution**: Streaming implementation
- Stream events from GPT-5 in real-time
- Accumulate text as it comes
- Don't buffer entire response
- Shorter responses work, longer ones still struggle

---

## Key Technical Findings

### MCP Protocol Timeouts
- **Default**: 60 seconds for requests
- **Progress notifications**: Should reset timer (but behavior varies by SDK)
- **Python SDK**: Handles progress correctly
- **TypeScript SDK**: Historically buggy with timeout resets

### Streaming Architecture
**The Problem with Buffering**:
```python
# Bad: Wait for everything, then return
response = await gpt5_call()  # Takes 80 seconds
return response  # Session already dead

# Better: Stream and accumulate
async for event in stream:
    accumulated_text += event.delta
return accumulated_text  # But still buffered at end
```

**What Actually Works**:
- Responses under ~2000 characters
- Completion time under 45 seconds
- 2-3 tool calls max

**What Fails**:
- 3000+ character responses
- 6+ downstream tool calls
- 80+ second processing time

### Approval Requirements
**Critical config for downstream servers**:
```python
{
    "url": "https://server.ngrok.app/sse",
    "require_approval": "never"  # ← Make tools actually run
}
```

Without this, tools get called but wait forever for approval.

---

## Performance Reality Check

### Successful Request Example
**Query**: "Latest AI news"  
**Timeline**:
- Start: 13:09:06
- Completion: 13:09:51
- **Duration**: 45 seconds ✓
- Events: 440
- Tool calls: 2
- Response: 1,745 characters
- **Result**: Success

### Failed Request Example
**Query**: "Latest Gurugram news"  
**Timeline**:
- Start: 13:12:16
- Completion: 13:13:50
- **Duration**: 94 seconds ✗
- Events: 930
- Tool calls: 7
- Response: 3,052 characters
- **Result**: `ClosedResourceError`

**Pattern**: Short = works, Long = dies

---

## Architectural Honesty

### What This Design Adds
```
Simple MCP:
Client → Server → Tools
(2 hops, predictable)

Our Design:
Client → Router → Internal LLM → Downstream Server → Tools
(4+ hops, unpredictable)
```

### Complexity Introduced
1. **Extra LLM call** for every request (latency + cost)
2. **Token overhead** from tool definitions in routing prompt
3. **Timeout risk** from cascading operations  
4. **Multi-layer debugging** (which layer failed?)
5. **Response size limits** (can't reliably do long responses)
6. **Monitoring complexity** (track router + downstream + internal LLM)

### The Debt Created
- Need sophisticated timeout handling
- Error propagation across 3+ layers
- Token cost on every request
- Hard to trace failures
- Future maintenance nightmare

### Why Standard MCP Exists
MCP already handles tool routing. The enterprise LLM can see all tools and decide which to call. That's literally the point of MCP.

**This router solves**: Token overhead from too many tool definitions  
**This router creates**: Everything else

---

## When This Makes Sense

**Valid Use Cases**:
- 100+ downstream tools (tool definition bloat is real)
- Dynamic tool availability (tools come and go)
- Complex routing logic (multi-step workflows)
- Centralized auth/logging (policy enforcement layer)

**Our Use Case**:
- 3 tools total (web_search, calculator, writing_style)
- Static tool set
- Simple routing
- No special auth needs

**Honest Assessment**: We don't need this architecture.

---

## What Actually Works

### Proven Solutions
1. **Short responses** (under 2000 chars)
2. **Limited tool calls** (2-3 max)
3. **Fast execution** (under 45 seconds)
4. **Streaming** from internal LLM
5. **Proper approval configs** on downstream servers

### Known Limitations
1. Long responses timeout
2. Complex queries with 6+ tool calls fail
3. No incremental response streaming to client
4. Hard 60-second wall from MCP protocol

---

## Recommendations

### If Building This (Manager Insists)
1. **Set aggressive limits**:
   ```python
   max_output_tokens=500  # Force short responses
   max_tool_calls=3       # Limit complexity
   timeout=40             # Leave buffer before MCP timeout
   ```

2. **Implement proper monitoring**:
   - Track routing decisions
   - Log downstream latencies
   - Monitor timeout rates
   - Alert on failures

3. **Document the debt**:
   - Why this architecture exists
   - What problems it solves
   - What problems it creates
   - When to refactor

4. **Plan the exit strategy**:
   - When tool count is < 10: Kill the router
   - When latency matters: Kill the router
   - When debugging takes hours: Kill the router

### If Pushing Back (The Real Solution)
**Show, don't tell**:
1. Build simple MCP server with tools directly exposed
2. Compare latency, complexity, debugging experience
3. Present both to manager
4. Let results speak

**The Simple Alternative**:
```python
# Just expose the damn tools directly
@mcp.tool()
def web_search(query: str) -> str:
    return search_api(query)

@mcp.tool()  
def calculator(expression: str) -> float:
    return eval(expression)
```

No routing LLM, no cascading timeouts, no mysterious failures.

---

## Technical Discoveries Worth Remembering

### SSE & MCP
- SSE connections can stay open for minutes
- But MCP request timeout is still 60 seconds
- Progress notifications ≠ response streaming
- Python MCP SDK is solid, TypeScript SDK has quirks

### OpenAI Responses API
- Streaming works well with `stream=True`
- Events come fast (10-50ms intervals)
- Accumulating text is straightforward
- Tool calls are interleaved with text generation

### Debugging Multi-Layer Systems
- Log at every boundary
- Include timestamps on everything
- Track request IDs across layers
- Monitor each hop independently

### The Approval Config Gotcha
**This will ruin your day**:
```python
# Default behavior - tools wait for approval
downstream_server = {"url": "..."}

# What you actually need
downstream_server = {
    "url": "...",
    "require_approval": "never"
}
```

Simple config, 6 hours of debugging.

---

## The Reality

**What works**: A technically functional MCP router that intelligently routes requests to downstream servers using an internal LLM.

**What's true**: It's over-engineered for the problem we're solving.

**What's next**: Either fix the timeout issues properly (incremental streaming to client) or acknowledge this is solving a problem we don't have.

---

## Final Thoughts

This was a masterclass in:
- Reading protocol specs
- Debugging distributed systems  
- Understanding timeouts and streaming
- Recognizing when "technically feasible" ≠ "good idea"

**The code works**. It's just questionable whether the code should exist.

Welcome to enterprise software architecture. 🎭

---

## Quick Reference

### Working Configuration
```python
# Router setup
client = openai.Client(api_key=os.getenv("OPENAI_API_KEY"))

response_stream = client.responses.create(
    model="gpt-5-2025-08-07",
    messages=[...],
    stream=True,
    tools=[...],
    reasoning_effort="low",
    text_verbosity="low",
    max_output_tokens=1000  # Limit response size
)

# Downstream server config
{
    "url": "https://server.ngrok.app/sse",
    "require_approval": "never"
}
```

### URLs
- Router: `https://c8d6c4a39bbf.ngrok-free.app/sse`
- Server 1: `https://0131279fd1e0.ngrok-free.app/sse`
- Server 2: `https://e71d5be7b4fc.ngrok-free.app/sse`

### Success Metrics
- Response time: < 45 seconds
- Character count: < 2000
- Tool calls: < 3
- Events processed: < 500

---

**Remember**: Just because you *can* build something doesn't mean you *should*. But hey, at least we proved it's possible. 🚀