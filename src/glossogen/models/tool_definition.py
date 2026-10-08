"""Pydantic models for tool calls an agent makes and the tools it is offered."""

from typing import Any

from pydantic import BaseModel


class ToolCallRequest(BaseModel):
    """A request from an agent to invoke a specific tool with the given arguments."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


class RecordedToolDefinition(BaseModel):
    """A tool as an agent is offered it: name, description, and input schema."""

    name: str
    description: str
    input_schema: dict[str, Any]
