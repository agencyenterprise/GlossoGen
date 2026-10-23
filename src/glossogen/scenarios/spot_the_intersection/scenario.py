"""Spot-the-intersection simulation scenario.

Each team has ``team_size`` viewers, each holding a private board of objects.
Exactly one object is on every board of a team; others are on some boards but
not all. The viewers talk on their team's link channel to find the common
object, and every member submits it with ``submit_object``. With two teams on
the same boards, the correct team that sent the fewest characters wins the
round.

Each round's boards are generated and certified from their rendered lines before
the run starts (see :mod:`board_generation` and :mod:`board_certification`), so a
round with no common object or more than one, or whose answer a partial
comparison isolates, is never played; with ``near_misses`` on, neither is one
solvable without every board. Scoring is deterministic.
"""

import random
from pathlib import Path
from typing import Any, ClassVar

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import RoleSpec
from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.event import SimulationEvent
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.spot_the_intersection.board_generation import generate_rounds
from glossogen.scenarios.spot_the_intersection.board_model import column_letter
from glossogen.scenarios.spot_the_intersection.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.spot_the_intersection.ids import (
    ALL_TEAMS_DONE_TRIGGER,
    DESCRIPTION_TEMPLATE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_SOLO_ID,
)
from glossogen.scenarios.spot_the_intersection.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.scenarios.spot_the_intersection.round_event_conversion import round_started_event
from glossogen.scenarios.spot_the_intersection.run_detail_extension import (
    SpotTheIntersectionRunDetailExtension,
)
from glossogen.scenarios.spot_the_intersection.team_declaration import intersection_teams
from glossogen.scenarios.spot_the_intersection.tools import build_tools
from glossogen.scenarios.spot_the_intersection.world import SpotTheIntersectionWorld
from glossogen.scenarios.spot_the_intersection.world_state import (
    outcome_reason,
    simulated_opponent_for,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_LINK_CHANNELS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})
_VIEWER_ROLE_GROUP = "viewer"


