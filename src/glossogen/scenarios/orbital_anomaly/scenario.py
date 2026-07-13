"""Orbital anomaly simulation scenario.

A single crew member aboard a crippled spacecraft is talked through
cascading system malfunctions by two Mission Control flight controllers
over a budget-constrained comm loop. The astronaut sees the physical panel
(which unit tripped, the current switch/tie configuration) and is the only
agent that can operate controls; the telemetry officer reads the downlinked
data (the exact fault plus the required hold and corrective setting); the
systems engineer holds the procedure handbook and the per-round secret
configuration rotation that maps each fault to a procedure template. No
single pair can complete a procedure: the engineer's template needs the
unit/config from the crew and the hold/setting from the telemetry officer,
and only the crew can act.

Every character sent on the comm loop costs simulated seconds; an anomaly
is lost when total communication time exceeds the case's time budget.

Heavy logic lives in dedicated sibling modules: :mod:`orbital_anomaly_cases`
(fault signatures, the rotation cipher, case assembly), :mod:`world`
(budget tracking and cascade stages), :mod:`actuation_judge` (the free-text
action judge), :mod:`mcp_tools` (the ``actuate_panel`` tool),
:mod:`agent_factory` (agent/channel construction), and
:mod:`injection_rendering` (per-round and debrief prompts).
"""

import logging
import random
from pathlib import Path
from typing import Any, Self

from glossogen.llm.provider_factory import create_provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.orbital_anomaly.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from glossogen.scenarios.orbital_anomaly.events import (
    OrbitalAnomalyCaseStage,
    OrbitalAnomalyCaseStarted,
)
from glossogen.scenarios.orbital_anomaly.ids import (
    ASTRONAUT_ID,
    ASTRONAUT_ROLE,
    LINK_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SYSTEMS_ENGINEER_ID,
    SYSTEMS_ENGINEER_ROLE,
    TELEMETRY_OFFICER_ID,
    TELEMETRY_OFFICER_ROLE,
)
from glossogen.scenarios.orbital_anomaly.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from glossogen.scenarios.orbital_anomaly.knobs import OrbitalAnomalyKnobs
from glossogen.scenarios.orbital_anomaly.mcp_tools import build_mcp_tools
from glossogen.scenarios.orbital_anomaly.orbital_anomaly_cases import get_cases
from glossogen.scenarios.orbital_anomaly.world import OrbitalAnomalyWorld
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class OrbitalAnomalyScenario(SimulationScenario):
    """Three-agent crewed-spacecraft anomaly scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three agent roles (independent of knobs)."""
        _ = knobs
        return [
            AgentRole(agent_id=ASTRONAUT_ID, role_name=ASTRONAUT_ROLE),
            AgentRole(agent_id=TELEMETRY_OFFICER_ID, role_name=TELEMETRY_OFFICER_ROLE),
            AgentRole(agent_id=SYSTEMS_ENGINEER_ID, role_name=SYSTEMS_ENGINEER_ROLE),
        ]

    @classmethod
    def knobs_model(cls) -> type[OrbitalAnomalyKnobs]:
        """Return the knobs model class for this scenario."""
        return OrbitalAnomalyKnobs

    def get_knobs(self) -> OrbitalAnomalyKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = OrbitalAnomalyKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: OrbitalAnomalyKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            cipher_enabled=knobs.cipher_enabled,
            easy_round_numbers=knobs.easy_round_numbers,
            fault_count_values=knobs.fault_count_values,
            fault_count_weights=knobs.fault_count_weights,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names()
        self._channel_display_names: dict[str, str] = build_channel_display_names()
        self._world = OrbitalAnomalyWorld(
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
        return "orbital_anomaly"

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "postmortem_enabled": self._knobs.postmortem_enabled,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent crew."""
        return build_agents(
            knobs=self._knobs,
            postmortem_active=self._postmortem_active,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return the comm-loop channel plus the optional debrief channel."""
        return build_channels(
            postmortem_active=self._postmortem_active,
            channel_display_names=self._channel_display_names,
        )

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            world=self._world,
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the debrief injection when the debrief is open, None otherwise."""
        _ = agent_id
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        return render_postmortem_injection(
            round_number=round_number,
            world=self._world,
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured debrief duration, or 0 when disabled."""
        if not self._knobs.postmortem_enabled:
            return 0.0
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the debrief channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the single-team success verdict for the just-ended round."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        if outcome.stabilized:
            reason = "stabilized"
        else:
            reason = "anomaly not resolved"
        return [RoundResult(success=outcome.stabilized, team_id=None, reason=reason)]

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once the anomaly is fully resolved or the system is lost."""
        if self._world.current_case is None:
            return None
        if self._world.is_vehicle_stabilized():
            return "vehicle_stabilized"
        if not self._world.is_vehicle_alive():
            return "vehicle_lost"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit a terminal notification and record this round's outcome."""
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)

    async def on_round_advanced(self, round_number: int) -> None:
        """Reset per-round state, load the next case, and log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log an OrbitalAnomalyCaseStarted event carrying the full ground-truth case."""
        case = self._world.current_case
        if case is None:
            return
        await self.runtime.event_logger.log(
            event=OrbitalAnomalyCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                variant_index=case.variant_index,
                time_budget_seconds=case.time_budget_seconds,
                stages=[
                    OrbitalAnomalyCaseStage(
                        fault_name=stage.fault_name,
                        subsystem=stage.subsystem,
                        cockpit_alarm=stage.cockpit_alarm,
                        panel_observation=stage.panel_observation,
                        telemetry_readout=stage.telemetry_readout,
                        judge_expected_actions=stage.judge_expected_actions,
                    )
                    for stage in case.stages
                ],
            )
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block debrief messages outside the debrief phase and comm-loop messages during it."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if self._world.is_postmortem_disabled:
                return "The debrief channel is closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The debrief channel is only open during the post-anomaly debrief phase. "
                    "Wait for the debrief phase to begin."
                )
        if channel_id == LINK_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The comm loop is closed during the debrief phase. Use the debrief channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the comm loop."""
        _ = agent_id
        if channel_id != LINK_CHANNEL_ID:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the comm-loop channel where the communication budget applies."""
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

    def get_world(self) -> ScenarioWorld:
        """Return the orbital anomaly world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the actuate_panel tool."""
        return build_mcp_tools(
            world=self._world,
            judge_provider=self._judge_provider,
            get_runtime=lambda: self._runtime,
        )

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the debrief channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})
