"""Declarative round-boundary interventions.

Defines the data model for the scheduled actions a simulation can perform
at the start of a given round: swapping one agent for a fresh instance
(with a configurable per-channel history visibility), disabling
postmortem, and injecting a case. The schedule is carried inside scenario knobs as a
``scheduled_events`` list and dispatched by the runtime's
``RoundBoundaryScheduler`` when the game clock advances.

Per-channel history visibility for the swapped-in agent is the
``ChannelVisibility`` union in :mod:`glossogen.models.channel_visibility`.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, model_validator

from glossogen.model_catalog import Provider
from glossogen.models.channel_visibility import ChannelVisibility, ChannelVisibilityFromRound


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
    provider: Provider
    channel_visibility: dict[str, ChannelVisibility] = Field(default_factory=dict)
    system_prompt: str | None = None

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


class InjectCase(BaseModel):
    """Override the round-N case with a scenario-supplied payload.

    The runtime hands ``payload`` opaquely to the scenario's
    ``inject_case_payload`` hook at the start of ``at_round``; the scenario
    decodes the dict into whatever case-data shape it uses internally and
    arranges for the next round's injection to render the override instead
    of the natural-cycle case. Used by veyru to inject novel motifs at a
    chosen round boundary; the payload schema is scenario-specific and
    validated inside the scenario hook, not here.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["inject_case"] = "inject_case"
    at_round: int = Field(ge=2)
    payload: dict[str, Any]


ScheduledEvent = Annotated[
    SwapAgent | SetPostmortem | InjectCase,
    Discriminator("type"),
]
