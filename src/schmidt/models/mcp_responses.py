"""Pydantic models for structured MCP tool responses.

Defines typed response models for simulation MCP tools, replacing raw dicts
with validated structures that agents receive as JSON.
"""

from pydantic import BaseModel


class ChannelMessage(BaseModel):
    """A single message as returned to agents by read_channel and send_message.

    ``round`` is the simulation round in which the message was sent, so an
    agent reading the channel can tell whether an instruction was issued for
    the current round or carried over from a previous one. ``elapsed_seconds``
    is the time the message was sent expressed as seconds since the simulation
    began (millisecond precision), so agents reason about relative timing
    without a verbose wall-clock timestamp.
    """

    round: int
    sender: str
    text: str
    elapsed_seconds: float


class ReadChannelResult(BaseModel):
    """Response from the read_channel MCP tool.

    ``current_round`` is the round the simulation is in at read time, so the
    agent can compare it against each message's ``round`` and identify stale
    instructions.
    """

    current_round: int
    messages: list[ChannelMessage]


class SendMessageResult(BaseModel):
    """Response from the send_message MCP tool.

    On success, status is "sent" and new_messages is empty.
    On conflict (new messages arrived since the agent's last read_channel),
    status is "conflict" and new_messages contains the unseen messages.
    The token_count reports the word count of the original text as a proxy
    for LLM tokens, or zero when the message was not delivered. ``current_round``
    is the round the simulation is in at send time, mirroring the field on
    ``ReadChannelResult`` and ``read_notifications`` so the agent always has
    a consistent reference for the current round.

    ``message_id`` is the id of the persisted ``SimulationMessage`` when
    ``status == "sent"``; it is ``None`` for ``conflict`` / ``rejected``
    results where no message was created. Because this result is captured in
    the ``ToolResultReceived`` event (which also carries the pristine
    ``arguments.text``), it provides an exact join from the pristine text the
    agent sent to the persisted ``MessageSent`` (whose ``message.text`` may
    have been transformed by ``transform_outgoing_message``, e.g. channel
    noise).
    """

    status: str
    detail: str
    new_messages: list[ChannelMessage]
    token_count: int
    current_round: int
    message_id: str | None
