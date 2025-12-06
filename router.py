"""
AgenticNexus MCP Router v2 - Fixed SSE Connection Management
Author: Aditya Bhatt

The key fix: SSE connections must stay within their async context.
Solution: Use a lifespan pattern where connections are established 
and maintained within the same async context as the server.

Architecture:
- SERVER (port 8002): Exposes `process_query` tool to LLM clients  
- CLIENT: Connects to downstream MCP servers (8000, 8001)
- BRAIN: GPT-5 via Responses API for planning and synthesis

Run:
    python router_v2.py
"""
import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server.fastmcp import FastMCP, Context
import uvicorn

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

DOWNSTREAM_SERVERS = [
    {"name": "search_server", "url": "http://localhost:8000/sse"},
    {"name": "calculator_server", "url": "http://localhost:8001/sse"},
]

ROUTER_PORT = 8002

# OpenAI client for internal LLM (the "brain") - Using Responses API with GPT-5
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
LLM_MODEL = "gpt-5"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class DownstreamConnection:
    """Represents a connection to a downstream MCP server."""
    name: str
    url: str
    session: ClientSession | None = None
    tools: list = field(default_factory=list)
    connected: bool = False


@dataclass 
class ToolRoute:
    """Maps a tool name to its downstream server."""
    tool_name: str
    server_name: str
    server_url: str
    tool_schema: dict


# =============================================================================
# Connection Manager (Singleton)
# =============================================================================

class DownstreamManager:
    """Manages connections to downstream MCP servers."""
    
    def __init__(self):
        self.connections: dict[str, DownstreamConnection] = {}
        self.tool_registry: dict[str, ToolRoute] = {}
        self._exit_stack: AsyncExitStack | None = None
        self._initialized = False
    
    async def connect_all(self, exit_stack: AsyncExitStack) -> None:
        """
        Connect to all configured downstream servers.
        Uses the provided exit_stack to manage connection lifecycles.
        """
        self._exit_stack = exit_stack
        
        print(f"\n{'='*60}")
        print("  AgenticNexus Router - Connecting to Downstream Servers")
        print(f"{'='*60}\n")
        
        for server_config in DOWNSTREAM_SERVERS:
            name = server_config["name"]
            url = server_config["url"]
            
            print(f"  → Connecting to {name} ({url})...")
            
            try:
                # Enter the SSE client context using exit_stack
                # This keeps the connection alive for the lifetime of exit_stack
                read_stream, write_stream = await exit_stack.enter_async_context(
                    sse_client(url)
                )
                
                # Enter the ClientSession context
                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                
                # Initialize the session
                await session.initialize()
                
                # Get tools from this server
                tools_response = await session.list_tools()
                tools = tools_response.tools
                
                # Store connection
                self.connections[name] = DownstreamConnection(
                    name=name,
                    url=url,
                    session=session,
                    tools=tools,
                    connected=True
                )
                
                # Register tools in routing table
                for tool in tools:
                    self.tool_registry[tool.name] = ToolRoute(
                        tool_name=tool.name,
                        server_name=name,
                        server_url=url,
                        tool_schema={
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        }
                    )
                
                print(f"    ✓ Connected! Found {len(tools)} tools: {[t.name for t in tools]}")
                
            except Exception as e:
                print(f"    ✗ Failed to connect: {e}")
                self.connections[name] = DownstreamConnection(
                    name=name,
                    url=url,
                    connected=False
                )
        
        self._initialized = True
        print(f"\n  Total tools available: {len(self.tool_registry)}")
        print(f"  Tool registry: {list(self.tool_registry.keys())}")
        print(f"\n{'='*60}\n")
    
    def get_all_tools_for_llm(self) -> list[dict]:
        """Get all tools formatted for OpenAI API."""
        tools = []
        for route in self.tool_registry.values():
            tools.append({
                "type": "function",
                "name": route.tool_name,
                "description": route.tool_schema.get("description", ""),
                "parameters": route.tool_schema.get("inputSchema", {})
            })
        return tools
    
    def get_tool_route(self, tool_name: str) -> ToolRoute | None:
        """Get the route for a specific tool."""
        return self.tool_registry.get(tool_name)
    
    def get_session(self, server_name: str) -> ClientSession | None:
        """Get the session for a specific server."""
        conn = self.connections.get(server_name)
        return conn.session if conn else None
    
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: dict,
        progress_callback: callable = None
    ) -> Any:
        """Call a tool on the appropriate downstream server."""
        route = self.get_tool_route(tool_name)
        if not route:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        session = self.get_session(route.server_name)
        if not session:
            raise ValueError(f"No connection to server: {route.server_name}")
        
        # Wrap progress callback with debug logging
        async def debug_progress_callback(p: float, t: float | None, m: str | None):
            print(f"  [Downstream Progress] {tool_name}: {p}/{t} - {m}")
            if progress_callback:
                await progress_callback(p, t, m)
        
        # Execute with progress callback
        print(f"  [Calling Downstream] {tool_name} on {route.server_name}")
        result = await session.call_tool(
            tool_name,
            arguments,
            meta={"progressToken": f"router-{tool_name}"},
            progress_callback=debug_progress_callback if progress_callback else None
        )
        print(f"  [Downstream Complete] {tool_name}")
        
        return result


