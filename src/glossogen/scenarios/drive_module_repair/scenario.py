"""Drive module repair simulation scenario.

Three agents coordinate over one shared bay channel to service a drive
module each round: the field technician (inspects the diagnostic panel and is
the only agent that can replace components), the diagnostics engineer (holds
this round's fault-tree mapping symptoms to faulty components and their
access-depth order), and the spec engineer (holds this round's service-spec
table mapping each component to its tool, torque, and calibration). The
technician must fuse the engineer's ordered plan with the spec engineer's
per-component specs and perform each replacement in order.

The fault-tree and the service spec re-randomize each round, so the
technician can never self-diagnose or self-spec and must rely on both
advisors. The spec engineer depends on the diagnostics engineer (specs are
keyed to the chosen components), forming an A->B->C->A dependency chain that
is not a single expert->novice relay.

Each ``service_component`` action is free text scored by an LLM judge
against the current stage's expected (component, tool, torque, calibration).
Round success requires every component replaced correctly, in order, within
the communication budget.

Heavy logic lives in dedicated sibling modules: :mod:`agent_factory`
(agent/channel construction), :mod:`mcp_tools` (the service_component tool),
:mod:`replacement_judge` (the LLM judge), :mod:`injection_rendering`
(per-round and postmortem prompts), :mod:`drive_module_cases` (per-round case
generation), :mod:`world_state` (the outcome type), and
:mod:`case_event_conversion` (case -> event-log adapter).
"""

import logging
import random
from pathlib import Path
from typing import Any, Self

from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.llm.provider_factory import create_provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import SimulationEvent
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import (
    PrimaryChannel,
    RoundResult,
    ScenarioRuntimeHandle,
    SimulationScenario,
)
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.drive_module_repair.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from glossogen.scenarios.drive_module_repair.case_event_conversion import case_started_event
from glossogen.scenarios.drive_module_repair.drive_module_cases import get_cases
from glossogen.scenarios.drive_module_repair.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.drive_module_repair.ids import (
    BAY_CHANNEL_ID,
    DIAGNOSTICS_ENGINEER_ID,
    DIAGNOSTICS_ENGINEER_ROLE,
    FIELD_TECHNICIAN_ID,
    FIELD_TECHNICIAN_ROLE,
    POSTMORTEM_CHANNEL_ID,
    SPEC_ENGINEER_ID,
    SPEC_ENGINEER_ROLE,
)
from glossogen.scenarios.drive_module_repair.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from glossogen.scenarios.drive_module_repair.knobs import DriveModuleRepairKnobs
from glossogen.scenarios.drive_module_repair.mcp_tools import build_mcp_tools
from glossogen.scenarios.drive_module_repair.world import DriveModuleWorld
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _protocol_role_groups() -> dict[str, frozenset[str]]:
    """Map each role-filter string to the role names it covers (single-team, three roles)."""
    return {
        "field_technician": frozenset({FIELD_TECHNICIAN_ROLE}),
        "diagnostics_engineer": frozenset({DIAGNOSTICS_ENGINEER_ROLE}),
        "spec_engineer": frozenset({SPEC_ENGINEER_ROLE}),
    }


class DriveModuleRepairScenario(SimulationScenario):
    """Three-agent drive-module repair coordination scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three role identities (independent of knobs)."""
        _ = knobs
        return [
            AgentRole(agent_id=FIELD_TECHNICIAN_ID, role_name=FIELD_TECHNICIAN_ROLE),
            AgentRole(agent_id=DIAGNOSTICS_ENGINEER_ID, role_name=DIAGNOSTICS_ENGINEER_ROLE),
            AgentRole(agent_id=SPEC_ENGINEER_ID, role_name=SPEC_ENGINEER_ROLE),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for DriveModuleRepairKnobs."""
        return DriveModuleRepairKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = DriveModuleRepairKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: DriveModuleRepairKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_initially_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            easy_round_numbers=knobs.easy_round_numbers,
            module_count_values=knobs.module_count_values,
            module_count_weights=knobs.module_count_weights,
            replacements_count_values=knobs.replacements_count_values,
            replacements_count_weights=knobs.replacements_count_weights,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names()
        self._channel_display_names: dict[str, str] = build_channel_display_names()
        self._world = DriveModuleWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    def name(self) -> str:
        """Return the scenario identifier."""
        return "drive_module_repair"

    def get_scenario_config(self) -> dict[str, object]:
        """Return drive-module knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent team."""
        return build_agents(
            knobs=self._knobs,
            postmortem_initially_active=self._postmortem_initially_active,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return the bay channel plus the optional postmortem channel."""
        return build_channels(
            postmortem_initially_active=self._postmortem_initially_active,
            channel_display_names=self._channel_display_names,
        )

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so the service_component tool can emit verdict events."""
        self._runtime = runtime

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            case=self._cases[round_number - 1],
            previous_outcome=self._world.previous_outcome(),
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        _ = agent_id
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        return render_postmortem_injection(
            round_number=round_number,
            previous_outcome=self._world.previous_outcome(),
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration, or 0 when disabled."""
        if not self._knobs.postmortem_enabled:
            return 0.0
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the single-team success verdict from the resolved outcome."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        if outcome.round_succeeded:
            reason = "device repaired"
        else:
            reason = outcome.failure_reason
        return [RoundResult(success=outcome.round_succeeded, team_id=None, reason=reason)]

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once the device is repaired or the budget is exhausted."""
        if self._world.current_case is None:
            return None
        if self._world.is_device_repaired():
            return "device_repaired"
        if self._world.round_budget_exceeded:
            return "device_failed"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit the terminal notification and record this round's outcome."""
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, prepare the next case, log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a DriveModuleCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=case_started_event(round_number=round_number, case=case)
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Gate the postmortem channel to the discussion phase; close bay during it."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id == BAY_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The bay channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the bay channel."""
        _ = agent_id
        if channel_id != BAY_CHANNEL_ID:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the bay channel where the communication budget applies."""
        return [PrimaryChannel(channel_id=BAY_CHANNEL_ID, team_id=None)]

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join bay-channel messages with each round's per-fault ground truth."""
        return build_communication_rounds(events=events)

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Point the protocol_explanation metric at the per-role describe templates."""
        return ProtocolExplanationConfig(
            prompts_dir=PROMPTS_DIR / "describe",
            role_groups=_protocol_role_groups(),
            role_templates={
                "field_technician": "field_technician_describe.jinja",
                "diagnostics_engineer": "diagnostics_engineer_describe.jinja",
                "spec_engineer": "spec_engineer_describe.jinja",
            },
        )

    def get_protocol_probe_config(self) -> ProtocolProbeConfig | None:
        """Point the protocol-probe metric family at the question bank and probe prompts."""
        return ProtocolProbeConfig(
            questions_path=Path(__file__).resolve().parent / "protocol_probe_questions.json",
            prompts_dir=PROMPTS_DIR / "probe",
            role_groups=_protocol_role_groups(),
            role_templates={
                "field_technician": "field_technician_probe.jinja",
                "diagnostics_engineer": "diagnostics_engineer_probe.jinja",
                "spec_engineer": "spec_engineer_probe.jinja",
            },
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed the world's per-round outcomes from source events on resume / fork."""
        self._world.restore_outcomes_from_events(events=events)

    def get_world(self) -> ScenarioWorld:
        """Return the drive-module world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the service_component tool."""
        return build_mcp_tools(
            world=self._world,
            judge_provider=self._judge_provider,
            get_runtime=lambda: self._runtime,
        )

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the postmortem channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})
