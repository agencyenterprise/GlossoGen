"""Spot-the-intersection simulation scenario.

Each team has ``team_size`` viewers, each holding a private board of objects.
Exactly one object is on every board of a team; others are on some boards but
not all. The viewers talk on their team's link channel, or with ``messaging``
set to ``one_to_one`` one teammate at a time on direct channels, to find the
common object, and every member submits it with ``submit_object``. With
``link_medium`` set to ``canvas`` they send drawings with ``send_drawing``
instead of text, and receive their teammates' drawings as images. With two
teams on the same boards, the correct team charged the fewest characters (or
pixels, under the canvas medium) wins the round. After each round a discussion
phase lets viewers agree on conventions, under the rules ``postmortem_mode`` and
``postmortem_character_limit`` set (see :mod:`postmortem_modes`).

Each round's boards are generated and certified from their rendered lines before
the run starts (see :mod:`board_generation` and :mod:`board_certification`), so a
round with no common object or more than one, or whose answer a partial
comparison isolates, is never played; with ``near_misses`` on, neither is one
solvable without every board. Scoring is deterministic.
"""

import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from glossogen.engine import team_structure
from glossogen.engine.team_declaration import RoleSpec
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import DIRECT_CHANNEL_PREFIX, Channel, ChannelTemplateEntry
from glossogen.models.event import SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.mcp_responses import SendMessageResult, SendStatus
from glossogen.scenario_contract.channel_noise import apply_character_noise
from glossogen.scenario_contract.communication_round_view import CommunicationRoundView
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.scenario_contract.protocol_probe_config import ProtocolProbeConfig
from glossogen.scenario_contract.registration import scenario
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenario_contract.scenario_base import (
    PrimaryChannel,
    RoundResult,
    SendMessageExecutor,
)
from glossogen.scenario_contract.scenario_tool import ScenarioTool
from glossogen.scenario_contract.scenario_world import ScenarioWorld
from glossogen.scenarios.spot_the_intersection.board_generation import generate_rounds
from glossogen.scenarios.spot_the_intersection.board_model import column_letter
from glossogen.scenarios.spot_the_intersection.discussion_phase import (
    DiscussionPhase,
    DiscussionSendResult,
)
from glossogen.scenarios.spot_the_intersection.drawing_tool import DrawingSender
from glossogen.scenarios.spot_the_intersection.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.spot_the_intersection.evaluation.busiest_member_share_metric import (
    BusiestMemberShareMetric,
)
from glossogen.scenarios.spot_the_intersection.evaluation.message_routes_metric import (
    MessageRoutesMetric,
)
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionSubmissionRecorded,
    SpotTheIntersectionRoundStarted,
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
from glossogen.scenarios.spot_the_intersection.knobs import (
    MAX_TEAM_SIZE,
    SpotTheIntersectionKnobs,
)
from glossogen.scenarios.spot_the_intersection.link_medium import (
    TEXT_REFUSED_ON_CANVAS_LINK,
    LinkMedium,
    charge_unit,
    charge_unit_singular,
)
from glossogen.scenarios.spot_the_intersection.messaging import (
    DIRECT_MESSAGES_CLOSED_IN_DISCUSSION,
    LINK_CLOSED_IN_DISCUSSION,
    LINK_IS_NOTICES_ONLY,
    ONE_TO_ONE_SEND_DESCRIPTION,
    Messaging,
    direct_channel_refusal,
)
from glossogen.scenarios.spot_the_intersection.partner_channels import (
    PartnerChannel,
    declared_partner_channels,
    every_partner_channel_id,
    partner_channel_entries,
    partner_channels_of,
    partner_channels_of_teams,
)
from glossogen.scenarios.spot_the_intersection.postmortem_modes import (
    USE_A_PARTNER_CHANNEL,
    USE_THE_DISCUSSION_CHANNEL,
    PostmortemMode,
    author_index,
    not_the_author_refusal,
)
from glossogen.scenarios.spot_the_intersection.round_event_conversion import round_started_event
from glossogen.scenarios.spot_the_intersection.run_detail_extension import (
    SpotTheIntersectionRunDetailExtension,
)
from glossogen.scenarios.spot_the_intersection.seats import (
    seat_role_names_of,
    teammates_of,
    viewer_role_name,
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


def _is_round_channel(channel_id: str) -> bool:
    """Whether ``channel_id`` is a link or direct channel, where viewers talk during a round."""
    return channel_id in _LINK_CHANNELS or channel_id.startswith(DIRECT_CHANNEL_PREFIX)


def _closed_in_discussion(channel_id: str) -> str | None:
    """Why ``channel_id``, a link or direct channel, is shut in a discussion phase, or ``None``."""
    if channel_id in _LINK_CHANNELS:
        return LINK_CLOSED_IN_DISCUSSION
    if channel_id.startswith(DIRECT_CHANNEL_PREFIX):
        return DIRECT_MESSAGES_CLOSED_IN_DISCUSSION
    return None


@scenario(name="spot_the_intersection")
class SpotTheIntersectionScenario(SimulationScenario):
    """Teams of viewers find the one object on every board, in as few characters as they can."""

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        """Return the event classes this scenario logs, all defined in its ``events`` module."""
        return (
            SpotTheIntersectionRoundStarted,
            IntersectionSubmissionRecorded,
        )

    postmortem_channel_ids: ClassVar[frozenset[str]] = frozenset(
        {POSTMORTEM_CHANNEL_ID, POSTMORTEM_A_CHANNEL_ID, POSTMORTEM_B_CHANNEL_ID}
    ) | every_partner_channel_id(max_team_size=MAX_TEAM_SIZE)

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """Each round's boards and submissions, for the run page."""
        return SpotTheIntersectionRunDetailExtension()

    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """The metrics that split a team's count by member."""
        return (BusiestMemberShareMetric, MessageRoutesMetric)

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
        self._role_names = {
            role.agent_id: role.role_name for team in self._team_specs for role in team.roles
        }
        self._partner_channels: tuple[PartnerChannel, ...] = ()
        if (
            self._postmortem_initially_active
            and knobs.postmortem_mode == PostmortemMode.CHOSEN_PARTNER
        ):
            self._partner_channels = partner_channels_of_teams(teams=self._team_specs)
        self._discussion: DiscussionPhase | None = None
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
            team_characters=knobs.team_characters,
            link_medium=knobs.link_medium,
        )
        self._drawing_sender = DrawingSender(
            width=knobs.canvas_width,
            height=knobs.canvas_height,
            link_channel_ids=_LINK_CHANNELS,
            in_postmortem=lambda: self._world.in_postmortem,
            get_runtime=lambda: self.runtime,
            channel_for_recipient=self._channel_for_recipient,
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
                "one_to_one": self._knobs.messaging == Messaging.ONE_TO_ONE,
                "team_characters": self._knobs.team_characters.value,
                "round_count": self._knobs.round_count,
                "postmortem_mode": self._knobs.postmortem_mode.value,
                "postmortem_character_limit": self._knobs.postmortem_character_limit,
                **self._medium_variables(),
            },
        )

    def _medium_variables(self) -> dict[str, Any]:
        """The template variables that word a prompt for the run's link medium."""
        return {
            "canvas": self._knobs.link_medium == LinkMedium.CANVAS,
            "canvas_width": self._knobs.canvas_width,
            "canvas_height": self._knobs.canvas_height,
            "unit": charge_unit(medium=self._knobs.link_medium),
            "unit_singular": charge_unit_singular(medium=self._knobs.link_medium),
        }

    def _render_system_prompt(self, role: RoleSpec, channels: list[ChannelTemplateEntry]) -> str:
        """Render one viewer's system prompt over the channels it reaches and its teammates.

        Its pair channels, in a ``chosen_partner`` run, follow the channels the
        engine declared.
        """
        teammates = teammates_of(teams=self._team_specs, agent_id=role.agent_id)
        seat = self._world.seats[role.agent_id]
        return self._renderer.render(
            template_name=role.system_template,
            template_variables={
                "channels": [
                    *channels,
                    *partner_channel_entries(
                        pairs=self._partner_channels,
                        role_names=self._role_names,
                        agent_id=role.agent_id,
                    ),
                ],
                "teammates": teammates,
                "one_to_one": self._knobs.messaging == Messaging.ONE_TO_ONE,
                "team_characters": self._knobs.team_characters.value,
                "team_size": self._knobs.team_size,
                "grid_size": self._knobs.grid_size,
                "first_column": column_letter(column=0),
                "last_column": column_letter(column=self._knobs.grid_size - 1),
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "two_teams": self._knobs.two_teams,
                "channel_noise_level": self._knobs.channel_noise_level,
                "noise_replacement_mode": self._knobs.noise_replacement_mode.value,
                "postmortem_enabled": self._postmortem_initially_active,
                "postmortem_mode": self._knobs.postmortem_mode.value,
                "postmortem_character_limit": self._knobs.postmortem_character_limit,
                "seat_role_names": seat_role_names_of(
                    teams=self._team_specs, agent_id=role.agent_id
                ),
                "seat_index": seat.board_index,
                **self._medium_variables(),
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return one agent per seat, wired to the channels it reaches."""
        configs = team_structure.build_agent_configs(
            teams=self._team_specs,
            render_system_prompt=self._render_system_prompt,
            default_model=default_model,
            default_provider=default_provider,
            compaction=self._knobs.compaction,
        )
        return [
            config.model_copy(
                update={
                    "channel_ids": [
                        *config.channel_ids,
                        *(
                            pair.channel_id
                            for pair in partner_channels_of(
                                pairs=self._partner_channels, agent_id=config.agent_id
                            )
                        ),
                    ]
                }
            )
            for config in configs
        ]

    def get_channels(self) -> list[Channel]:
        """Return each team's link, then its debrief or pair channels when this run holds them."""
        return [
            *team_structure.channels(teams=self._team_specs),
            *declared_partner_channels(pairs=self._partner_channels, role_names=self._role_names),
        ]

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
            messaging=self._knobs.messaging,
            team_characters=self._knobs.team_characters,
            link_medium=self._knobs.link_medium,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the discussion-phase injection while a discussion phase runs."""
        if not self._knobs.postmortem_enabled or self._world.is_postmortem_disabled:
            return None
        seat = self._world.seat_of(agent_id=agent_id)
        if seat is None:
            return None
        author = author_index(
            mode=self._knobs.postmortem_mode,
            round_number=round_number,
            team_size=self._knobs.team_size,
        )
        author_role_name: str | None = None
        if author is not None:
            author_role_name = viewer_role_name(team_id=seat.team_id, index=author)
        return render_postmortem_injection(
            renderer=self._renderer,
            round_number=round_number,
            previous_outcome=self._world.previous_outcome(team_id=seat.team_id),
            team_characters=self._knobs.team_characters,
            link_medium=self._knobs.link_medium,
            postmortem_mode=self._knobs.postmortem_mode,
            postmortem_character_limit=self._knobs.postmortem_character_limit,
            author_role_name=author_role_name,
            is_author=author == seat.board_index,
        )

    def on_postmortem_started(self, round_number: int) -> None:
        """Open the discussion phase, with no partner chosen and no character sent."""
        super().on_postmortem_started(round_number=round_number)
        self._discussion = DiscussionPhase(
            round_number=round_number,
            character_limit=self._knobs.postmortem_character_limit,
            partner_channels=self._partner_channels,
            role_names=self._role_names,
        )

    def _discussion_phase(self) -> DiscussionPhase:
        """The discussion phase in progress; raises before the first one opens."""
        if self._discussion is None:
            raise RuntimeError("no discussion phase has opened in this run")
        return self._discussion

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
                    reason=outcome_reason(outcome=outcome, link_medium=self._knobs.link_medium),
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
        """Keep the discussion channels to their phase, and the link and direct channels out of it.

        With one-to-one messaging the link carries only the world's notices, so
        a viewer cannot post on it. In a phase one viewer writes, only that
        viewer posts on the discussion channel. A refusal on a channel the phase
        closes says where the viewer may post instead.
        """
        if channel_id in type(self).postmortem_channel_ids:
            return self._discussion_channel_refusal(agent_id=agent_id)
        if channel_id in _LINK_CHANNELS and self._knobs.messaging == Messaging.ONE_TO_ONE:
            return LINK_IS_NOTICES_ONLY
        closed = _closed_in_discussion(channel_id=channel_id)
        if closed is None or not self._world.in_postmortem:
            return None
        return f"{closed} {self._where_to_post_in_discussion(agent_id=agent_id)}"

    def _discussion_channel_refusal(self, agent_id: str) -> str | None:
        """Why ``agent_id`` may not post on a discussion channel now, or ``None``."""
        if self._world.is_postmortem_disabled:
            return "The discussion channel has been closed for the remainder of the simulation."
        if not self._world.in_postmortem:
            return (
                "The discussion channel is only available during the post-round "
                "discussion phase. Wait for the discussion phase to begin."
            )
        return self._not_the_author_refusal(agent_id=agent_id)

    def _where_to_post_in_discussion(self, agent_id: str) -> str:
        """Where ``agent_id`` may post in this discussion phase, for a refusal elsewhere.

        A viewer that is not this phase's author is told who is.
        """
        refusal = self._not_the_author_refusal(agent_id=agent_id)
        if refusal is not None:
            return refusal
        if self._knobs.postmortem_mode == PostmortemMode.CHOSEN_PARTNER:
            return USE_A_PARTNER_CHANNEL
        return USE_THE_DISCUSSION_CHANNEL

    def _not_the_author_refusal(self, agent_id: str) -> str | None:
        """Who writes this phase when it is not ``agent_id``, or ``None`` when it may post."""
        seat = self._world.seats[agent_id]
        author = author_index(
            mode=self._knobs.postmortem_mode,
            round_number=self._discussion_phase().round_number,
            team_size=self._knobs.team_size,
        )
        if author is None or author == seat.board_index:
            return None
        return not_the_author_refusal(
            author_role_name=viewer_role_name(team_id=seat.team_id, index=author)
        )

    def validate_direct_channel(self, agent_id: str, recipient_agent_ids: list[str]) -> str | None:
        """With one-to-one messaging, a viewer may address one teammate; otherwise no one."""
        if self._knobs.messaging != Messaging.ONE_TO_ONE:
            return "This run has no direct channels: post on your team's link."
        return direct_channel_refusal(
            seats=self._world.seats, agent_id=agent_id, recipient_agent_ids=recipient_agent_ids
        )

    def send_message_executor(self) -> SendMessageExecutor:
        """Post on a channel when broadcasting; name one teammate with ``to`` when one-to-one."""
        if self._knobs.messaging == Messaging.ONE_TO_ONE:
            return self.send_to_teammate
        return self.post_on_channel

    def send_message_description(self) -> str:
        """The ``send_message`` description matching the run's messaging."""
        if self._knobs.messaging == Messaging.ONE_TO_ONE:
            return ONE_TO_ONE_SEND_DESCRIPTION
        return super().send_message_description()

    async def post_on_channel(
        self, agent_id: str, channel_id: str, text: str, force: bool
    ) -> SendMessageResult:
        """Post ``text`` on ``channel_id``, under the discussion phase's rules while one runs."""
        return await self._publish(agent_id=agent_id, channel_id=channel_id, text=text, force=force)

    async def send_to_teammate(
        self, agent_id: str, to: str, text: str, force: bool
    ) -> SendMessageResult:
        """Post ``text`` to the teammate ``to`` on their direct channel.

        ``to`` may also name a channel ``agent_id`` belongs to, which is how a
        viewer posts in the discussion phase; ``validate_outgoing_message``
        refuses the link.
        """
        channel_id = await self._channel_for_recipient(agent_id, to)
        return await self._publish(agent_id=agent_id, channel_id=channel_id, text=text, force=force)

    async def _channel_for_recipient(self, agent_id: str, to: str) -> str:
        """The channel a one-to-one ``to`` reaches: one ``agent_id`` belongs to, or a direct one."""
        if self._is_declared_channel_of(agent_id=agent_id, channel_id=to):
            return to
        return await self.runtime.direct_channel_for(agent_id=agent_id, recipient_agent_ids=[to])

    async def _publish(
        self, agent_id: str, channel_id: str, text: str, force: bool
    ) -> SendMessageResult:
        """Publish one message; in a discussion phase, hold it to the phase's partner and limit.

        With a character limit, every send in the phase returns what the sender
        has left. Under the canvas medium, text on the link or a direct channel
        during a round is refused: those channels carry drawings.
        """
        if not self._world.in_postmortem:
            if self._knobs.link_medium == LinkMedium.CANVAS and _is_round_channel(
                channel_id=channel_id
            ):
                return SendMessageResult(
                    status=SendStatus.REJECTED,
                    detail=TEXT_REFUSED_ON_CANVAS_LINK,
                    new_messages=[],
                    token_count=0,
                    current_round=self.runtime.current_round,
                    message_id=None,
                )
            return await self.runtime.publish_message(
                agent_id=agent_id, channel_id=channel_id, text=text, force=force
            )
        phase = self._discussion_phase()
        result = await self._publish_in_discussion(
            phase=phase, agent_id=agent_id, channel_id=channel_id, text=text, force=force
        )
        if not phase.has_character_limit:
            return result
        return DiscussionSendResult(
            **dict(result),
            discussion_characters_left=phase.characters_left(agent_id=agent_id),
        )

    async def _publish_in_discussion(
        self, phase: DiscussionPhase, agent_id: str, channel_id: str, text: str, force: bool
    ) -> SendMessageResult:
        """Claim a send's partner and characters, publish it, and give them back if unsent.

        The scenario's own refusal is checked first, so a viewer told the link is
        closed, or that another viewer writes this phase, reads that reason
        rather than a limit it did not reach.
        """
        refusal = self.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id)
        if refusal is None:
            refusal = phase.refusal_for(
                agent_id=agent_id, channel_id=channel_id, characters=len(text)
            )
        if refusal is not None:
            return SendMessageResult(
                status=SendStatus.REJECTED,
                detail=refusal,
                new_messages=[],
                token_count=0,
                current_round=self.runtime.current_round,
                message_id=None,
            )
        claim = phase.claim(agent_id=agent_id, channel_id=channel_id, characters=len(text))
        sent = False
        try:
            result = await self.runtime.publish_message(
                agent_id=agent_id, channel_id=channel_id, text=text, force=force
            )
            sent = result.status == SendStatus.SENT
        finally:
            if not sent:
                phase.release(claim=claim)
        return result

    def _is_declared_channel_of(self, agent_id: str, channel_id: str) -> bool:
        """Whether ``channel_id`` is a link or discussion channel ``agent_id`` belongs to."""
        return any(
            channel.channel_id == channel_id and agent_id in channel.member_agent_ids
            for channel in self.get_channels()
        )

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character noise to messages on the link and direct channels."""
        _ = agent_id
        if not _is_round_channel(channel_id=channel_id):
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Each team's link with its direct channels, scored per team when two teams play."""
        channels: list[PrimaryChannel] = []
        for team in self._team_specs:
            team_id: str | None = team.team_id
            if team.team_id == TEAM_SOLO_ID:
                team_id = None
            channels.append(
                PrimaryChannel(
                    channel_id=team.task.channel_id,
                    team_id=team_id,
                    includes_direct_channels=True,
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
        """Opt into the protocol-probe metrics with one symmetric viewer role group.

        One-to-one runs are asked which teammate they would message first. A
        canvas run has none: the probe asks for the text a viewer would send.
        """
        if self._knobs.link_medium == LinkMedium.CANVAS:
            return None
        scenario_root = Path(__file__).resolve().parent
        template = "viewer_probe.jinja"
        if self._knobs.messaging == Messaging.ONE_TO_ONE:
            template = "viewer_probe_one_to_one.jinja"
        return ProtocolProbeConfig(
            questions_path=scenario_root / "protocol_probe_questions.json",
            prompts_dir=scenario_root / "prompts" / "probe",
            role_groups={_VIEWER_ROLE_GROUP: self._viewer_role_names()},
            role_templates={_VIEWER_ROLE_GROUP: template},
        )

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Tailor the protocol-explanation metric with the viewer describe template.

        One-to-one runs are asked how messages travelled between teammates, and
        canvas runs how their drawings encoded an object.
        """
        scenario_root = Path(__file__).resolve().parent
        template = "viewer_describe.jinja"
        if self._knobs.messaging == Messaging.ONE_TO_ONE:
            template = "viewer_describe_one_to_one.jinja"
        if self._knobs.link_medium == LinkMedium.CANVAS:
            template = "viewer_describe_canvas.jinja"
        return ProtocolExplanationConfig(
            prompts_dir=scenario_root / "prompts" / "describe",
            role_groups={_VIEWER_ROLE_GROUP: self._viewer_role_names()},
            role_templates={_VIEWER_ROLE_GROUP: template},
        )

    def get_world(self) -> ScenarioWorld:
        """Return the spot_the_intersection world."""
        return self._world

    def get_tools(self) -> list[ScenarioTool]:
        """Return the submit_object tool, and send_drawing under the canvas medium."""
        tools = build_tools(world=self._world, get_runtime=lambda: self._runtime)
        if self._knobs.link_medium == LinkMedium.CANVAS:
            tools.append(
                self._drawing_sender.tool(one_to_one=self._knobs.messaging == Messaging.ONE_TO_ONE)
            )
        return tools
