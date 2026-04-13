"""Pydantic models for structured MCP tool responses.

Defines typed response models for simulation MCP tools, replacing raw dicts
with validated structures that agents receive as JSON.
"""

from pydantic import BaseModel


class ChannelMessage(BaseModel):
    """A single message as returned to agents by read_channel and send_message."""

    sender: str
    text: str
    timestamp: str


class SendMessageResult(BaseModel):
    """Response from the send_message MCP tool.

    On success, status is "sent" and new_messages is empty.
    On conflict (new messages arrived since the agent's last read_channel),
    status is "conflict" and new_messages contains the unseen messages.
    The token_count reports the word count of the original text as a proxy
    for LLM tokens, or zero when the message was not delivered.
    """

    status: str
    detail: str
    new_messages: list[ChannelMessage]
    token_count: int
