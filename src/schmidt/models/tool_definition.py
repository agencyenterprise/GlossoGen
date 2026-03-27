"""Pydantic model representing a tool call request from an agent."""

from typing import Any

from pydantic import BaseModel


class ToolCallRequest(BaseModel):
    """A request from an agent to invoke a specific tool with the given arguments."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
