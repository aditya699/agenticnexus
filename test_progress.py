"""
Minimal test to verify MCP progress notifications work
"""
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client


async def test_progress():
    """Test progress notifications from AgenticNexus server."""
    server_url = "http://localhost:8000/sse"
    
    print("🔌 Connecting to server...")
    
    async with sse_client(server_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("✅ Connected!\n")
            
            # List tools
            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}\n")
            
            # Define progress callback
            progress_updates = []
            async def progress_callback(progress: float, total: float | None, message: str | None):
                update = f"Progress: {progress}/{total} - {message}"
                progress_updates.append(update)
                print(f"📊 {update}")
            
            # Call web_search with progress tracking
            print("🔍 Calling web_search with progress tracking...\n")
            result = await session.call_tool(
                "web_search",
                {
                    "objective": "Test search",
                    "search_queries": ["Python MCP"],
                    "max_results": 2,
                    "max_chars_per_result": 200
                },
                meta={"progressToken": "test-token-123"},
                progress_callback=progress_callback
            )
            
            print(f"\n✅ Tool completed!")
            print(f"📊 Total progress updates received: {len(progress_updates)}")
            
            if progress_updates:
                print("\nProgress updates:")
                for update in progress_updates:
                    print(f"  - {update}")
            else:
                print("\n❌ NO PROGRESS UPDATES RECEIVED!")
                print("This means the server isn't sending them or client isn't receiving them.")


if __name__ == "__main__":
    asyncio.run(test_progress())