# Global manager instance
downstream_manager = DownstreamManager()


# =============================================================================
# Internal LLM Planner (GPT-5 via Responses API)
# =============================================================================

async def plan_tool_calls(query: str, available_tools: list[dict]) -> list[dict]:
    """
    Use internal LLM (GPT-5 via Responses API) to plan which tools to call.
    Returns a list of tool calls with arguments.
    """
    
    # Build tool descriptions for the prompt
    tool_descriptions = "\n".join([
        f"- {t['name']}: {t.get('description', 'No description')}\n  Schema: {json.dumps(t.get('parameters', {}), indent=2)}"
        for t in available_tools
    ])
    
    planning_prompt = f"""You are a planning assistant. Given a user query and available tools, 
decide which tools to call and with what arguments.

AVAILABLE TOOLS:
{tool_descriptions}

USER QUERY: {query}

Respond with a JSON array of tool calls. Each tool call should have:
- "tool": the tool name (exactly as shown above)
- "arguments": the arguments to pass (matching the schema)

Example response format:
[
  {{"tool": "web_search", "arguments": {{"objective": "Find latest news", "search_queries": ["AI news 2025"]}}}}
]

If no tools are needed, respond with an empty array: []

IMPORTANT: 
- Only use tools that are in the AVAILABLE TOOLS list
- Match the argument names exactly to the schema
- Respond ONLY with valid JSON, no other text or markdown"""

    try:
        # Use Responses API with GPT-5
        response = openai_client.responses.create(
            model=LLM_MODEL,
            input=[
                {
                    "type": "message",
                    "role": "user", 
                    "content": [{"type": "input_text", "text": planning_prompt}]
                }
            ],
            reasoning={"effort": "low"},
            text={"verbosity": "low"}
        )
        
        # Extract text from response - handle different output structures
        result = ""
        for item in response.output:
            # Check for direct text attribute (some response types)
            if hasattr(item, 'text') and item.text:
                result += item.text
            # Check for content array (message type responses)
            elif hasattr(item, 'content') and item.content:
                for content in item.content:
                    if hasattr(content, 'text') and content.text:
                        result += content.text
        
        # Debug: print what we got
        print(f"  [Planner] Raw LLM output: {result[:200]}..." if len(result) > 200 else f"  [Planner] Raw LLM output: {result}")
        
        if not result.strip():
            print(f"  [Planner] Warning: Empty response from LLM")
            return []
        
        # Clean up markdown if present
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()
        
        parsed = json.loads(result)
        
        # Handle both array and object with "tools" key
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "tools" in parsed:
            return parsed["tools"]
        else:
            return []
            
    except Exception as e:
        print(f"  [Planner Error] {e}")
        return []


