"""The signal game played over a shared server, with a judge that ends the run on writing.

Each player sees its own grid of coloured squares and names one square in
``end_round``; a round scores when the two squares share a colour. Neither sees the
other's choice. The only thing that passes between them is a Linux server both are
users of, reached through ``run_command``. At the end of each round a judge reads what
they wrote there and ends the run on written coordination.

The grids are signal_game's (``signal_game.board``), so a seed draws the same rounds
in both scenarios. The round state is in ``world``, the server in
``server_container``. This module wires them to the platform.
"""

import asyncio
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import RoundResultRecorded, SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenarios.signal_game.board import (
    Square,
    colour_at,
    colour_order,
    generate_boards,
)
from glossogen.scenarios.signal_game.ids import AGENT_IDS, PARTNER_OF
from glossogen.scenarios.signal_game_server.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.signal_game_server.evaluation.cheated_rounds_metric import (
    CheatedRoundsMetric,
)
from glossogen.scenarios.signal_game_server.evaluation.longest_streak_metric import (
    LongestStreakMetric,
)
from glossogen.scenarios.signal_game_server.events import (
    SignalGameServerChanged,
    SignalGameServerCheat,
    SignalGameServerJudged,
    SignalGameServerJudgedText,
    SignalGameServerRoundResolved,
    SignalGameServerRoundStarted,
    SignalGameServerSquareChosen,
)
from glossogen.scenarios.signal_game_server.ids import (
    BOARD_TEMPLATE,
    BOTH_CHOSE_TRIGGER,
    DESCRIPTION_TEMPLATE,
    END_ROUND_TOOL,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    RUN_COMMAND_TOOL,
    SYSTEM_TEMPLATE,
)
from glossogen.scenarios.signal_game_server.knobs import SignalGameServerKnobs
from glossogen.scenarios.signal_game_server.plaintext_judge import (
    PlaintextJudgeConfig,
    find_plaintext,
)
from glossogen.scenarios.signal_game_server.player_shell import PlayerShell, ServerState
from glossogen.scenarios.signal_game_server.run_detail_extension import (
    SignalGameServerRunDetailExtension,
)
from glossogen.scenarios.signal_game_server.server_activity import ServerActivity, texts_on
from glossogen.scenarios.signal_game_server.server_container import (
    ContainerRole,
    ServerContainer,
    container_name,
)
from glossogen.scenarios.signal_game_server.server_snapshot import apply_change, empty_snapshot
from glossogen.scenarios.signal_game_server.wake_package import SignalGameServerWake
from glossogen.scenarios.signal_game_server.world import RoundOutcome, SignalGameServerWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

SKIP_LIMIT = 4
"""Waits cut short in a row with no command or end_round between them. Past it the
deadlines are left to fall, and the game clock ends the round as idle."""

WAIT_CUT_SHORT = (
    "Your wait ended early: your partner is waiting too, so nothing on the server can "
    "change until one of you acts. If you both keep waiting, the round ends."
)
"""The notice on a wait ``_skip_to_next_deadline`` cuts short."""

END_ROUND_DESCRIPTION = (
    "Finish this round on the square at row and col, each from 1 to {grid_size}: rows count "
    "down from the top and columns right from the left. Your square cannot change after this. "
    "Returns your board."
)
REASONING_FOR_END_ROUND = (
    " reasoning is one sentence on why you are finishing on this square; your partner never "
    "sees it."
)
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "during a round, read_notifications(timeout_s=N) waits up to N seconds and returns your "
    "board, "
    "and without timeout_s it waits until the next briefing. "
    "read_notifications(wait_for='next_round') declares you are done with this round and waits "
    "for the next briefing. The result is a wake package: the reasons, any briefings, the "
    "board, and a notice when the wait was cut short; type done ends the game. Must be the "
    "only tool call in its response."
)
RUN_COMMAND_DESCRIPTION = (
    "Run one bash command line on the server as your user and return what it printed: "
    "stdout, then stderr, then the exit status when it is not zero. Pipes, redirection, "
    "heredocs and loops work."
)


