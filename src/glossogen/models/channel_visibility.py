"""Per-channel history visibility for an agent swapped into a run.

A discriminated union (``Full``, ``None``, ``FromRound``) rather than a binary
blocked-channels set, so a swap can declare e.g. "show ``link`` only from round 16
onwards" without affecting other channels. Swap configs in scenario knobs and the
``AgentSwappedMidRun`` event both carry it.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field


class ChannelVisibilityFull(BaseModel):
    """Channel history fully visible to the swapped-in agent.

    The new agent's ``read_channel`` returns the entire prior history
    of this channel, and the predecessor's tool calls targeting it
    survive history reconstruction unchanged.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["full"] = "full"


class ChannelVisibilityNone(BaseModel):
    """Channel history hidden from the swapped-in agent.

    The new agent's ``member_join_index`` for the channel is bumped to
    the current message count, so ``read_channel`` returns only post-swap
    messages. Every send/read tool call the predecessor made on this
    channel is dropped from the reconstructed history along with its
    matching tool return.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["none"] = "none"


class ChannelVisibilityFromRound(BaseModel):
    """Channel history windowed from a specific round onward.

    Sets ``member_join_index`` for the swapped-in agent to the channel's
    message count at the start of round ``round_floor``. The predecessor's
    reconstructed tool calls on this channel are filtered: every
    ``read_channel`` call is dropped (its tool-return blob would otherwise
    leak older messages), and every ``send_message`` call is dropped iff
    its ``ToolCallInvoked.round_number < round_floor``.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["from_round"] = "from_round"
    round_floor: int = Field(ge=1)


ChannelVisibility = Annotated[
    ChannelVisibilityFull | ChannelVisibilityNone | ChannelVisibilityFromRound,
    Discriminator("kind"),
]