class SpotTheIntersectionScenario(SimulationScenario):
    """Teams of viewers find the one object on every board, in as few characters as they can."""

    postmortem_channel_ids: ClassVar[frozenset[str]] = frozenset(
        {POSTMORTEM_CHANNEL_ID, POSTMORTEM_A_CHANNEL_ID, POSTMORTEM_B_CHANNEL_ID}
    )

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """Each round's boards and submissions, for the run page."""
        return SpotTheIntersectionRunDetailExtension()

    @classmethod
    def knobs_model(cls) -> type[SpotTheIntersectionKnobs]:
        """Return the knobs model class for this scenario."""
        return SpotTheIntersectionKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return one role per seat; with no knobs, the default preset's roster.

        ``knobs`` is validated through the knobs model, so a config that does not
        validate raises.
        """
        config = knobs
        if config is None:
            config = cls.load_knobs_preset(preset_name="knobs_default")
        teams = intersection_teams(knobs=cls.knobs_model().model_validate(config))
        return [
            AgentRole(agent_id=role.agent_id, role_name=role.role_name)
            for team in teams
            for role in team.roles
        ]

    def __init__(self, knobs: SpotTheIntersectionKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_initially_active = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._noise_rng = random.Random(knobs.seed)
        self._team_specs = intersection_teams(knobs=knobs)
        self._world = SpotTheIntersectionWorld(
            rounds=generate_rounds(
                seed=knobs.seed, round_count=knobs.round_count, settings=knobs.board_settings()
            ),
            team_specs=self._team_specs,
            postmortem_channel_ids=type(self).postmortem_channel_ids,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
            competitive=knobs.two_teams,
            simulated_opponent=simulated_opponent_for(
                seed=knobs.seed, share=knobs.simulated_opponent_ratio
            ),
            round_time_budget_seconds=knobs.round_time_budget_seconds,
        )

    def get_knobs(self) -> SpotTheIntersectionKnobs:
        """Return this scenario's validated knobs."""
        return self._knobs

    def scenario_description(self) -> str:
        """Return a description reflecting the active knobs."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "team_size": self._knobs.team_size,
                "grid_size": self._knobs.grid_size,
                "two_teams": self._knobs.two_teams,
                "simulated_opponent_ratio": self._knobs.simulated_opponent_ratio,
                "round_count": self._knobs.round_count,
            },
        )

    def _render_system_prompt(self, role: RoleSpec, channels: list[ChannelTemplateEntry]) -> str:
        """Render one viewer's system prompt over the channels it reaches."""
        return self._renderer.render(
            template_name=role.system_template,
            template_variables={
                "channels": channels,
                "team_size": self._knobs.team_size,
                "grid_size": self._knobs.grid_size,
                "first_column": column_letter(column=0),
                "last_column": column_letter(column=self._knobs.grid_size - 1),
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "two_teams": self._knobs.two_teams,
                "channel_noise_level": self._knobs.channel_noise_level,
                "noise_replacement_mode": self._knobs.noise_replacement_mode.value,
                "postmortem_enabled": self._postmortem_initially_active,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return one agent per seat, wired to the channels it reaches."""
        return team_structure.build_agent_configs(
            teams=self._team_specs,
            render_system_prompt=self._render_system_prompt,
            default_model=default_model,
            default_provider=default_provider,
            compaction=self._knobs.compaction,
        )

    def get_channels(self) -> list[Channel]:
        """Return each team's link, then its debrief when this run holds one."""
        return team_structure.channels(teams=self._team_specs)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return one viewer's round-start injection: its board and last result."""
        seat = self._world.seat_of(agent_id=agent_id)
        if seat is None:
            return None
        round_boards = self._world.round_boards(round_number=round_number)
        return render_round_injection(
            renderer=self._renderer,
            round_number=round_number,
            board_lines=round_boards.board_lines[seat.board_index],
            previous_outcome=self._world.previous_outcome(team_id=seat.team_id),
            round_time_budget_seconds=self._knobs.round_time_budget_seconds,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the discussion-phase injection while a discussion phase runs."""
        if not self._knobs.postmortem_enabled or self._world.is_postmortem_disabled:
            return None
        seat = self._world.seat_of(agent_id=agent_id)
        if seat is None:
            return None
        return render_postmortem_injection(
            renderer=self._renderer,
            round_number=round_number,
            previous_outcome=self._world.previous_outcome(team_id=seat.team_id),
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed every team's outcomes, and the round the source stopped in, on resume."""
        self._world.restore_rounds_from_events(events=events)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return each team's verdict: every member submitted the answer."""
        _ = trigger
        self._world.mark_round_outcome(round_number=round_number)
        results: list[RoundResult] = []
        for team_id in self._world.team_ids:
            outcome = self._world.outcome_for(team_id=team_id, round_number=round_number)
            if outcome is None:
                continue
            result_team_id: str | None = team_id
            if team_id == TEAM_SOLO_ID:
                result_team_id = None
            results.append(
                RoundResult(
                    success=outcome.correct,
                    team_id=result_team_id,
                    reason=outcome_reason(outcome=outcome),
                )
            )
        return results

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once every team has locked or spent its budget."""
        if self._world.current_round_boards is None:
            return None
        if self._world.all_teams_done():
            return ALL_TEAMS_DONE_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Score the round and tell each team its result."""
        _ = trigger
        self._world.mark_round_outcome(round_number=round_number)
        await self._world.emit_round_terminal_notification()

    async def on_round_advanced(self, round_number: int) -> None:
        """Load the round's boards and record them in the event log.

        A resumed run that reopens a round whose start its log already holds,
        whether it stopped during the round or during its discussion phase, does
        not record the start a second time.
        """
        start_recorded = self._world.round_start_recorded(round_number=round_number)
        self._world.finalize_round_sync(round_number=round_number)
        if start_recorded:
            return
        await self.runtime.event_logger.log(
            event=round_started_event(
                round_boards=self._world.round_boards(round_number=round_number),
                round_time_budget_seconds=self._knobs.round_time_budget_seconds,
            )
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Keep the discussion channel to its phase, and the link out of it."""
        _ = agent_id
        if channel_id in type(self).postmortem_channel_ids:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id in _LINK_CHANNELS and self._world.in_postmortem:
            return (
                "The link channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character noise to messages on the link channels."""
        _ = agent_id
        if channel_id not in _LINK_CHANNELS:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Each team's link, scored per team when two teams play."""
        channels: list[PrimaryChannel] = []
        for team in self._team_specs:
            team_id: str | None = team.team_id
            if team.team_id == TEAM_SOLO_ID:
                team_id = None
            channels.append(
                PrimaryChannel(
                    channel_id=team.task.channel_id,
                    team_id=team_id,
                    includes_direct_channels=False,
                )
            )
        return channels

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join link messages with each round's boards and answer."""
        return build_communication_rounds(events=events)

    def _viewer_role_names(self) -> frozenset[str]:
        """Every seat's role name in this configuration."""
        return frozenset(role.role_name for team in self._team_specs for role in team.roles)

    def get_protocol_probe_config(self) -> ProtocolProbeConfig | None:
        """Opt into the protocol-probe metrics with one symmetric viewer role group."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolProbeConfig(
            questions_path=scenario_root / "protocol_probe_questions.json",
            prompts_dir=scenario_root / "prompts" / "probe",
            role_groups={_VIEWER_ROLE_GROUP: self._viewer_role_names()},
            role_templates={_VIEWER_ROLE_GROUP: "viewer_probe.jinja"},
        )

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Tailor the protocol-explanation metric with the viewer describe template."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolExplanationConfig(
            prompts_dir=scenario_root / "prompts" / "describe",
            role_groups={_VIEWER_ROLE_GROUP: self._viewer_role_names()},
            role_templates={_VIEWER_ROLE_GROUP: "viewer_describe.jinja"},
        )

    def get_world(self) -> ScenarioWorld:
        """Return the spot_the_intersection world."""
        return self._world

    def get_tools(self) -> list[ScenarioTool]:
        """Return the submit_object tool."""
        return build_tools(world=self._world, get_runtime=lambda: self._runtime)
