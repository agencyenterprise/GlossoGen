"""Abstract base class that every simulation scenario must implement.

Defines the contract for autonomous execution mode. Each scenario specifies
its agents, channels, injections, timing parameters, and evaluation logic.
"""

import importlib.resources
import logging
from abc import ABC, abstractmethod
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, Protocol, Self

import orjson
from pydantic_core import PydanticUndefined

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.metric_entry_points import external_metric_names
from glossogen.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.event_logger import EventLogger
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import AgentSwappedMidRun, SimulationEvent
from glossogen.models.model_consumer import ModelConsumer
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.base_knobs import BaseKnobs

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
    custom events and read the current round number. Defined as a Protocol
    to avoid an import cycle with ``SimulationRuntime``.
    """

    @property
    def event_logger(self) -> EventLogger: ...

    @property
    def current_round(self) -> int: ...


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to run in autonomous mode.

    Each concrete subclass defines the agents, channels, prompt injections,
    timing parameters, and evaluation logic that comprise a single simulation
    scenario.
    """

    _runtime: ScenarioRuntimeHandle | None = None
    # Populated by scenarios that rename agents or channels for display.
    # Empty here so the default lookups fall through to the raw id.
    _agent_display_names: dict[str, str] = {}
    _channel_display_names: dict[str, str] = {}
    # Channels carrying postmortem traffic, declared once here rather than
    # written out per scenario. Read by the replaced-agent history filter
    # below, and by the world it is handed to, which reports it as the
    # globally-disabled set once the debrief closes. Empty means the scenario
    # has no postmortem.
    postmortem_channel_ids: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, knobs: BaseKnobs) -> None:
        """Construct the scenario from its validated knobs.

        Declared here because ``create_from_config`` builds every scenario this
        way. Subclasses narrow ``knobs`` to their own model and assign the
        attributes they need; they do not call up to this.
        """
        _ = knobs

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return the names of all metrics available for this scenario.

        The default is every generic metric, plus any metric another installed
        distribution declares. External names are read from installed metadata
        rather than by importing the metric classes, because a metric module
        imports this contract and importing them back would close a cycle.
        Scenarios with scenario-specific metrics override this method.
        """
        return sorted(set(GENERIC_METRIC_NAMES) | set(external_metric_names()))

    @classmethod
    @abstractmethod
    def knobs_model(cls) -> type[BaseKnobs]:
        """Return this scenario's knobs Pydantic model class.

        The single source of truth for the scenario's configuration: the JSON
        Schema and per-field defaults both derive from it, so scenarios declare
        the model here rather than re-implementing schema/default accessors.
        """
        ...

    @classmethod
    @abstractmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return agent IDs and display names for the given knobs configuration.

        Used by the web API to populate the per-agent model override UI
        before a simulation starts. Must not require a scenario instance, and
        may receive a partial (or ``None``) knobs dict, so read role-determining
        flags via ``resolve_bool_knob`` so missing values fall back to the
        model's declared defaults.
        """
        ...

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for this scenario's knobs model.

        Used by the MCP server to expose available configuration fields, their
        types, enum values, and descriptions to LLM clients.
        """
        return cls.knobs_model().model_json_schema()

    @classmethod
    def scenario_package_files(cls) -> Traversable:
        """Return the package directory this scenario class lives in.

        Resolved from the class's own module rather than from a path computed
        under ``glossogen/scenarios``, so a scenario shipped in another
        distribution finds its own files.

        ``files`` takes the module as an anchor and answers with the directory
        holding it, so this works for a class in a ``scenario`` submodule without
        the caller counting dots. External scenarios cannot put the class in the
        package's own ``__init__``; the loader refuses that layout, because
        discovery has to find the package from the entry-point string without
        importing anything.
        """
        return importlib.resources.files(cls.__module__)

    @classmethod
    def knobs_preset_names(cls) -> list[str]:
        """Return the names of the knobs presets this scenario ships, without ``.json``.

        These are what the docs tell people to pass to ``--config``, what the
        frontend offers in its preset picker, and what the MCP ``list_scenarios``
        tool reports. The default reads ``knobs_*.json`` from the scenario's own
        package; a scenario that keeps presets elsewhere overrides this and
        ``load_knobs_preset`` together.
        """
        return sorted(
            entry.name.removesuffix(".json")
            for entry in cls.scenario_package_files().iterdir()
            if entry.name.startswith("knobs_") and entry.name.endswith(".json")
        )

    @classmethod
    def load_knobs_preset(cls, preset_name: str) -> dict[str, Any]:
        """Return the parsed contents of one knobs preset.

        Raises ``ValueError`` when the scenario ships no preset under that name,
        so a caller reporting a 404 does not have to know how presets are stored.

        The name is checked against the presets this scenario actually ships
        rather than being joined onto the package directory and tried. Callers
        pass it through from a request: the MCP ``get_knobs_preset`` tool takes an
        arbitrary string, and ``../<other scenario>/knobs_default`` would
        otherwise resolve and be read.
        """
        if preset_name not in cls.knobs_preset_names():
            raise ValueError(f"Knobs preset not found for {cls.__name__}: {preset_name!r}")
        return orjson.loads((cls.scenario_package_files() / f"{preset_name}.json").read_bytes())

    @classmethod
    def resolve_bool_knob(cls, knobs: dict[str, Any] | None, field_name: str) -> bool:
        """Resolve a boolean knob from a partial config dict.

        Reads ``field_name`` from ``knobs`` when present, otherwise falls back
        to the knobs model's declared default. When the field is required (no
        declared default), falls back to ``False``, the baseline layout shown
        before a run is configured. Lets ``get_agent_roles`` branch on
        role-determining flags without hardcoding a default that could drift
        from the model.
        """
        if knobs is not None and field_name in knobs:
            return bool(knobs[field_name])
        default = cls.knobs_model().model_fields[field_name].get_default()
        if default is PydanticUndefined:
            return False
        return bool(default)

    @classmethod
    def resolve_str_knob(cls, knobs: dict[str, Any] | None, field_name: str) -> str:
        """Resolve a string knob from a partial config dict.

        Same fallback order as :meth:`resolve_bool_knob`: the configured value,
        then the knobs model's declared default, then the empty string, which
        every caller reads as the knob not being configured.
        """
        if knobs is not None and field_name in knobs:
            return str(knobs[field_name])
        default = cls.knobs_model().model_fields[field_name].get_default()
        if default is PydanticUndefined:
            return ""
        return str(default)

    @classmethod
    def get_judge_models(cls, knobs: dict[str, Any] | None) -> tuple[ModelConsumer, ...]:
        """Return the models this scenario calls itself, beyond what its agents call.

        A scenario that resolves its rounds with an LLM names that model in its
        own knobs, under a provider that need not be the one its agents run.
        Declaring it here is what lets a launch check whether the environment can
        reach it, rather than the scenario finding out mid-run: the judge is
        built on first use, so a run whose agents authenticate starts and spends
        before the missing credential is reached.

        The default reads the ``judge_model`` / ``judge_provider`` pair, the
        convention every scenario here follows. A scenario calling more than one
        model of its own, or naming the knobs differently, overrides this. One
        that resolves its rounds without an LLM declares no such knobs and
        inherits the empty answer.
        """
        fields = cls.knobs_model().model_fields
        if "judge_model" not in fields or "judge_provider" not in fields:
            return ()
        model = cls.resolve_str_knob(knobs=knobs, field_name="judge_model")
        provider = cls.resolve_str_knob(knobs=knobs, field_name="judge_provider")
        if model == "" or provider == "":
            return ()
        return (ModelConsumer(name="round judge", model=model, provider=provider),)

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

        Validates through ``knobs_model``, so a scenario only declares its knobs
        class once. Override if construction needs more than the knobs.
        """
        return cls(knobs=cls.knobs_model().model_validate(config))

    @classmethod
    def name(cls) -> str:
        """Return the unique identifier for this scenario.

        Derived from the package directory, which the registry already keys on,
        so the two cannot disagree. Override only if a scenario needs an
        identifier that differs from its folder.

        A classmethod because this is what a run directory is named after, and
        the loader has to check it against the name a scenario was registered
        under before anything is constructed. Callers may still reach it through
        an instance.

        Read off the same directory :meth:`scenario_package_files` resolves, so the
        two cannot disagree about which package a scenario lives in. Counting dots
        in the module path instead would make that a second implementation to keep
        in step.
        """
        return cls.scenario_package_files().name

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

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name of a channel as seen by a specific agent.

        Looks the id up in ``_channel_display_names``, falling back to the id
        itself. Override when the name depends on which agent is asking.
        """
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent.

        Looks the id up in ``_agent_display_names``, falling back to the id.
        """
        return self._agent_display_names.get(agent_id, agent_id)

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

    @abstractmethod
    def get_knobs(self) -> BaseKnobs:
        """Return this scenario's validated knobs instance.

        The single source of truth for runtime configuration values: the
        platform reads timing and config off this, so scenarios expose their
        stored knobs here rather than re-implementing each getter. Overrides
        may narrow the return type to their concrete knobs model.
        """
        ...

    def get_scenario_config(self) -> dict[str, object]:
        """Return scenario configuration as a JSON-serializable dict for logging and display."""
        return self.get_knobs().model_dump()

    @abstractmethod
    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return an injected prompt message for an agent at a given round.

        Returns None when no injection is scheduled for this round and agent.
        """
        ...

    # --- Autonomous agent timing configuration ---

    def get_round_count(self) -> int:
        """Return the total number of rounds in this scenario."""
        return self.get_knobs().round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last before force-advancing."""
        return self.get_knobs().max_round_duration_seconds

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
        """Store the runtime handle. Called once before the simulation starts.

        Scenarios read the bound handle via the ``runtime`` property to emit
        custom events (judge verdicts, world-state transitions) from inside
        their MCP tool executors or to read the active round number.
        """
        self._runtime = runtime

    @property
    def runtime(self) -> ScenarioRuntimeHandle:
        """Return the bound runtime handle.

        Raises ``RuntimeError`` if accessed before ``bind_runtime``. The
        supervisor binds it before the simulation starts, so tool executors
        and round hooks can rely on it being present.
        """
        if self._runtime is None:
            raise RuntimeError(f"{type(self).__name__}: runtime accessed before bind_runtime")
        return self._runtime

    def is_finished_early(self) -> bool:
        """Return True if the scenario has reached a natural conclusion before max rounds.

        The game clock checks this each iteration and terminates the simulation
        early when it returns True. The default returns False.
        """
        return False

    def get_early_round_end_trigger(self) -> str | None:
        """Return a trigger string when the round has decisively ended, else None.

        A trigger ends the round; None lets it continue.

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

    @abstractmethod
    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the channels that evaluators should focus on.

        The primary channels are where the core task happens under constraints.
        Char/compression metrics score each returned channel and emit one
        Measurement per channel (suffixed by ``team_id`` for multi-team
        scenarios); the language-emergence judges treat every returned channel
        as primary. Return an empty list only when the scenario genuinely has
        no channel evaluators should score. That silently skips every
        primary-channel metric.
        """
        ...

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Build per-round views for the communication-feature analysis pipeline.

        Each returned ``CommunicationRoundView`` joins the round's
        primary-channel messages with a scenario-rendered ground-truth
        block describing the round's case and agent information
        asymmetry. The open-coding and feature-presence metrics consume
        these views directly, so the metric code never branches on
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

        Zero when the scenario has postmortem switched off, or when the world
        has closed it for the rest of the run. The game clock reads this once,
        at construction, so it reflects the configuration the run starts with.
        """
        knobs = self.get_knobs()
        if not knobs.postmortem_enabled:
            return 0.0
        if self.get_world().is_postmortem_disabled:
            return 0.0
        return knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Called by the game clock when a postmortem phase begins after a round.

        Opens the world's postmortem phase, which is what the scenario's
        message validation checks to decide whether the discussion channel
        accepts traffic yet.
        """
        _ = round_number
        self.get_world().enter_postmortem()

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

    @abstractmethod
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
        team. Return an empty list only when the scenario genuinely has
        no per-round success criterion, which emits no
        ``RoundResultRecorded`` events and the generic metrics produce no
        Measurement for the run.
        """
        ...

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
        Only the FIRST boundary in the run is reported. Multi-swap
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
        names. Returning ``None`` causes every probe metric to skip
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
        """Return channel IDs to strip from a replaced agent's tool history.

        Their ``send_message`` and ``read_channel`` traffic is removed from the
        reconstructed history.

        Used by the replace-agent flow to hide scenario-private channels
        from the new agent so it cannot read protocol-defining content from
        the prior agent's tool returns. Defaults to the scenario's
        ``postmortem_channel_ids``, which is where agents discuss the
        protocol out of band; a scenario that declares none blocks nothing.
        """
        return cls.postmortem_channel_ids