async def synthesize_response(query: str, tool_results: list[dict]) -> str:
    """
    Use internal LLM (GPT-5 via Responses API) to synthesize a final response from tool results.
    """
    
    results_text = "\n\n".join([
        f"Tool: {r['tool']}\nSuccess: {r.get('success', True)}\nResult: {r['result']}"
        for r in tool_results
    ])
    
    synthesis_prompt = f"""Based on the following tool execution results, provide a comprehensive 
and helpful response to the user's query.

USER QUERY: {query}

TOOL RESULTS:
{results_text}

Provide a clear, well-structured response that addresses the user's query using the information 
from the tool results. Be concise but comprehensive."""

    try:
        # Use Responses API with GPT-5
        response = openai_client.responses.create(
            model=LLM_MODEL,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": synthesis_prompt}]
                }
            ],
            reasoning={"effort": "low"},
            text={"verbosity": "low"}
        )
        
        # Extract text from response - handle different output structures
        result = ""
        for item in response.output:
            # Check for direct text attribute
            if hasattr(item, 'text') and item.text:
                result += item.text
            # Check for content array
            elif hasattr(item, 'content') and item.content:
                for content in item.content:
                    if hasattr(content, 'text') and content.text:
                        result += content.text
        
        return result.strip() if result else "Unable to synthesize response."
        
    except Exception as e:
        return f"Error synthesizing response: {e}"


# =============================================================================
# Router MCP Server
# =============================================================================

mcp = FastMCP(name="agenticnexus-router")


@mcp.tool()
async def process_query(
    query: str,
    ctx: Context
) -> str:
    """
    Process a natural language query using available downstream tools.
    
    This is the main entry point for the AgenticNexus router. It will:
    1. Analyze your query to determine which tools are needed
    2. Execute the required tools on downstream servers
    3. Synthesize a comprehensive response
    
    Args:
        query: Your natural language query or request
    
    Returns:
        A comprehensive response based on tool execution results
    """
    
    # Report initial progress
    await ctx.report_progress(0.1, 1.0, "Analyzing query and planning tool calls...")
    
    # Get available tools
    available_tools = downstream_manager.get_all_tools_for_llm()
    
    if not available_tools:
        return "No downstream tools available. Please check server connections."
    
    # Plan tool calls using internal LLM
    await ctx.report_progress(0.2, 1.0, "Planning which tools to use...")
    planned_calls = await plan_tool_calls(query, available_tools)
    
    if not planned_calls:
        # No tools needed, just respond directly using GPT-5
        await ctx.report_progress(0.9, 1.0, "Generating direct response...")
        
        response = openai_client.responses.create(
            model=LLM_MODEL,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}]
                }
            ],
            reasoning={"effort": "low"},
            text={"verbosity": "low"}
        )
        
        # Extract text from response - handle different output structures
        result = ""
        for item in response.output:
            # Check for direct text attribute
            if hasattr(item, 'text') and item.text:
                result += item.text
            # Check for content array
            elif hasattr(item, 'content') and item.content:
                for content in item.content:
                    if hasattr(content, 'text') and content.text:
                        result += content.text
        
        return result.strip() if result else "Unable to generate response."
    
    # Execute planned tool calls
    await ctx.report_progress(0.3, 1.0, f"Executing {len(planned_calls)} tool(s)...")
    
    tool_results = []
    total_tools = len(planned_calls)
    
    for idx, tool_call in enumerate(planned_calls):
        tool_name = tool_call.get("tool")
        tool_args = tool_call.get("arguments", {})
        
        progress = 0.3 + (0.5 * (idx / total_tools))
        await ctx.report_progress(
            progress, 
            1.0, 
            f"Executing tool {idx+1}/{total_tools}: {tool_name}"
        )
        
        try:
            # Create progress forwarder with captured variables (fix closure bug)
            # We need to capture tool_name and progress at THIS iteration
            def make_progress_forwarder(captured_tool_name: str, captured_progress: float):
                async def forward_progress(p: float, t: float | None, m: str | None):
                    # Forward downstream progress to our client
                    try:
                        sub_progress = captured_progress + (0.5 / total_tools) * (p / (t or 1.0))
                        await ctx.report_progress(
                            sub_progress, 
                            1.0, 
                            f"[{captured_tool_name}] {m or 'Working...'}"
                        )
                    except Exception as e:
                        print(f"  [Progress Forward Error] {e}")
                return forward_progress
            
            progress_forwarder = make_progress_forwarder(tool_name, progress)
            
            # Call the tool on downstream server
            result = await downstream_manager.call_tool(
                tool_name,
                tool_args,
                progress_callback=progress_forwarder
            )
            
            # Extract result text
            result_text = ""
            if result.content:
                if hasattr(result.content[0], 'text'):
                    result_text = result.content[0].text
                else:
                    result_text = str(result.content[0])
            
            tool_results.append({
                "tool": tool_name,
                "result": result_text,
                "success": True
            })
            
        except Exception as e:
            print(f"  [Tool Execution Error] {tool_name}: {e}")
            tool_results.append({
                "tool": tool_name,
                "result": f"Error: {str(e)}",
                "success": False
            })
    
    # Synthesize final response
    await ctx.report_progress(0.9, 1.0, "Synthesizing final response...")
    
    final_response = await synthesize_response(query, tool_results)
    
    await ctx.report_progress(1.0, 1.0, "Complete!")
    
    return final_response


