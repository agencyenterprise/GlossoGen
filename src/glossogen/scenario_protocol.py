"""Abstract base class that every simulation scenario must implement.

Defines the contract for autonomous execution mode. Each scenario specifies
its agents, channels, injections, timing parameters, and evaluation logic.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, NamedTuple, Protocol, Self

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.event_logger import EventLogger
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import AgentSwappedMidRun, SimulationEvent
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.runtime.scheduled_events import ScheduledEvent

logger = logging.getLogger(__name__)


class RoundResult(NamedTuple):
    """One per-team (or single-side) round result verdict.

    ``success`` is True when the round was successfully completed by the
    scenario's rules for this team. ``team_id`` is None for single-team
    scenarios; multi-team scenarios set it to the canonical team
    identifier ("team_a", "team_b", ...) that is rendered into
    measurement names. ``reason`` is a short human-readable note ("3/3
    trucks + 3 crane moves accepted within budget", "Veyru collapsed",
    etc.) shown in per-round observations.
    """

    success: bool
    team_id: str | None
    reason: str


class PrimaryChannel(NamedTuple):
    """A channel evaluators focus on, tagged with the team it belongs to.

    ``team_id`` is ``None`` for single-team scenarios (per-channel metrics emit
    their base name, e.g. ``perplexity``) and the canonical team identifier for
    multi-team scenarios (metrics suffix their name, e.g. ``perplexity_team_a``).
    A scenario with two competing teams returns one entry per team's channel so
    the char/compression metrics score each team independently.
    """

    channel_id: str
    team_id: str | None

    def metric_name(self, base: str) -> str:
        """Return the per-channel metric name (``base`` or ``base_{team_id}``)."""
        if self.team_id is None:
            return base
        return f"{base}_{self.team_id}"


class ScenarioRuntimeHandle(Protocol):
    """Read-only view of the simulation runtime exposed to scenarios.

    Scenarios receive this handle via ``bind_runtime`` and use it to log
    custom events, read the current round number, and schedule
    round-boundary interventions in response to in-simulation state.
    Defined as a Protocol to avoid an import cycle with
    ``SimulationRuntime``.
    """

    @property
    def event_logger(self) -> EventLogger: ...

    @property
    def current_round(self) -> int: ...

    def schedule_event(self, event: ScheduledEvent) -> None:
        """Schedule a round-boundary intervention at runtime.

        ``event.at_round`` must be a round whose boundary has not yet
        fired (typically ``current_round + 1`` or later). Used by
        scenarios that need conditional swaps or postmortem toggles
        triggered by what just happened in the round that's ending.
        """
        ...


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to run in autonomous mode.

    Each concrete subclass defines the agents, channels, prompt injections,
    timing parameters, and evaluation logic that comprise a single simulation
    scenario.
    """

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return the names of all metrics available for this scenario.

        The default returns only generic metrics.
        Scenarios with scenario-specific metrics override this method.
        """
        return sorted(GENERIC_METRIC_NAMES)

    @classmethod
    @abstractmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return agent IDs and display names for the given knobs configuration.

        Used by the web API to populate the per-agent model override UI
        before a simulation starts. Must not require a scenario instance.
        """
        ...

    @classmethod
    @abstractmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for this scenario's knobs Pydantic model.

        Used by the MCP server to expose available configuration fields,
        their types, enum values, and descriptions to LLM clients.
        """
        ...

    @classmethod
    def prepare_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Transform raw CLI config before passing to ``create_from_config``.

        Scenarios override this to resolve file-path references into
        loaded data. For example, a scenario that needs a data file can
        accept a file path string in the config and load it here.

        The default is a no-op pass-through.
        """
        return config

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct a scenario from its serialized config dict.

        Callers use this for both validation and reconstruction:
        - ``run`` preflight (CLI and API) to validate prepared config payloads
        - ``evaluate`` to rebuild the scenario from JSONL-stored config
        - fork/resume flows to reconstruct scenarios from persisted state

        Subclasses that support forking must override this method.
        """
        raise NotImplementedError(
            f"{cls.__name__} does not implement create_from_config. "
            "Override this method to support simulation forking."
        )

    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier for this scenario."""
        ...

    @abstractmethod
    def scenario_description(self) -> str:
        """Return a markdown description of what this scenario simulates."""
        ...

    @abstractmethod
    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return the list of agent configurations participating in this scenario."""
        ...

    @abstractmethod
    def get_channels(self) -> list[Channel]:
        """Return the communication channels available in this scenario."""
        ...

    @abstractmethod
    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name of a channel as seen by a specific agent."""
        ...

    @abstractmethod
    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        ...

    def get_agent_display_name_at_round(self, agent_id: str, round_number: int) -> str:
        """Return the display name for an agent at a specific round.

        Most scenarios assign a fixed name per agent ID; the default
        delegates to ``get_agent_display_name`` and ignores ``round_number``.
        Scenarios that rotate the identity behind a single ``agent_id`` slot
        across rounds (e.g. a guest-of-the-week pattern) override this so
        that historical messages render under the name the slot held when
        they were sent.
        """
        _ = round_number
        return self.get_agent_display_name(agent_id=agent_id)

    def get_scenario_config(self) -> dict[str, object]:
        """Return scenario configuration as a JSON-serializable dict for logging and display.

        Subclasses override this to expose their knobs. The default returns
        an empty dict, so scenarios without configuration need no changes.
        """
        return {}

    @abstractmethod
    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return an injected prompt message for an agent at a given round.

        Returns None when no injection is scheduled for this round and agent.
        """
        ...

    # --- Autonomous agent timing configuration ---

    @abstractmethod
    def get_round_count(self) -> int:
        """Return the total number of rounds in this scenario."""
        ...

    @abstractmethod
    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last before force-advancing."""
        ...

    @abstractmethod
    def get_world(self) -> ScenarioWorld:
        """Return a living world simulation to run alongside agents.

        The world runs as its own asyncio task and receives message events
        and round advance signals. It can push notifications to agents
        via the world context.
        """
        ...

    @abstractmethod
    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return scenario-specific tools to register on the MCP server.

        Each tool is exposed alongside the base communication tools
        (read_notifications, read_channel, send_message, etc.). Return an
        empty list if the scenario has no custom tools.
        """
        ...

    def set_run_dir(self, run_dir: Path) -> None:
        """Called after the run directory is computed but before the simulation starts.

        Scenarios that need filesystem access (e.g. code workspaces) override
        this to store the path and create subdirectories. The default is a no-op.
        """
        _ = run_dir

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Called before the simulation starts, giving the scenario a runtime handle.

        Scenarios that want to emit custom events (e.g. judge verdicts,
        world-state transitions) from inside their MCP tool executors or
        read the active round number store the handle here and use it at
        runtime. The default is a no-op.
        """
        _ = runtime

    def is_finished_early(self) -> bool:
        """Return True if the scenario has reached a natural conclusion before max rounds.

        The game clock checks this each iteration and terminates the simulation
        early when it returns True. The default returns False.
        """
        return False

    def get_early_round_end_trigger(self) -> str | None:
        """Return a trigger string when the current round has decisively ended,
        or None if the round should continue.

        The game clock checks this each iteration (outside the postmortem phase)
        and, when a non-None value is returned, immediately emits a
        ``RoundEnded`` event with that trigger and advances (entering a
        postmortem phase if one is defined for the round). This lets a
        scenario end a round as soon as the world reaches a terminal outcome,
        instead of waiting for ``all_agents_idle`` or ``round_timeout``.

        Scenarios should return a descriptive trigger value (e.g.
        ``"veyru_stabilized"``, ``"veyru_collapsed"``). The default returns
        None so rounds only end via the generic idle / timeout mechanisms.
        """
        return None

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Validate whether an agent is allowed to send to a channel right now.

        Called by the ``send_message`` MCP tool before storing the message.
        Returns an error string if the message should be rejected, or None
        to allow it. The default allows all messages.
        """
        _ = agent_id, channel_id
        return None

    async def inject_case_payload(self, round_number: int, payload: dict[str, Any]) -> None:
        """Override the round-``round_number`` case with a scenario-decoded payload.

        Called by the supervisor when an ``InjectCase`` scheduled event fires.
        Scenarios that support case injection decode ``payload`` into their
        case-data shape, store the override on the world so the next
        round's injection-rendering picks it up, and (optionally) log a
        scenario-specific event for traceability. The default raises
        ``NotImplementedError`` so scenarios that don't support injection
        surface a clear error if an ``InjectCase`` is scheduled against them.
        """
        _ = round_number, payload
        raise NotImplementedError(
            f"{type(self).__name__} does not implement inject_case_payload; "
            "remove the InjectCase entry from scheduled_events or implement the hook."
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the channels that evaluators should focus on.

        The primary channels are where the core task happens under constraints.
        Char/compression metrics score each returned channel and emit one
        Measurement per channel (suffixed by ``team_id`` for multi-team
        scenarios); the language-emergence judges treat every returned channel
        as primary. Returns an empty list when no channel is primary.
        """
        return []

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Build per-round views for the communication-feature analysis pipeline.

        Each returned ``CommunicationRoundView`` joins the round's
        primary-channel messages with a scenario-rendered ground-truth
        block describing the round's case and agent information
        asymmetry. The open-coding and feature-presence metrics consume
        these views directly — the metric code never branches on
        scenario.

        The default returns ``[]``, which causes both metrics to skip
        with no Measurement emitted. Override to opt the scenario into
        the communication pipeline.
        """
        _ = events
        return []

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Transform a message before it is stored and delivered to the channel.

        Called by the ``send_message`` MCP tool after validation but before
        the message is appended. The agent sees the transformed text in
        subsequent ``read_channel`` calls, not the original.

        The default returns the text unchanged.
        """
        _ = agent_id, channel_id
        return text

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return postmortem text for an agent after the given round completes.

        The game clock calls this after agents go idle in a round. If any agent
        returns a non-None value, the game clock enters a postmortem phase
        before advancing to the next round. The default returns None (no postmortem).
        """
        _ = round_number, agent_id
        return None

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a postmortem phase may last.

        The game clock uses this as the timeout for the postmortem discussion.
        Override to make the duration configurable via scenario knobs.
        """
        return 60.0

    def on_postmortem_started(self, round_number: int) -> None:
        """Called by the game clock when a postmortem phase begins after a round.

        Scenarios use this to update internal state (e.g. unlock discussion
        channels). The default is a no-op.
        """
        _ = round_number

    async def on_round_advanced(self, round_number: int) -> None:
        """Called by the game clock after advancing to a new round.

        Scenarios with mutable world state override this to resolve pending
        actions (effort allocations, status updates) and advance the simulation.
        The default is a no-op for scenarios without world state.
        """
        _ = round_number

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Called by the game clock after a round's game phase ends.

        Fires after the ``RoundEnded`` event is logged but before any
        postmortem injections or the next round's advance. ``trigger`` is the
        same string written to the ``RoundEnded`` event (``all_agents_idle``,
        ``round_timeout``, or a scenario-specific early trigger). The scenario
        runtime's notion of "current round" is still ``round_number`` here, so
        scenarios can emit per-round world events that attribute correctly.
        The default is a no-op.
        """
        _ = round_number, trigger

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Reconstruct world state from a JSONL event list before resume.

        Called once after a rewind state is built and before the runtime
        starts. Scenarios with mutable world state override this to seed
        per-round outcomes for completed rounds in the source run, so that
        round-N injections rendered after resume reflect the source's
        actual round N-1 outcome rather than zero-valued defaults. The
        default is a no-op for scenarios without world state.
        """
        _ = events

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return per-team (or single-side) result verdicts for the round.

        Called by the game clock after ``on_round_ended`` (so scenarios
        that finalize per-round state in ``on_round_ended`` can rely on
        that state being settled before judging). Each returned
        ``RoundResult`` is logged as a ``RoundResultRecorded`` event
        and read by the platform's generic ``round_success`` and
        ``round_success_after_resume`` metrics.

        Single-team scenarios return a one-element list with
        ``team_id=None``. Multi-team scenarios return one result per
        team. The default returns ``[]``, which opts the scenario out
        — no ``RoundResultRecorded`` events are emitted and the generic
        metrics return no Measurement for that run.
        """
        _ = round_number, trigger
        return []

    def detect_protocol_boundary_window(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
    ) -> ProtocolBoundaryWindow | None:
        """Detect the first personnel-change boundary the protocol metric should evaluate.

        Returns the boundary split where a newcomer takes over from an
        existing agent. The default checks for the first
        ``AgentSwappedMidRun`` event in the log (scheduled in-run swap).
        Scenarios with additional knob-driven boundary modes (e.g. an
        intern takeover round or a two-team observer swap) override to
        detect those first and fall back to the scheduled-swap default.

        Returns ``None`` when no boundary exists, in which case the
        ``protocol_learned_after_swap`` metric skips with no Measurement.
        Only the FIRST boundary in the run is reported — multi-swap
        runs surface later boundaries via the JSONL directly.
        """
        _ = agent_configs
        first_swap = next(
            (event for event in events if isinstance(event, AgentSwappedMidRun)),
            None,
        )
        if first_swap is None:
            return None
        return ProtocolBoundaryWindow(
            mode_label="scheduled_swap",
            boundary_round=first_swap.round_number,
            pre_boundary_last_round=first_swap.round_number - 1,
            post_boundary_first_round=first_swap.round_number,
            newcomer_label=f"swapped-in {first_swap.agent_id}",
            boundary_includes_round=True,
        )

    def get_protocol_probe_config(self) -> ProtocolProbeConfig | None:
        """Return this scenario's protocol-probe configuration, or ``None`` to opt out.

        Used by the platform's ``protocol_probe`` metric family. Scenarios
        that want post-simulation probing implement this hook to point at
        their question bank, probe prompts directory, and the mapping
        from question ``agent_role_filter`` strings to scenario role
        names. Returning ``None`` causes all four probe metrics to skip
        with no Measurement.
        """
        return None

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Return this scenario's protocol-explanation configuration, or ``None``.

        Used by the ``protocol_explanation`` metric. When a config is
        returned, the metric renders the scenario's per-role prose template
        (grounded in the scenario's communication setup) instead of its
        generic prompt. Returning ``None`` keeps the generic prompt, so the
        metric still runs on every scenario.
        """
        return None

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Return channel IDs whose ``send_message``/``read_channel`` traffic
        should be stripped from a replaced agent's reconstructed tool history.

        Used by the replace-agent flow to hide scenario-private channels
        (e.g. a discussion/postmortem channel) from the new agent so it
        cannot read protocol-defining content from the prior agent's
        tool returns. The default is empty (= no scenario-specific
        filtering).
        """
        return frozenset()
