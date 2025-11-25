"""
AgenticNexus - Main FastAPI application.
"""
from fastapi import FastAPI
from .mcp.server import router as mcp_router

# Create FastAPI app
app = FastAPI(
    title="AgenticNexus",
    description="Production-grade MCP and A2A communication backend",
    version="0.1.0"
)

# Include MCP router
app.include_router(mcp_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "AgenticNexus",
        "version": "0.1.0",
        "status": "operational"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """
    Run on startup.
    Load all tools from tools/core/
    """
    print("🚀 AgenticNexus starting...")
    
    # Import tools to register them
    # This triggers the @tool decorator
    from .tools.core.search import tool as search_tool

    from .tools.base import TOOL_REGISTRY
    print(f"✅ Loaded {len(TOOL_REGISTRY)} tools")
    for tool_name in TOOL_REGISTRY:
        print(f"   - {tool_name}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)