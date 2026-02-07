"""
Tool Registry for Agent Tool Calling

Manages tool registration, validation, and execution.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolResultStatus(str, Enum):
    """Tool execution result status."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """Result of tool execution."""

    status: ToolResultStatus
    result: Any
    error: Optional[str] = None
    execution_time: Optional[float] = None


class ToolParameter(BaseModel):
    """Parameter definition for a tool."""

    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None


class Tool(BaseModel):
    """Tool definition for function calling."""

    name: str = Field(description="Tool name")
    description: str = Field(description="Tool description")
    parameters: List[ToolParameter] = Field(default_factory=list, description="Tool parameters")
    execute_fn: Optional[Callable] = Field(
        default=None, exclude=True, description="Execution function"
    )

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert tool to OpenAI function calling format."""
        properties = {}
        required = []

        for param in self.parameters:
            prop_def = {"type": param.type, "description": param.description}
            if param.enum:
                prop_def["enum"] = param.enum

            properties[param.name] = prop_def

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert tool to Anthropic tool use format."""
        # Anthropic uses similar format to OpenAI
        return self.to_openai_format()

    def to_google_format(self) -> Dict[str, Any]:
        """Convert tool to Google GenAI function calling format."""
        # Google GenAI 2.x supports automatic function calling with Python functions
        # For manual function calling, we use FunctionDeclaration format
        properties = {}
        required = []

        for param in self.parameters:
            prop_def = {
                "type": param.type.upper()
                if param.type in ["string", "number", "boolean"]
                else param.type,
                "description": param.description,
            }
            if param.enum:
                prop_def["enum"] = param.enum

            properties[param.name] = prop_def

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": required,
            },
        }

    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        Validate tool arguments against parameter definitions.

        Args:
            arguments: Arguments to validate

        Returns:
            True if valid
        """
        for param in self.parameters:
            if param.required and param.name not in arguments:
                logger.error(f"Missing required parameter: {param.name}")
                return False

            if param.name in arguments:
                value = arguments[param.name]
                # Basic type checking
                if param.type == "string" and not isinstance(value, str):
                    logger.error(f"Parameter {param.name} must be string")
                    return False
                elif param.type == "number" and not isinstance(value, (int, float)):
                    logger.error(f"Parameter {param.name} must be number")
                    return False
                elif param.type == "boolean" and not isinstance(value, bool):
                    logger.error(f"Parameter {param.name} must be boolean")
                    return False

                # Enum validation
                if param.enum and value not in param.enum:
                    logger.error(f"Parameter {param.name} must be one of {param.enum}")
                    return False

        return True

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute tool with given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            ToolResult
        """
        import time

        if not self.execute_fn:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                result=None,
                error="Tool execution function not defined",
            )

        if not self.validate_arguments(arguments):
            return ToolResult(status=ToolResultStatus.ERROR, result=None, error="Invalid arguments")

        try:
            start_time = time.time()
            result = self.execute_fn(**arguments)
            execution_time = time.time() - start_time

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                result=result,
                execution_time=execution_time,
            )
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {e}", exc_info=True)
            return ToolResult(status=ToolResultStatus.ERROR, result=None, error=str(e))


class ToolRegistry:
    """Registry for managing tools."""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """
        Register a tool.

        Args:
            tool: Tool to register
        """
        if tool.name in self.tools:
            logger.warning(f"Tool {tool.name} already registered, overwriting")

        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool or None if not found
        """
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self.tools.keys())

    def get_tools_for_llm(self, provider: str = "openai") -> List[Dict[str, Any]]:
        """
        Get tools in format suitable for LLM function calling.

        Args:
            provider: LLM provider ("gemini" or "perplexity")

        Returns:
            List of tool definitions
        """
        if provider == "openai":
            return [tool.to_openai_format() for tool in self.tools.values()]
        elif provider == "anthropic":
            return [tool.to_anthropic_format() for tool in self.tools.values()]
        elif provider == "gemini":
            return [tool.to_google_format() for tool in self.tools.values()]
        elif provider == "perplexity":
            # Perplexity uses OpenAI-compatible format
            return [tool.to_openai_format() for tool in self.tools.values()]
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            ToolResult
        """
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                result=None,
                error=f"Tool {name} not found",
            )

        return tool.execute(arguments)
