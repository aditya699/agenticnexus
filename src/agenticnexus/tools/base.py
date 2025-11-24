"""
Tool registry and decorator for AgenticNexus.
NOTE:
1.MCP uses JSON Schema for tool input definitions.
2.JSON Schema types differ from Python types. That is not so important here, what is more important that json schema is language agnostic.(which means that ur mcp server can be written in any language and it will still be able to understand the tool definitions)
"""

from .schemas import ToolDefinition

# In-memory storage for all registered tools
TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def get_all_tools() -> list[ToolDefinition]:
    """Return all registered tools."""
    return list(TOOL_REGISTRY.values())


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool by name."""
    return TOOL_REGISTRY.get(name)

def python_type_to_json_schema(python_type: type) -> str:
    """Convert Python type to JSON Schema type."""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return type_map.get(python_type, "string")  # Default to string

import inspect
from typing import Callable

def tool(name: str, description: str) -> Callable:
    """
    Decorator to register a function as an MCP tool.
    
    Usage:
        @tool(name="echo", description="Returns what you send")
        def echo(message: str) -> str:
            return message

    NOTE: Usually decorators are used to modify the behavior of functions without chaning the function itself. But here we are using decorator to register the function as a tool in TOOL_REGISTRY. The original function remains unchanged and is returned at the end of the decorator.
    """
    def decorator(func: Callable) -> Callable:
        # Step 1: Get function parameters using inspect
        sig = inspect.signature(func)
        
        # Step 2: Build inputSchema from parameters
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            # Get type hint (default to str if not specified)
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else str
            
            # Convert to JSON Schema type
            json_type = python_type_to_json_schema(param_type)
            
            # Add to properties
            properties[param_name] = {"type": json_type}
            
            # If no default value, it's required
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        # Step 3: Create inputSchema
        input_schema = {
            "type": "object",
            "properties": properties,
            "required": required
        }
        
        # Step 4: Create ToolDefinition
        tool_def = ToolDefinition(
            name=name,
            description=description,
            inputSchema=input_schema,
            function=func
        )
        
        # Step 5: Register in TOOL_REGISTRY
        TOOL_REGISTRY[name] = tool_def
        
        # Step 6: Return original function
        return func
    
    return decorator