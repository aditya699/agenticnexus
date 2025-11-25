"""
MCP server - FastAPI routes for JSON-RPC requests.
"""
from fastapi import APIRouter
from .models import (
    MCPRequest,
    ERROR_METHOD_NOT_FOUND
)
from .utils import handle_tools_list, handle_tools_call

router = APIRouter()


@router.post("/mcp")
async def mcp_endpoint(request: MCPRequest):
    """
    Main MCP endpoint.
    Routes requests based on method field.
    """
    
    # Route: tools/list
    if request.method == "tools/list":
        return handle_tools_list(request)
    
    # Route: tools/call
    elif request.method == "tools/call":
        return handle_tools_call(request)
    
    # Error: unknown method
    else:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {
                "code": ERROR_METHOD_NOT_FOUND,
                "message": f"Method '{request.method}' not found"
            }
        }