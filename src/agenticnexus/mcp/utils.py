"""
MCP utilities - handler functions for processing requests.
"""
from .models import (
    MCPRequest,
    ERROR_INTERNAL_ERROR
)
from ..tools.base import get_all_tools, get_tool


def handle_tools_list(request: MCPRequest) -> dict:
    """
    Handle tools/list request.
    Returns all registered tools in MCP format.
    """
    try:
        # Get all tools from registry
        tools = get_all_tools()
        
        # Convert to MCP format (ToolSchema)
        tools_json = [tool.to_schema().model_dump() for tool in tools]
        
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {
                "tools": tools_json
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {
                "code": ERROR_INTERNAL_ERROR,
                "message": str(e)
            }
        }


def handle_tools_call(request: MCPRequest) -> dict:
    """
    Handle tools/call request.
    Executes a tool and returns the result.
    """
    try:
        # Extract tool name and arguments
        tool_name = request.params["name"]
        tool_args = request.params["arguments"]
        
        # Get tool from registry
        tool = get_tool(tool_name)
        
        if tool is None:
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool '{tool_name}' not found"
                        }
                    ],
                    "isError": True
                }
            }
        
        # Execute the tool
        result = tool.function(**tool_args)
        
        # Return result
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": str(result)
                    }
                ],
                "isError": False
            }
        }
        
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing tool: {str(e)}"
                    }
                ],
                "isError": True
            }
        }