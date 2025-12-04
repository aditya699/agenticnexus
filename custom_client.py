"""
Author: Aditya Bhatt
Hybrid MCP Client - Responses API + Direct MCP Control

Architecture:
- OpenAI Responses API (GPT-5) for LLM decisions
- Direct MCP connection for tool execution + REAL-TIME progress visibility
- NO built-in MCP from OpenAI (we control everything)

PROVEN: Progress notifications stream in real-time from server!
"""
import asyncio
import json
import os
from openai import OpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client
from dotenv import load_dotenv

load_dotenv()

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def mcp_to_openai_tool(tool):
    """Convert MCP tool to OpenAI Responses API format."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.inputSchema
    }


async def process_query(query: str, session: ClientSession, openai_tools: list):
    """Process query using Responses API + direct MCP tool execution."""
    print(f"\n💬 You: {query}")
    print("🤖 Processing...\n")
    
    # Call OpenAI RESPONSES API with GPT-5 (NO server_url - we control tools!)
    try:
        stream = openai_client.responses.create(
            model="gpt-5",
            tools=openai_tools,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}]
                }
            ],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            stream=True,
            timeout=None
        )
    except Exception as e:
        print(f"\n❌ OpenAI API Error: {e}")
        print(f"Error details: {str(e)}")
        return
    
    tool_calls_detected = []
    assistant_response = ""
    current_tool_name = None
    
    # Stream events from GPT-5
    for event in stream:
        event_type = event.type
        
        # Capture tool name from output_item.added
        if event_type == "response.output_item.added":
            if hasattr(event, 'item') and hasattr(event.item, 'name'):
                current_tool_name = event.item.name
                if current_tool_name:
                    print(f"🔧 OpenAI wants to call: {current_tool_name}")
        
        # Function call completed - capture arguments
        elif event_type == "response.function_call_arguments.done":
            tool_calls_detected.append({
                "name": current_tool_name or "unknown",
                "arguments": event.arguments
            })
            
        # Assistant text streaming
        elif event_type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
            assistant_response += event.delta
    
    # If tools were called, execute them with REAL-TIME progress
    if tool_calls_detected:
        print(f"\n\n🔧 GPT-5 wants to call {len(tool_calls_detected)} tool(s)\n")
        
        all_tool_results = []
        
        for idx, tool_call in enumerate(tool_calls_detected, 1):
            tool_name = tool_call["name"]
            tool_args = json.loads(tool_call["arguments"])
            
            print(f"⚡ Tool {idx}/{len(tool_calls_detected)}: {tool_name}")
            print(f"📝 Arguments: {json.dumps(tool_args, indent=2)}\n")
            
            # Progress callback with visual progress bar
            async def progress_handler(progress: float, total: float | None, message: str | None):
                """Handle REAL-TIME progress notifications from MCP server."""
                if total and total > 0:
                    percentage = int((progress / total) * 100)
                    bar_length = 30
                    filled = int(bar_length * progress / total)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    status_msg = f" - {message}" if message else ""
                    print(f"\r📊 [{bar}] {percentage}%{status_msg}", end="", flush=True)
                elif message:
                    print(f"\r📊 {message}", end="", flush=True)
            
            # Execute via OUR MCP connection with STREAMING progress!
            result = await session.call_tool(
                tool_name, 
                tool_args,
                meta={"progressToken": f"progress-tool-{idx}"},
                progress_callback=progress_handler  # REAL-TIME UPDATES!
            )
            print("\n✅ Tool execution complete!\n")
            
            # Extract result
            result_text = ""
            if result.content:
                if hasattr(result.content[0], 'text'):
                    result_text = result.content[0].text
                else:
                    result_text = str(result.content[0])
            
            all_tool_results.append({
                "tool": tool_name,
                "result": result_text
            })
        
        # Send all results back to GPT-5 for final answer
        print("🧠 Sending results to GPT-5 for final answer...\n")
        
        # Build conversation with tool results
        conversation = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": query}]
            }
        ]
        
        # Add tool execution context
        tool_summary = "\n\n".join([
            f"Tool: {tr['tool']}\nResult: {tr['result']}" 
            for tr in all_tool_results
        ])
        
        conversation.append({
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": f"Here are the tool execution results:\n\n{tool_summary}\n\nPlease provide a comprehensive answer based on these results."
            }]
        })
        
        # Get final answer from GPT-5
        final_stream = openai_client.responses.create(
            model="gpt-5",
            input=conversation,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            stream=True
        )
        
        print("💡 Final Answer: ", end="", flush=True)
        for event in final_stream:
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)
        print("\n")
    
    return assistant_response


async def main():
    """Main hybrid client - connects to MCP server directly."""
    server_url = "http://localhost:8000/sse"
    
    print("=" * 60)
    print("🚀 HYBRID MCP CLIENT - GPT-5 + AgenticNexus")
    print("=" * 60)
    print("🔌 Connecting to AgenticNexus MCP server...")
    
    async with sse_client(server_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize connection
            await session.initialize()
            print("✅ Connected!\n")
            
            # Get tools from OUR server
            tools_response = await session.list_tools()
            tools = tools_response.tools
            print(f"🔧 Loaded {len(tools)} tools: {[t.name for t in tools]}\n")
            
            # Convert to OpenAI format
            openai_tools = [mcp_to_openai_tool(t) for t in tools]
            
            # Interactive loop
            while True:
                print("=" * 60)
                user_input = input("💬 You (or 'quit' to exit): ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 Goodbye!")
                    break
                
                if not user_input:
                    continue
                
                await process_query(user_input, session, openai_tools)


if __name__ == "__main__":
    asyncio.run(main())