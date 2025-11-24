"""
Tool schema definitions for AgenticNexus.

ToolSchema: JSON-serializable format for MCP responses.
ToolDefinition: Internal storage that includes the callable function.
"""

from typing import Any, Callable
from pydantic import BaseModel, Field


class ToolSchema(BaseModel):
    """
    MCP-compliant tool format.
    Sent to agents via tools/list response.
    """
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="What the tool does")
    inputSchema: dict[str, Any] = Field(..., description="JSON Schema for parameters")


class ToolDefinition:
    """
    Internal tool storage.
    Includes the actual function to execute.
    """
    def __init__(
        self,
        name: str,
        description: str,
        inputSchema: dict[str, Any],
        function: Callable
    ):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema
        self.function = function

    def to_schema(self) -> ToolSchema:
        """Convert to MCP-compliant format (drops function)."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            inputSchema=self.inputSchema
        )