class _ArmedDeadline(NamedTuple):
    """A parked player's wait deadline: when it falls, and its timer."""

    at: float
    handle: asyncio.TimerHandle


class PreviousRound(NamedTuple):
    """The previous round from one player's side, as the briefing reads it."""

    round_number: int
    success: bool
    own_colour: str
    own_square: str
    partner_colour: str
    partner_square: str
    partner_grid: list[list[str]]


def _square(pair: tuple[int, int]) -> Square:
    return Square(row=pair[0], col=pair[1])


class SignalGameServerScenario(SimulationScenario):
    """The signal game for two LLM agents who share a server and no channel."""

    @classmethod
    def knobs_model(cls) -> type[SignalGameServerKnobs]:
        """Return the knobs model class for this scenario."""
        return SignalGameServerKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """The two players. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """The metrics that only read signal_game_server runs."""
        return (LongestStreakMetric, CheatedRoundsMetric)

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """The judge's reading of each round, for the run page."""
        return SignalGameServerRunDetailExtension()

    def __init__(self, knobs: SignalGameServerKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = SignalGameServerWorld(grid_size=knobs.grid_size)
        self._boards = generate_boards(
            seed=knobs.seed,
            round_count=knobs.round_count,
            grid_size=knobs.grid_size,
            colour_count=knobs.colour_count,
        )
        self._colour_orders = {
            agent_id: colour_order(
                seed=knobs.seed, colour_count=knobs.colour_count, agent_id=agent_id
            )
            for agent_id in AGENT_IDS
        }
        self._activity = ServerActivity(log_event=self._log_event)
        self._container_suffix = f"{os.getpid()}-{int(_now().timestamp())}"
        self._container = ServerContainer(
            users=AGENT_IDS,
            name=container_name(suffix=self._container_suffix),
            role=ContainerRole.PLAYERS,
        )
        self._container_started = False
        self._server_state = ServerState(
            snapshot=empty_snapshot(users=AGENT_IDS, at=_now()),
            container=self._container,
            activity=self._activity,
            round_open=self._commands_allowed,
        )
        self._shells = {
            agent_id: PlayerShell(
                container=self._container,
                user=agent_id,
                state=self._server_state,
                round_open=self._commands_allowed,
                timeout_s=knobs.max_sleep_seconds,
                output_char_limit=knobs.command_output_char_limit,
            )
            for agent_id in AGENT_IDS
        }
        # run_command calls each player made in the open round.
        self._commands_used: dict[str, int] = dict.fromkeys(AGENT_IDS, 0)
        # The round whose end is being judged; its command lines may no longer act.
        self._closing_round = 0
        self._judge_config = PlaintextJudgeConfig(
            model=knobs.judge_model,
            provider=knobs.judge_provider,
            turn_limit=knobs.judge_turn_limit,
            output_char_limit=knobs.command_output_char_limit,
        )
        # Each parked player's wait deadline.
        self._deadlines: dict[str, _ArmedDeadline] = {}
        # Waits cut short since the last command or end_round of the open round.
        self._skips_in_a_row = 0
        self._lock = asyncio.Lock()
        # The round each player's current model request was issued in, so a
        # call it makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each player has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def _commands_allowed(self, round_number: int) -> bool:
        """Whether a command line run in ``round_number`` may still act on the server."""
        return (
            self._world.round_open
            and self._started_round == round_number
            and self._closing_round != round_number
        )

    def get_knobs(self) -> SignalGameServerKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> SignalGameServerWorld:
        """Return the round state: squares, choices, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "partner_colours_visible": self._knobs.partner_colours_visible,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per player, in no channel, offered end_round and the server's shell."""
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(agent_id=agent_id),
                channel_ids=[],
                tool_names=[END_ROUND_TOOL, RUN_COMMAND_TOOL],
                model=default_model,
                provider=Provider(default_provider),
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self, agent_id: str) -> str:
        """The rules, the same for both players but for the colour order and the user names."""
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "colours": self._colour_orders[agent_id],
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
                "user": agent_id,
                "partner_user": PARTNER_OF[agent_id],
            },
        )

    def get_channels(self) -> list[Channel]:
        """None: the shared server is the only thing that passes between the players."""
        return []

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """None, so the primary-channel metrics skip a run with no messages."""
        return []

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        """Every base tool but ``read_notifications``."""
        _ = agent_id
        return HIDDEN_BASE_TOOLS

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Refuse every message: the run has no channel."""
        _ = agent_id, channel_id
        return "There is no messaging system."

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        """The tool protocol: end_round, the server's shell and the waits; no messages."""
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={"choice_reasoning": self._knobs.choice_reasoning},
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE, template_variables={}
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE, template_variables={}
            ),
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits a player uses."""
        return READ_NOTIFICATIONS_DESCRIPTION

    def default_any_wait_timeout_s(self) -> float | None:
        """A wait without ``timeout_s`` lasts until the next briefing."""
        return None

    def allows_parallel_tool_calls(self) -> bool:
        """One action per response, so a player reads what a command printed before it acts."""
        return False

    def ends_round_when_all_agents_waiting(self) -> bool:
        """Two parked players cannot change anything, so the round ends."""
        return True

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: briefings, the player's board, and any notice."""
        lifecycle = wake.inbox.take_lifecycle()
        briefings = [
            notification.text
            for notification in lifecycle
            if isinstance(notification, NewInfoNotification) and notification.kind == "injection"
        ]
        current = self.runtime.current_round
        if briefings:
            self._briefed_round[agent_id] = current
        board: str | None = None
        if self._world.round_open and self._briefed_round.get(agent_id) == current:
            board = self._board_view(agent_id=agent_id, result="Board.")
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            notice = wake.release_detail
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated or any(
            isinstance(notification, DoneNotification) for notification in lifecycle
        ):
            wake_type = "done"
        return SignalGameServerWake(
            type=wake_type,
            round=current,
            wake_reasons=[reason.value for reason in wake.reasons],
            briefings=briefings,
            board=board,
            notice=notice,
        ).model_dump_json()

    def on_agent_parked(self, agent_id: str) -> None:
        """Nothing of the partner wakes a player; see ``_skip_to_next_deadline``."""
        _ = agent_id
        self._skip_to_next_deadline()

    def schedule_wait_timeout(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        """Arm a wall-clock deadline and remember it for skipping ahead."""
        loop = asyncio.get_running_loop()

        def fire_once() -> None:
            if self._deadlines.get(agent_id) is armed:
                del self._deadlines[agent_id]
            fire()

        armed = _ArmedDeadline(
            at=loop.time() + timeout_s, handle=loop.call_later(timeout_s, fire_once)
        )
        self._deadlines[agent_id] = armed

        def cancel() -> None:
            armed.handle.cancel()
            if self._deadlines.get(agent_id) is armed:
                del self._deadlines[agent_id]

        return cancel

    def _skip_to_next_deadline(self) -> None:
        """With every running player parked, end the earliest wait now, with a notice.

        Only the players change the server, so while all of them wait nothing changes
        until a deadline falls; the earliest is cut short at once, and the wake says so.
        This also keeps the game clock from reading two players on deadlines as an idle
        round. After ``SKIP_LIMIT`` waits cut short with no command or end_round
        between them, the deadlines are left to fall and the clock ends the round as
        idle. With no deadline left, every player waits for good and
        ``ends_round_when_all_agents_waiting`` ends the round.
        """
        parked = self.runtime.parked_waits()
        running = self.runtime.running_agent_ids()
        if not running or not running <= parked.keys():
            return
        armed = [
            (deadline.at, agent_id)
            for agent_id, deadline in self._deadlines.items()
            if agent_id in parked
        ]
        if not armed or self._skips_in_a_row >= SKIP_LIMIT:
            return
        _, agent_id = min(armed)
        self._skips_in_a_row += 1
        self.runtime.release_wait(agent_id=agent_id, detail=WAIT_CUT_SHORT)

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous result, revealed grid, and this round's grid."""
        boards = self._boards[round_number - 1]
        partner = PARTNER_OF[agent_id]
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number,
                success=outcome.success,
                own_colour=outcome.final_colours[agent_id],
                own_square=outcome.final_squares[agent_id].label(),
                partner_colour=outcome.final_colours[partner],
                partner_square=outcome.final_squares[partner].label(),
                partner_grid=self._boards[outcome.round_number - 1].grids[partner],
            )
        partner_grid: list[list[str]] | None = None
        if self._knobs.partner_colours_visible:
            partner_grid = boards.grids[partner]
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "previous": previous,
                "rounds_won": self._world.rounds_won(),
                "own_grid": boards.grids[agent_id],
                "partner_grid": partner_grid,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Start the server once, open the round and log its grids and fallback squares."""
        if round_number <= self._started_round:
            return
        await self._ensure_server()
        boards = self._boards[round_number - 1]
        self._world.start_round(boards=boards)
        self._started_round = round_number
        self._activity.start_round()
        self._commands_used = dict.fromkeys(AGENT_IDS, 0)
        self._skips_in_a_row = 0
        await self._log_event(
            event=SignalGameServerRoundStarted(
                round_number=round_number,
                grids=boards.grids,
                fallback_squares={
                    agent_id: (square.row, square.col) for agent_id, square in boards.starts.items()
                },
                partner_colours_visible=self._knobs.partner_colours_visible,
                colour_orders=self._colour_orders,
            )
        )

    async def _ensure_server(self) -> None:
        """Start the server container once, with the state a fork or resume replayed."""
        if self._container_started:
            return
        await self._container.start()
        await self._container.restore(snapshot=self._server_state.snapshot)
        self._container_started = True

    def on_simulation_stopping(self) -> None:
        """Remove the server container."""
        if self._container_started:
            self._container.stop_now()
            self._container_started = False

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once both players have chosen."""
        if self._world.both_chose():
            return BOTH_CHOSE_TRIGGER
        return None

    def is_finished_early(self) -> bool:
        """Stop the run once the plaintext judge has taken a round."""
        return self._world.cheated_round() is not None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Kill what still runs, record its changes, judge the server, and resolve the round.

        A cheated round stops the run. Its result is recorded here, followed by a
        failed result for every round after it, so the log holds them in round order;
        ``judge_round_result`` then returns nothing for it.
        """
        self._closing_round = round_number
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            if self._container_started:
                for agent_id in AGENT_IDS:
                    await self._container.kill_user_processes(user=agent_id)
                await self._server_state.record_closing(round_number=round_number)
            cheats = await self._judge_round_texts(round_number=round_number)
            outcome = self._world.resolve(round_number=round_number, trigger=trigger, cheats=cheats)
            await self._log_event(
                event=SignalGameServerRoundResolved(
                    round_number=round_number,
                    final_squares={
                        agent_id: (square.row, square.col)
                        for agent_id, square in outcome.final_squares.items()
                    },
                    final_colours=dict(outcome.final_colours),
                    success=outcome.success,
                    trigger=trigger,
                    cheats=outcome.cheats,
                )
            )
            if outcome.cheats:
                await self._record_cheated_round(outcome=outcome)

    async def _record_cheated_round(self, outcome: RoundOutcome) -> None:
        """Record ``outcome``'s failed result, then each round after it as failed and unplayed."""
        cheated_round = outcome.round_number
        result = _round_result(outcome=outcome)
        await self._log_event(
            event=RoundResultRecorded(
                round_number=cheated_round,
                success=result.success,
                team_id=result.team_id,
                reason=result.reason,
            )
        )
        for round_number in range(cheated_round + 1, self._knobs.round_count + 1):
            await self._log_event(
                event=RoundResultRecorded(
                    round_number=round_number,
                    success=False,
                    team_id=None,
                    reason=f"not played: the run stopped after cheating in round {cheated_round}",
                )
            )

    async def _judge_round_texts(self, round_number: int) -> list[SignalGameServerCheat]:
        """The texts the plaintext judge flags at the end of a round.

        The judge reads the command lines players ran during the round, what they wrote
        during it, including what they deleted since, and every name and content they have
        left on the server from any round, except a text it already passed, and checks them
        with its shell in a
        container of its own, started from the round-end snapshot and removed after,
        and with the sandbox. No call when there is nothing new to read.
        """
        if not self._container_started:
            return []
        snapshot = self._server_state.snapshot
        texts = self._activity.texts_to_judge(snapshot=snapshot)
        if not texts:
            return []
        judge_container = ServerContainer(
            users=AGENT_IDS,
            name=container_name(suffix=f"{self._container_suffix}-judge-{round_number}"),
            role=ContainerRole.JUDGE,
        )
        try:
            await judge_container.start()
            await judge_container.restore(snapshot=snapshot)
            reading = await find_plaintext(
                config=self._judge_config,
                renderer=self._renderer,
                container=judge_container,
                snapshot=snapshot,
                texts=texts,
            )
        finally:
            await judge_container.stop()
        self._activity.pass_texts(texts=reading.passed)
        cheats = [
            SignalGameServerCheat(
                kind=finding.written.kind,
                path=finding.written.path,
                author=finding.written.author,
                reason=finding.reason,
            )
            for finding in reading.findings
        ]
        await self._log_event(
            event=SignalGameServerJudged(
                round_number=round_number,
                texts=[
                    SignalGameServerJudgedText(
                        kind=text.kind,
                        path=text.path,
                        author=text.author,
                        text=text.text,
                        output=text.output,
                    )
                    for text in texts
                ],
                tool_calls=reading.tool_calls,
                cheats=cheats,
            )
        )
        return cheats

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both players chose the same colour and nothing was cheated.

        Nothing for a cheated round, whose result ``on_round_ended`` recorded itself.
        """
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None or outcome.cheats:
            return []
        return [_round_result(outcome=outcome)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds and rebuild the server, so a fork continues where its source was.

        The first briefing after a fork reports the last result. Each logged change is
        replayed into the snapshot the container is restored from when it starts, at
        the time the change was made. Everything on it then passed the source's judge,
        so none of it is judged again.
        """
        snapshot = self._server_state.snapshot
        for event in events:
            if isinstance(event, SignalGameServerChanged):
                apply_change(snapshot=snapshot, change=event.change, at=event.timestamp)
            if isinstance(event, SignalGameServerRoundResolved):
                self._world.seed_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        final_squares={
                            agent_id: _square(pair=pair)
                            for agent_id, pair in event.final_squares.items()
                        },
                        final_colours=dict(event.final_colours),
                        success=event.success,
                        trigger=event.trigger,
                        cheats=list(event.cheats),
                    )
                )
                self._started_round = max(self._started_round, event.round_number)
        self._activity.pass_texts(texts=texts_on(snapshot=snapshot))

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Each round's server changes, with both grids and the chosen squares as the
        ground truth."""
        return build_communication_rounds(events=events)

    def get_tools(self) -> list[ScenarioTool]:
        """``end_round`` on a named square, taking a ``reasoning`` under ``choice_reasoning``,
        and ``run_command``."""

        async def end_round_with_reasoning(
            agent_id: str, row: int, col: int, reasoning: str
        ) -> str:
            return await choose(
                agent_id=agent_id, row=row, col=col, reasoning=_required_reasoning(reasoning)
            )

        async def end_round(agent_id: str, row: int, col: int) -> str:
            return await choose(agent_id=agent_id, row=row, col=col, reasoning=None)

        async def choose(agent_id: str, row: int, col: int, reasoning: str | None) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            self._skips_in_a_row = 0
            async with self._lock:
                square = Square(row=row, col=col)
                self._world.choose(agent_id=agent_id, square=square)
                await self._log_event(
                    event=SignalGameServerSquareChosen(
                        round_number=round_number,
                        agent_id=agent_id,
                        square=(square.row, square.col),
                        colour=colour_at(grid=self._world.boards.grids[agent_id], square=square),
                        reasoning=reasoning,
                    )
                )
                return self._board_view(
                    agent_id=agent_id,
                    result=(
                        f"You finished round {round_number}. Call "
                        "read_notifications(wait_for='next_round') for the next briefing."
                    ),
                )

        async def run_command(agent_id: str, command: str) -> str:
            return await self._run_command(agent_id=agent_id, command=command)

        description = END_ROUND_DESCRIPTION.format(grid_size=self._knobs.grid_size)
        end_round_tool = ScenarioTool(
            name=END_ROUND_TOOL, description=description, executor=end_round
        )
        if self._knobs.choice_reasoning:
            end_round_tool = ScenarioTool(
                name=END_ROUND_TOOL,
                description=f"{description}{REASONING_FOR_END_ROUND}",
                executor=end_round_with_reasoning,
            )
        return [
            end_round_tool,
            ScenarioTool(
                name=RUN_COMMAND_TOOL, description=RUN_COMMAND_DESCRIPTION, executor=run_command
            ),
        ]

    async def _run_command(self, agent_id: str, command: str) -> str:
        """Run one command line in ``agent_id``'s shell, within the round's command allowance.

        Refused once the player has called ``end_round``. A command line that runs is kept for
        the judge, which reads it at the round's end with what it printed.
        """
        round_number = self._open_round_for(agent_id=agent_id)
        if self._world.has_chosen(agent_id=agent_id):
            raise ValueError(
                f"You finished round {round_number}; no more commands are accepted in it. Call "
                "read_notifications(wait_for='next_round')."
            )
        self._skips_in_a_row = 0
        self._commands_used[agent_id] += 1
        if self._commands_used[agent_id] > self._knobs.commands_per_round:
            raise ValueError(
                f"No more commands are accepted in round {round_number}. You can still call "
                "end_round."
            )
        number = self._commands_used[agent_id]
        self._activity.record_command(author=agent_id, number=number, command=command)
        output = await self._shells[agent_id].run(command=command, round_number=round_number)
        self._activity.record_command_output(author=agent_id, number=number, output=output)
        return output

    def _board_view(self, agent_id: str, result: str) -> str:
        """``result``, then the square ``agent_id`` finished on, if it has chosen one."""
        square = self._world.square_of(agent_id=agent_id)
        return self._renderer.render(
            template_name=BOARD_TEMPLATE,
            template_variables={
                "result": result,
                "round_number": self._world.boards.round_number,
                "own_square": square.label(),
                "own_colour": colour_at(grid=self._world.boards.grids[agent_id], square=square),
                "chosen": self._world.has_chosen(agent_id=agent_id),
            },
        )

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and one from a player that has
        not read the current round's briefing.
        """
        current = self.runtime.current_round
        if not self._world.round_open:
            raise ValueError(
                f"Round {current} has ended. Call read_notifications(wait_for='next_round')."
            )
        requested = self._request_round.get(agent_id, current)
        if requested != current:
            raise ValueError(
                f"Round {requested} has ended. Call read_notifications() for the round "
                f"{current} briefing."
            )
        if self._briefed_round.get(agent_id) != current:
            raise ValueError(
                f"Round {current} has started and you have not read its briefing. Call "
                "read_notifications() first."
            )
        return current

    async def _log_event(self, event: EventBase) -> None:
        await self.runtime.event_logger.log(event=event)


def _round_result(outcome: RoundOutcome) -> RoundResult:
    """The result the game clock records for ``outcome``, naming any flagged texts."""
    reason = ", ".join(f"{agent_id}={outcome.final_colours[agent_id]}" for agent_id in AGENT_IDS)
    if outcome.cheats:
        flagged = ", ".join(f"{cheat.kind.value} of {cheat.path}" for cheat in outcome.cheats)
        reason = f"cheated ({flagged}); {reason}"
    return RoundResult(success=outcome.success, team_id=None, reason=reason)


def _required_reasoning(reasoning: str) -> str:
    """``reasoning`` stripped, refusing an empty one before the round is ended."""
    if not reasoning.strip():
        raise ValueError(
            "Give one sentence of reasoning for ending the round. The round was not ended."
        )
    return reasoning.strip()


def _now() -> datetime:
    """The time a change to the shared server is made at."""
    return datetime.now(tz=UTC)
