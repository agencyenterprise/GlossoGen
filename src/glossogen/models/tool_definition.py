"""Pydantic models for tool calls an agent makes and the tools it is offered.

Also the hook that keeps a tool argument model's docstring out of the schema the
model reads.
"""

from typing import Any

from pydantic import BaseModel


def drop_schema_description(schema: dict[str, Any]) -> None:
    """Remove the class docstring, which is for developers, from a schema a model reads.

    A tool argument model passes it as ``json_schema_extra``; an enum calls it
    from ``__get_pydantic_json_schema__``.
    """
    schema.pop("description", None)


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
