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

from pydantic import BaseModel, ConfigDict, Field

from glossogen.models.compaction_config import CompactionConfig
from glossogen.runtime.scheduled_events import ScheduledEvent
from glossogen.scenarios.channel_noise import NoiseReplacementMode


class AgentModelOverride(BaseModel):
    """Per-agent model/provider override configured in scenario knobs."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str | None = None


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

    ``agent_max_tokens`` is the per-cycle output token cap passed to the
    LLM (``ModelSettings.max_tokens``). Default is sized for thinking-capable
    models (Anthropic Opus, OpenAI o1/gpt-5 reasoning, Qwen3-Thinking,
    DeepSeek-R1) where the budget includes reasoning tokens. Self-hosted
    non-thinking deployments (Llama 3.3 Instruct, Qwen Instruct) typically
    emit <2K output tokens per cycle, so this can be lowered (e.g. 4096) in
    runs that hit ``vllm`` ``--max-model-len`` limits to reclaim input
    headroom.

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

    model_config = ConfigDict(extra="ignore")

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
    agent_max_tokens: int = 16384
    compaction: CompactionConfig = CompactionConfig()
