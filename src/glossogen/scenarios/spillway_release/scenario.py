"""Spillway release simulation scenario.

Three agents coordinate over one shared ops channel to manage a reservoir
each round: the dam operator (sees only the current water level and controls
the spillway gates), civil defense (sees only the weather forecast and
inflow, and can evacuate downstream), and the park ranger (sees only the
downstream park schedule, and can close the park). The information split
forces communication every round: the operator cannot choose a correct gate
setting without civil defense's inflow, nor decide whether a release is safe
without the ranger's park schedule.

Round scoring is fully deterministic (see :mod:`world_state`): a round
succeeds only when the reservoir ends within its safe band, no release
reaches an occupied park, and neither a needless park closure nor an
unwarranted evacuation occurred — all within the communication budget.

Heavy logic lives in dedicated sibling modules: :mod:`agent_factory`
(agent/channel construction), :mod:`mcp_tools` (the four action tools),
:mod:`injection_rendering` (per-round and postmortem prompts),
:mod:`spillway_cases` (per-round case generation), :mod:`world_state` (the
``SpillwayOutcome`` type + the resolution rule), and
:mod:`case_event_conversion` (case -> event-log adapter).
"""

import logging
import random
from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.spillway_release.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from glossogen.scenarios.spillway_release.case_event_conversion import case_started_event
from glossogen.scenarios.spillway_release.events import SpillwayRoundResolved
from glossogen.scenarios.spillway_release.ids import (
    CIVIL_DEFENSE_ID,
    CIVIL_DEFENSE_ROLE,
    DAM_OPERATOR_ID,
    DAM_OPERATOR_ROLE,
    OPS_CHANNEL_ID,
    PARK_RANGER_ID,
    PARK_RANGER_ROLE,
    POSTMORTEM_CHANNEL_ID,
)
from glossogen.scenarios.spillway_release.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from glossogen.scenarios.spillway_release.knobs import SpillwayReleaseKnobs
from glossogen.scenarios.spillway_release.mcp_tools import build_mcp_tools
from glossogen.scenarios.spillway_release.spillway_cases import get_cases
from glossogen.scenarios.spillway_release.world import SpillwayWorld
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class SpillwayReleaseScenario(SimulationScenario):
    """Three-agent reservoir-release coordination scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three role identities (independent of knobs)."""
        _ = knobs
        return [
            AgentRole(agent_id=DAM_OPERATOR_ID, role_name=DAM_OPERATOR_ROLE),
            AgentRole(agent_id=CIVIL_DEFENSE_ID, role_name=CIVIL_DEFENSE_ROLE),
            AgentRole(agent_id=PARK_RANGER_ID, role_name=PARK_RANGER_ROLE),
        ]

    @classmethod
    def knobs_model(cls) -> type[SpillwayReleaseKnobs]:
        """Return the knobs model class for this scenario."""
        return SpillwayReleaseKnobs

    def get_knobs(self) -> SpillwayReleaseKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = SpillwayReleaseKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: SpillwayReleaseKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_initially_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            easy_round_numbers=knobs.easy_round_numbers,
            gate_count=knobs.gate_count,
            release_per_gate_per_hour=knobs.release_per_gate_per_hour,
            max_level=knobs.max_level,
            min_level=knobs.min_level,
            day_end_hours=knobs.day_end_hours,
            archetype_weights=knobs.archetype_weights,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names()
        self._channel_display_names: dict[str, str] = build_channel_display_names()
        self._world = SpillwayWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )

    def name(self) -> str:
        """Return the scenario identifier."""
        return "spillway_release"

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "gate_count": self._knobs.gate_count,
                "release_per_gate_per_hour": self._knobs.release_per_gate_per_hour,
                "max_level": self._knobs.max_level,
                "min_level": self._knobs.min_level,
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
        """Return the ops channel plus the optional postmortem channel."""
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
            reason = "dam safe and no one downstream harmed"
        else:
            reason = outcome.failure_reason
        return [RoundResult(success=outcome.round_succeeded, team_id=None, reason=reason)]

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit the terminal notification, resolve the round, and log the verdict."""
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)
        await self._emit_round_resolved_event(round_number=round_number)

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, prepare the next case, log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a SpillwayCaseStarted event carrying the full ground-truth case."""
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self.runtime.event_logger.log(
            event=case_started_event(round_number=round_number, case=case)
        )

    async def _emit_round_resolved_event(self, round_number: int) -> None:
        """Log a SpillwayRoundResolved event carrying the deterministic verdict."""
        outcome = self._world.previous_outcome()
        if outcome is None:
            return
        await self.runtime.event_logger.log(
            event=SpillwayRoundResolved(
                round_number=round_number,
                case_number=outcome.case_number,
                end_level=outcome.end_level,
                release_total=outcome.release_total,
                would_overlap=outcome.would_overlap,
                clearing_was_needed=outcome.clearing_was_needed,
                park_secured=outcome.park_secured,
                evacuated=outcome.evacuated,
                budget_exceeded=outcome.budget_exceeded,
                dam_ok=outcome.dam_ok,
                casualties=outcome.casualties,
                needless_closure=outcome.needless_closure,
                false_alarm=outcome.false_alarm,
                round_succeeded=outcome.round_succeeded,
                failure_reason=outcome.failure_reason,
            )
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Gate the postmortem channel to the discussion phase; close ops during it."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id == OPS_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The ops channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the ops channel."""
        _ = agent_id
        if channel_id != OPS_CHANNEL_ID:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the ops channel where the communication budget applies."""
        return [PrimaryChannel(channel_id=OPS_CHANNEL_ID, team_id=None)]

    def get_world(self) -> ScenarioWorld:
        """Return the spillway world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the read_gauge / open_gates / notify_park / evacuate tools."""
        return build_mcp_tools(
            world=self._world,
            get_runtime=lambda: self._runtime,
        )

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the postmortem channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})
