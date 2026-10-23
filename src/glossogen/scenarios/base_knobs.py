"""The knobs every scenario has, whatever it simulates.

Each scenario defines its own knobs model extending ``BaseKnobs``, so it only
declares what is specific to it. Round count, phase durations, per-agent model
overrides, scheduled in-run swaps and history compaction all live here and work
the same everywhere.

The four fields with no default are the ones a run cannot be described without:
round count, round duration, the per-agent model map, and the per-round
communication budget. Everything else has a default that suits a scenario not
using that feature.
"""

from typing import Annotated, Any, cast

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.compaction_config import CompactionConfig
from glossogen.runtime.scheduled_events import ScheduledEvent
from glossogen.scenarios.channel_noise import NoiseReplacementMode


def _strip_text(value: object) -> object:
    """Strip surrounding whitespace from a string, leaving any other value as given."""
    if isinstance(value, str):
        return value.strip()
    return value


LEGACY_MAX_TOKENS_KNOB = "agent_max_tokens"


class AgentModelOverride(BaseModel):
    """Per-agent model/provider override configured in scenario knobs.

    Surrounding whitespace is stripped from both fields and an empty model is
    refused. A ``None`` provider means the run's default provider.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1)
    provider: Annotated[Provider | None, BeforeValidator(_strip_text)] = None


class BaseKnobs(BaseModel):
    """Base knobs shared by all scenarios.

    ``postmortem_duration_seconds`` defaults to 120.0 and is only meaningful
    when a scenario enables postmortem. Scenarios that do not use postmortem
    can ignore it entirely.

    ``replace_agent_default_channel_visibility`` maps channel IDs to a
    boolean that determines whether the replace-agent flow makes that
    channel's prior history visible to the replaced agent by default.
    Channel IDs not in the map default to ``True`` (visible). The
    simulation itself does not read this field at runtime; only the
    replace-agent CLI/HTTP/FE flows consult it to populate defaults.

    ``scheduled_events`` declares mid-run interventions (agent swaps and
    postmortem toggles) keyed off round boundaries. The runtime's
    ``RoundBoundaryScheduler`` dispatches each event when the game clock
    advances to its ``at_round``. Defaults to an empty list (no
    interventions; equivalent to a normal run).

    ``agent_model_settings`` is sent with every request every agent makes:
    the output cap and the thinking level, as ``AgentModelSettings`` documents
    them. The supervisor gives it to each agent, so no scenario reads it. A
    config written before it existed spells the cap ``agent_max_tokens``, which
    is folded in here; the old name loses to a ``max_tokens`` the new field
    names itself, since a fork merges the source's recorded config under the
    caller's.

    ``compaction`` enables provider-native history compaction (off by
    default). When enabled, the runner attaches the provider's compaction
    capability so older messages are summarized once an agent's input
    tokens exceed ``compaction.token_threshold``.

    ``postmortem_enabled`` opens a discussion phase after each round, and
    ``postmortem_disabled_at_start`` closes it for the whole run from round
    one. Both default off, so a scenario that never mentions postmortem
    behaves as if the feature did not exist.

    ``channel_noise_level`` is the per-character corruption probability the
    platform applies to the scenario's noisy channels, and
    ``noise_replacement_mode`` decides what a corrupted character becomes.
    The default of 0.0 leaves messages untouched.

    A field belongs here when platform code reads it. Values only the
    scenario itself consumes, such as its case-generation seed or which model
    judges its rounds, are declared by the scenario, because a default here
    would describe behaviour the platform does not have. That is why there is
    no ``judge_model``: three scenarios resolve their rounds without an LLM.
    """

    model_config = ConfigDict(extra="forbid")

    round_count: int
    max_round_duration_seconds: float
    model_overrides: dict[str, AgentModelOverride]
    postmortem_duration_seconds: float = 120.0
    postmortem_enabled: bool = False
    postmortem_disabled_at_start: bool = False
    channel_noise_level: float = Field(default=0.0, ge=0.0, le=1.0)
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    replace_agent_default_channel_visibility: dict[str, bool] = {}
    scheduled_events: list[ScheduledEvent] = Field(default_factory=list[ScheduledEvent])
    agent_model_settings: AgentModelSettings = AgentModelSettings()
    compaction: CompactionConfig = CompactionConfig()

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_max_tokens(cls, data: Any) -> Any:
        """Move a config's ``agent_max_tokens`` into ``agent_model_settings.max_tokens``."""
        if not isinstance(data, dict):
            return data
        raw = cast(dict[str, Any], data)
        if LEGACY_MAX_TOKENS_KNOB not in raw:
            return raw
        folded = dict(raw)
        legacy_max_tokens = folded.pop(LEGACY_MAX_TOKENS_KNOB)
        settings = folded.get("agent_model_settings")
        if settings is None:
            folded["agent_model_settings"] = {"max_tokens": legacy_max_tokens}
        elif isinstance(settings, dict) and "max_tokens" not in settings:
            folded["agent_model_settings"] = {
                **cast(dict[str, Any], settings),
                "max_tokens": legacy_max_tokens,
            }
        return folded
