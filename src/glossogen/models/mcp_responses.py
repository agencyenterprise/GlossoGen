"""Pydantic models for structured MCP tool responses.

Defines typed response models for simulation MCP tools, replacing raw dicts
with validated structures that agents receive as JSON.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from glossogen.models.canvas import ToolResultImage


class SendStatus(StrEnum):
    """What happened to a ``send_message`` call."""

    SENT = "sent"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ChannelMessage(BaseModel):
    """A single message as returned to agents by read_channel and send_message.

    ``round`` is the simulation round in which the message was sent, so an
    agent reading the channel can tell whether an instruction was issued for
    the current round or carried over from a previous one. ``elapsed_seconds``
    is the time the message was sent expressed as seconds since the simulation
    began (millisecond precision), so agents reason about relative timing
    without a verbose wall-clock timestamp.

    ``image`` is set on a drawing: it is the number of the image attached to the
    same tool result, and ``text`` is empty. A text message leaves it out.
    """

    round: int
    sender: str
    text: str
    elapsed_seconds: float
    image: int | None = Field(default=None, exclude_if=lambda image: image is None)


class CarriesImages(BaseModel):
    """A tool result that can attach images, such as the drawings among the messages it lists.

    ``attached_images`` is left out of the JSON the agent reads. The runner
    attaches each image to the tool result, so the model sees the image itself.
    """

    attached_images: list[ToolResultImage] = Field(
        default_factory=list[ToolResultImage], exclude=True
    )


class SendReceipt(BaseModel):
    """The fields every ``send_message`` result carries, whatever else a scenario adds.

    ``message_id`` is the id of the persisted ``SimulationMessage`` when ``status``
    is ``SendStatus.SENT`` and ``None`` otherwise. Readers of a recorded result
    validate it against ``RecordedSendReceipt`` instead.
    """

    status: SendStatus
    message_id: str | None


class RecordedSendReceipt(BaseModel):
    """A ``send_message`` result as a run's event log recorded it.

    Results recorded before ``send_message`` returned a ``message_id`` carry
    none, and read as ``None``, the same as a call that posted nothing. The
    fields a scenario's own result adds are ignored.
    """

    status: SendStatus
    message_id: str | None = None


class ReadChannelResult(CarriesImages):
    """Response from the read_channel MCP tool.

    ``current_round`` is the round the simulation is in at read time, so the
    agent can compare it against each message's ``round`` and identify stale
    instructions.
    """

    current_round: int
    messages: list[ChannelMessage]


class SendMessageResult(SendReceipt, CarriesImages):
    """Response from the send_message MCP tool.

    On success, status is ``SendStatus.SENT`` and new_messages is empty.
    On conflict (new messages arrived since the agent's last read_channel),
    status is ``SendStatus.CONFLICT`` and new_messages contains the unseen messages,
    with the drawings among them rendered in ``attached_images``.
    The token_count reports the word count of the original text as a proxy
    for LLM tokens, or zero when the message was not delivered. ``current_round``
    is the round the simulation is in at send time, mirroring the field on
    ``ReadChannelResult`` and ``read_notifications`` so the agent always has
    a consistent reference for the current round.

    ``message_id`` is the id of the persisted ``SimulationMessage`` when
    ``status`` is ``SENT``; it is ``None`` for ``CONFLICT`` / ``REJECTED``
    results where no message was created. Because this result is captured in
    the ``ToolResultReceived`` event (which also carries the pristine
    ``arguments.text``), it provides an exact join from the pristine text the
    agent sent to the persisted ``MessageSent`` (whose ``message.text`` may
    have been transformed by ``transform_outgoing_message``, e.g. channel
    noise).
    """

    detail: str
    new_messages: list[ChannelMessage]
    token_count: int
    current_round: int
