"""Declarative round-boundary interventions.

Defines the data model for two scheduled actions a simulation can perform
at the start of a given round: swapping one agent for a fresh instance
(with a configurable per-channel history visibility), and disabling
postmortem. The schedule is carried inside scenario knobs as a
``scheduled_events`` list and dispatched by the runtime's
``RoundBoundaryScheduler`` when the game clock advances.

Per-channel history visibility for the swapped-in agent is encoded as a
discriminated union (``Full``, ``None``, ``FromRound``) rather than a
binary blocked-channels set, so a swap can declare e.g. "show
``link`` only from round 16 onwards" without affecting other channels.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, model_validator


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


class SwapAgent(BaseModel):
    """Replace one agent with a fresh instance at the start of ``at_round``.

    The new agent runs under the same ``agent_id`` (so channel
    membership is preserved) but is a brand-new pydantic-ai instance
    with reconstructed tool-call history (``tool_calls_only=True``)
    and per-channel visibility from ``channel_visibility``. Channels not
    listed in ``channel_visibility`` default to fully visible.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["swap_agent"] = "swap_agent"
    at_round: int = Field(ge=2)
    agent_id: str
    model: str
    provider: str
    channel_visibility: dict[str, ChannelVisibility] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_round_floors(self) -> Self:
        for channel_id, visibility in self.channel_visibility.items():
            if isinstance(visibility, ChannelVisibilityFromRound):
                if visibility.round_floor > self.at_round:
                    raise ValueError(
                        f"channel {channel_id!r} round_floor={visibility.round_floor} "
                        f"exceeds swap at_round={self.at_round}"
                    )
        return self


class SetPostmortem(BaseModel):
    """Toggle postmortem at the start of ``at_round``.

    Only ``enabled=False`` is supported (re-enable mid-run is not
    implemented). The runtime calls ``world.disable_postmortem_globally()``
    when this fires; subsequent postmortem injections and phase entries
    are skipped for the rest of the run.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["set_postmortem"] = "set_postmortem"
    at_round: int = Field(ge=2)
    enabled: bool

    @model_validator(mode="after")
    def _validate_disable_only(self) -> Self:
        if self.enabled:
            raise ValueError("set_postmortem mid-run only supports enabled=False")
        return self


ScheduledEvent = Annotated[SwapAgent | SetPostmortem, Discriminator("type")]
