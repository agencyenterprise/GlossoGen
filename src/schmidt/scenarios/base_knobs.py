"""Shared base models for scenario knobs."""

from pydantic import BaseModel, ConfigDict, Field

from schmidt.models.compaction_config import CompactionConfig
from schmidt.runtime.scheduled_events import ScheduledEvent


class AgentModelOverride(BaseModel):
    """Per-agent model/provider override configured in scenario knobs."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str | None = None


class BaseKnobs(BaseModel):
    """Base knobs shared by all scenarios.

    ``postmortem_duration_seconds`` defaults to 120 and is only meaningful
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

    ``round_time_budget_seconds`` is the canonical per-round communication
    budget: one character on the scenario's primary channel costs one
    simulated second, and the round fails when the running total exceeds
    the budget. ``None`` means the scenario has no per-round budget (e.g.
    Salon, whose pressure axis is the Inquisitor's guess count instead).

    ``compaction`` enables provider-native history compaction (off by
    default). When enabled, the runner attaches the provider's compaction
    capability so older messages are summarized once an agent's input
    tokens exceed ``compaction.token_threshold``.
    """

    model_config = ConfigDict(extra="ignore")

    max_round_duration_seconds: float
    model_overrides: dict[str, AgentModelOverride]
    postmortem_duration_seconds: float = 120.0
    replace_agent_default_channel_visibility: dict[str, bool] = {}
    scheduled_events: list[ScheduledEvent] = Field(default_factory=list[ScheduledEvent])
    agent_max_tokens: int = 16384
    round_time_budget_seconds: int | None
    compaction: CompactionConfig = CompactionConfig()
