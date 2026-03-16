"""Pydantic models representing tool definitions, call requests, and call results."""

from typing import Any

from pydantic import BaseModel


class ToolParameter(BaseModel):
    """A single parameter within a tool's signature."""

    name: str
    param_type: str
    description: str
    required: bool


class ToolSpec(BaseModel):
    """Schema describing a tool that an agent can invoke, including
    its name, description, and parameters.
    """

    name: str
    description: str
    parameters: list[ToolParameter]


class ToolCallRequest(BaseModel):
    """A request from an agent to invoke a specific tool with the given arguments."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolCallResult(BaseModel):
    """The result returned after executing a tool call, containing
    the output or an error indication.
    """

    call_id: str
    tool_name: str
    output: str
    is_error: bool
