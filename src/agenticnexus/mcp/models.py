"""
MCP protocol models - JSON-RPC 2.0 format.
"""
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


# ============ BASE MODELS ============

class MCPRequest(BaseModel):
    """Base request - all MCP requests have these fields."""
    jsonrpc: str = Field(default="2.0")
    id: Union[int, str] = Field(...)
    method: str = Field(...)
    params: Optional[dict[str, Any]] = Field(default=None)


class MCPResponse(BaseModel):
    """Base response - all MCP responses have these fields."""
    jsonrpc: str = Field(default="2.0")
    id: Union[int, str] = Field(...)
    result: Optional[dict[str, Any]] = Field(default=None)
    error: Optional[dict[str, Any]] = Field(default=None)


# ============ TOOLS/LIST ============

class ToolsListRequest(MCPRequest):
    """Request to list all tools."""
    method: str = Field(default="tools/list")


class ToolsListResponse(MCPResponse):
    """Response with list of tools."""
    result: dict[str, list] = Field(...)


# ============ TOOLS/CALL ============

class ToolsCallRequest(MCPRequest):
    """Request to execute a tool."""
    method: str = Field(default="tools/call")
    params: dict[str, Any] = Field(...)


class ToolsCallResponse(MCPResponse):
    """Response from tool execution."""
    result: dict[str, Any] = Field(...)


# ============ ERROR HANDLING ============

class MCPError(BaseModel):
    """Error structure."""
    code: int = Field(...)
    message: str = Field(...)
    data: Optional[dict[str, Any]] = Field(default=None)


# Error codes
ERROR_PARSE_ERROR = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL_ERROR = -32603