@mcp.tool()
async def list_available_tools(ctx: Context) -> str:
    """
    List all tools available through the AgenticNexus router.
    
    Returns information about all downstream tools that can be used
    via the process_query function.
    """
    
    tools_info = []
    
    for name, route in downstream_manager.tool_registry.items():
        tools_info.append({
            "name": route.tool_name,
            "server": route.server_name,
            "description": route.tool_schema.get("description", "No description")
        })
    
    return json.dumps({
        "total_tools": len(tools_info),
        "tools": tools_info
    }, indent=2)


@mcp.tool()
async def health_check(ctx: Context) -> str:
    """
    Check the health of all downstream server connections.
    """
    
    status = []
    
    for name, conn in downstream_manager.connections.items():
        status.append({
            "server": name,
            "url": conn.url,
            "connected": conn.connected,
            "tools_count": len(conn.tools) if conn.tools else 0
        })
    
    return json.dumps({
        "router_status": "healthy",
        "downstream_servers": status
    }, indent=2)


# =============================================================================
# Main Entry Point - Proper Async Context Management
# =============================================================================

async def run_router():
    """
    Run the router with proper async context management.
    All SSE connections stay within this async context.
    """
    print("\n" + "="*60)
    print("  AgenticNexus MCP Router v2")
    print("  " + "-"*56)
    print(f"  Router Port: {ROUTER_PORT}")
    print(f"  Downstream Servers: {len(DOWNSTREAM_SERVERS)}")
    print("="*60 + "\n")
    
    # AsyncExitStack keeps all connections alive
    async with AsyncExitStack() as exit_stack:
        # Connect to all downstream servers
        await downstream_manager.connect_all(exit_stack)
        
        if not downstream_manager.tool_registry:
            print("  ⚠ Warning: No tools loaded from downstream servers!")
            print("  Make sure localhost:8000 and localhost:8001 are running.")
        
        print(f"  Starting router on port {ROUTER_PORT}...")
        print(f"  Endpoint: http://localhost:{ROUTER_PORT}/sse")
        print("\n" + "="*60 + "\n")
        
        # Get the SSE app directly from FastMCP - don't wrap it
        sse_app = mcp.sse_app()
        
        # Run with uvicorn directly using the sse_app
        config = uvicorn.Config(
            sse_app,  # Use sse_app directly, not wrapped
            host="0.0.0.0", 
            port=ROUTER_PORT,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        # This blocks until server stops, keeping exit_stack alive
        await server.serve()


def main():
    """Entry point."""
    try:
        asyncio.run(run_router())
    except KeyboardInterrupt:
        print("\n  Shutting down...")


if __name__ == "__main__":
    main()