"""Two players on separate coloured grids who can affect each other only by moving.

An adaptation of the Embodied Communication Game (Scott-Phillips, Kirby & Ritchie
2009). Each player sees its own grid's colours, the partner's square and every
move the partner makes, and nothing else of the partner. A round scores when both
finish on squares of the same colour. There is no channel and no tool that takes
free text, so anything one player tells the other is built out of moves.

The geometry is in ``board``, the round state in ``world``. This module wires
them to the platform.
"""

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.llm.deferred_provider import DeferredLLMProvider
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import RoundResultRecorded, SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.model_consumer import ModelConsumer
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.signal_game.board import (
    Square,
    colour_at,
    colour_order,
    generate_boards,
)
from glossogen.scenarios.signal_game.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.signal_game.evaluation.cheated_rounds_metric import CheatedRoundsMetric
from glossogen.scenarios.signal_game.evaluation.excess_moves_metric import ExcessMovesMetric
from glossogen.scenarios.signal_game.evaluation.longest_streak_metric import LongestStreakMetric
from glossogen.scenarios.signal_game.events import (
    SignalGameCheat,
    SignalGameMoveMade,
    SignalGamePlaintextJudged,
    SignalGamePlayerFinished,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
    SignalGameServerChanged,
)
from glossogen.scenarios.signal_game.ids import (
    AGENT_IDS,
    BOARD_TEMPLATE,
    BOTH_FINISHED_TRIGGER,
    DESCRIPTION_TEMPLATE,
    END_ROUND_TOOL,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    MAX_MOVES_PER_CALL,
    MOVE_RESULT_TEMPLATE,
    MOVE_TOOL,
    PARTNER_OF,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    RUN_COMMAND_TOOL,
    SYSTEM_TEMPLATE,
    Direction,
    Medium,
)
from glossogen.scenarios.signal_game.knobs import SignalGameKnobs
from glossogen.scenarios.signal_game.plaintext_judge import find_plaintext
from glossogen.scenarios.signal_game.server_activity import ServerActivity
from glossogen.scenarios.signal_game.server_shell_fs import ServerShellFs
from glossogen.scenarios.signal_game.shared_server import SharedServer
from glossogen.scenarios.signal_game.shell_session import ShellSession, WaitBudget, build_commands
from glossogen.scenarios.signal_game.wake_package import SignalGameWake
from glossogen.scenarios.signal_game.world import LoggedAction, RoundOutcome, SignalGameWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per round a player is released from a wait nothing can end. Past it the
player stays parked, and the round ends once both are."""

PARTNER_ACTED = "partner_acted"
"""The release detail that wakes a parked player when its partner has acted. The
wake renders it as a reason and shows the board, not as a notice."""

MOVE_DESCRIPTION = (
    f"Move your figure through 1 to {MAX_MOVES_PER_CALL} steps, applied in order. Each step "
    "is up, down, left or right (one square) and spends one of your moves for the "
    "round. Your partner sees every step. A step off the grid, or past your last move, stops "
    "the sequence there: the steps before it stand. Returns the board and your partner's "
    "actions since you last looked."
)
END_ROUND_DESCRIPTION = (
    "Finish this round on the square you are on. Your square cannot change after this. "
    "Returns the board."
)
FILE_SYSTEM_END_ROUND_DESCRIPTION = (
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
    "during a round it waits until your partner acts, then returns the board with its "
    "actions. read_notifications(wait_for='next_round') declares you are done with this round "
    "and waits for the next briefing. The result is a wake package: the reasons, any "
    "briefings, the board, and a notice when the wait was cut short; type done ends the game. "
    "Must be the only tool call in its response."
)
FILE_SYSTEM_READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "during a round, read_notifications(timeout_s=N) waits up to N seconds and returns your "
    "board, "
    "and without timeout_s it waits until the next briefing. "
    "read_notifications(wait_for='next_round') declares you are done with this round and waits "
    "for the next briefing. The result is a wake package: the reasons, any briefings, and the "
    "board; type done ends the game. Must be the only tool call in its response."
)
REASONING_FOR_MOVE = (
    " reasoning is one sentence on why you are moving this way; your partner never sees it."
)

RUN_COMMAND_DESCRIPTION = (
    "Run one bash command line on the server as your user and return what it printed: "
    "stdout, then stderr, then the exit status when it is not zero. Pipes, redirection, "
    "heredocs and loops work."
)


class _ArmedDeadline(NamedTuple):
    """A parked player's wait deadline under ``file_system``: when it falls, and its timer."""

    at: float
    fire: Callable[[], None]
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


class ShownAction(NamedTuple):
    """One of the partner's actions, as the board view reads it."""

    sequence: int
    action: str
    square: str


def _square(pair: tuple[int, int]) -> Square:
    return Square(row=pair[0], col=pair[1])


class SignalGameScenario(SimulationScenario):
    """The Embodied Communication Game for two LLM agents, with no channel."""

    @classmethod
    def knobs_model(cls) -> type[SignalGameKnobs]:
        """Return the knobs model class for this scenario."""
        return SignalGameKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """The two players. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

    @classmethod
    def get_judge_models(cls, knobs: dict[str, Any] | None) -> tuple[ModelConsumer, ...]:
        """The plaintext judge, which only the ``file_system`` medium calls."""
        if knobs is None or "medium" not in knobs:
            return ()
        if Medium(knobs["medium"]) is not Medium.FILE_SYSTEM:
            return ()
        return super().get_judge_models(knobs=knobs)

    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """The metrics that only read signal_game runs."""
        return (ExcessMovesMetric, LongestStreakMetric, CheatedRoundsMetric)

    def __init__(self, knobs: SignalGameKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = SignalGameWorld(
            grid_size=knobs.grid_size, moves_per_round=knobs.moves_per_round
        )
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
        self._server = SharedServer(users=AGENT_IDS, at=_now())
        self._activity = ServerActivity(
            server=self._server, log_event=self._log_event, round_open=self._shell_round_open
        )
        self._shells = {
            agent_id: self._new_shell(agent_id=agent_id, knobs=knobs) for agent_id in AGENT_IDS
        }
        # run_command calls each player made in the open round.
        self._commands_used: dict[str, int] = dict.fromkeys(AGENT_IDS, 0)
        # The round whose end is being judged; its command lines may no longer act.
        self._closing_round = 0
        self._judge_provider = DeferredLLMProvider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )
        # Each parked player's wait deadline under file_system.
        self._deadlines: dict[str, _ArmedDeadline] = {}
        self._lock = asyncio.Lock()
        # The round each player's current model request was issued in, so a
        # move it makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each player has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def _new_shell(self, agent_id: str, knobs: SignalGameKnobs) -> ShellSession:
        """``agent_id``'s shell on the shared server, with its own wait budget."""
        view = ServerShellFs(
            server=self._server, user=agent_id, observer=self._activity, clock=_now
        )
        wait_budget = WaitBudget(seconds_per_command=knobs.max_sleep_seconds)
        return ShellSession(
            view=view,
            commands=build_commands(
                view=view,
                activity=self._activity,
                users=AGENT_IDS,
                wait_budget=wait_budget,
                sleeper=asyncio.sleep,
            ),
            wait_budget=wait_budget,
            output_char_limit=knobs.command_output_char_limit,
        )

    def _shell_round_open(self, round_number: int) -> bool:
        """Whether a command line run in ``round_number`` may still act on the server."""
        return (
            self._world.round_open
            and self._started_round == round_number
            and self._closing_round != round_number
        )

    def get_knobs(self) -> SignalGameKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> SignalGameWorld:
        """Return the round state: positions, moves, verdicts."""
        return self._world

    @property
    def _file_system(self) -> bool:
        return self._knobs.medium is Medium.FILE_SYSTEM

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "file_system": self._file_system,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per player, in no channel, offered move and end_round, and under
        ``file_system`` end_round and the shared-server command instead."""
        tool_names = [MOVE_TOOL, END_ROUND_TOOL]
        if self._file_system:
            tool_names = [END_ROUND_TOOL, RUN_COMMAND_TOOL]
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(agent_id=agent_id),
                channel_ids=[],
                tool_names=list(tool_names),
                model=default_model,
                provider=Provider(default_provider),
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self, agent_id: str) -> str:
        """The rules, the same for both players but for the order the colours are listed in."""
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "colours": self._colour_orders[agent_id],
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "moves_per_round": self._knobs.moves_per_round,
                "max_moves_per_call": MAX_MOVES_PER_CALL,
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
                "file_system": self._file_system,
                "user": agent_id,
                "partner_user": PARTNER_OF[agent_id],
            },
        )

    def get_channels(self) -> list[Channel]:
        """None: moves are the only thing that passes between the players."""
        return []

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """None, so the primary-channel metrics skip a run with no text."""
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
        """The move protocol, and under ``file_system`` the server commands; no messages."""
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={
                    "max_moves_per_call": MAX_MOVES_PER_CALL,
                    "move_reasoning": self._knobs.move_reasoning,
                    "file_system": self._file_system,
                },
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE,
                template_variables={"file_system": self._file_system},
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE,
                template_variables={"file_system": self._file_system},
            ),
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits a player uses."""
        if self._file_system:
            return FILE_SYSTEM_READ_NOTIFICATIONS_DESCRIPTION
        return READ_NOTIFICATIONS_DESCRIPTION

    def default_any_wait_timeout_s(self) -> float | None:
        """A plain wait ends only when something arrives: only the players change the board."""
        return None

    def allows_parallel_tool_calls(self) -> bool:
        """One action per response: a player must see its partner's reply before its next move.

        With parallel calls a model can move, end the round and wait in one
        response, fixing its square before anything its partner does could reach it.
        """
        return False

    def ends_round_when_all_agents_waiting(self) -> bool:
        """Two parked players cannot change anything, so the round ends."""
        return True

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: briefings, the board with the partner's new actions, any notice.

        Everything is taken before anything awaits, so an action the partner makes
        while this renders is still unshown and goes with the next result.
        """
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
        reasons = [reason.value for reason in wake.reasons]
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            if wake.release_detail == PARTNER_ACTED:
                reasons = [
                    PARTNER_ACTED if reason == WakeReason.RELEASED.value else reason
                    for reason in reasons
                ]
            else:
                notice = wake.release_detail
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated or any(
            isinstance(notification, DoneNotification) for notification in lifecycle
        ):
            wake_type = "done"
        return SignalGameWake(
            type=wake_type,
            round=current,
            wake_reasons=reasons,
            briefings=briefings,
            board=board,
            notice=notice,
        ).model_dump_json()

    def on_agent_parked(self, agent_id: str) -> None:
        """Resume a waiting player at once when there is something to see, or nothing to wait for.

        A player waits with a plain ``read_notifications()`` until its partner
        acts. A partner action it has not been shown resumes it straight away.
        When the partner has finished, or is parked too, nothing will arrive, so
        the player is released with a notice saying so, at most
        ``RELEASE_LIMIT`` times a round. A player that has finished, or waits
        for the next round, is otherwise left parked.

        Under ``file_system`` nothing of the partner wakes a player; see
        ``_skip_to_next_deadline``.
        """
        if self._file_system:
            self._skip_to_next_deadline()
            return
        if not self._world.round_open:
            return
        if self._briefed_round.get(agent_id) != self.runtime.current_round:
            return
        parked = self.runtime.parked_waits()
        wait = parked.get(agent_id)
        if wait is None or wait.wait_for is WaitFor.NEXT_ROUND:
            return
        if self._world.has_unseen(agent_id=agent_id):
            self.runtime.release_wait(agent_id=agent_id, detail=PARTNER_ACTED)
            return
        if self._world.is_finished(agent_id=agent_id):
            return
        partner = PARTNER_OF[agent_id]
        partner_finished = self._world.is_finished(agent_id=partner)
        if not partner_finished and partner not in parked:
            return
        if not self._world.claim_release(agent_id=agent_id, limit=RELEASE_LIMIT):
            return
        self.runtime.release_wait(
            agent_id=agent_id,
            detail=self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={
                    "partner_finished": partner_finished,
                },
            ),
        )

    def schedule_wait_timeout(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        """Arm a wall-clock deadline, and under ``file_system`` remember it for skipping ahead."""
        if not self._file_system:
            return super().schedule_wait_timeout(agent_id=agent_id, timeout_s=timeout_s, fire=fire)
        loop = asyncio.get_running_loop()

        def fire_once() -> None:
            if self._deadlines.get(agent_id) is armed:
                del self._deadlines[agent_id]
            fire()

        armed = _ArmedDeadline(
            at=loop.time() + timeout_s,
            fire=fire_once,
            handle=loop.call_later(timeout_s, fire_once),
        )
        self._deadlines[agent_id] = armed

        def cancel() -> None:
            armed.handle.cancel()
            if self._deadlines.get(agent_id) is armed:
                del self._deadlines[agent_id]

        return cancel

    def _skip_to_next_deadline(self) -> None:
        """With every running player parked, fire the earliest wait deadline now.

        Only the players change the server, so while all of them wait nothing changes
        until a deadline falls; the earliest falls at once. This also keeps the game
        clock from reading two players on deadlines as an idle round. With no deadline
        left, every player waits for good and ``ends_round_when_all_agents_waiting``
        ends the round.
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
        if not armed:
            return
        _, agent_id = min(armed)
        deadline = self._deadlines[agent_id]
        deadline.handle.cancel()
        deadline.fire()

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous result, revealed grid, this round's grid and starts."""
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
                "own_start": boards.starts[agent_id].label(),
                "partner_start": boards.starts[partner].label(),
                "moves_per_round": self._knobs.moves_per_round,
                "file_system": self._file_system,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Put each player on its start square and log the round's grids and starts."""
        if round_number <= self._started_round:
            return
        boards = self._boards[round_number - 1]
        self._world.start_round(boards=boards)
        self._started_round = round_number
        self._activity.start_round()
        self._commands_used = dict.fromkeys(AGENT_IDS, 0)
        await self._log_event(
            event=SignalGameRoundStarted(
                round_number=round_number,
                grids=boards.grids,
                start_squares={
                    agent_id: (square.row, square.col) for agent_id, square in boards.starts.items()
                },
                moves_per_round=self._knobs.moves_per_round,
                partner_colours_visible=self._knobs.partner_colours_visible,
                colour_orders=self._colour_orders,
                medium=self._knobs.medium,
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once neither player can move."""
        if self._world.both_finished():
            return BOTH_FINISHED_TRIGGER
        return None

    def is_finished_early(self) -> bool:
        """Stop the run once the plaintext judge has taken a round."""
        return self._world.cheated_round() is not None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the squares the players stand on.

        Under ``file_system`` the judge first reads the server. The round is marked
        closing before anything awaits, so a command line still running stops at its
        next access instead of changing the server after the judge has read it. A
        cheated round stops the run, and every round after it is recorded as failed.
        """
        self._closing_round = round_number
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            cheats = await self._judge_round_texts(round_number=round_number)
            outcome = self._world.resolve(round_number=round_number, trigger=trigger, cheats=cheats)
            await self._log_event(
                event=SignalGameRoundResolved(
                    round_number=round_number,
                    final_squares={
                        agent_id: (square.row, square.col)
                        for agent_id, square in outcome.final_squares.items()
                    },
                    final_colours=dict(outcome.final_colours),
                    moves_used=dict(outcome.moves_used),
                    success=outcome.success,
                    trigger=trigger,
                    cheats=outcome.cheats,
                )
            )
            if outcome.cheats:
                await self._forfeit_rounds_after(cheated_round=round_number)

    async def _forfeit_rounds_after(self, cheated_round: int) -> None:
        """Record each round after ``cheated_round`` as failed, since the run stops there."""
        for round_number in range(cheated_round + 1, self._knobs.round_count + 1):
            await self._log_event(
                event=RoundResultRecorded(
                    round_number=round_number,
                    success=False,
                    team_id=None,
                    reason=f"not played: the run stopped after cheating in round {cheated_round}",
                )
            )

    async def _judge_round_texts(self, round_number: int) -> list[SignalGameCheat]:
        """The texts the plaintext judge flags at the end of a round.

        The judge reads what players wrote during the round, including what they
        deleted since, and every name and content they have left on the server from
        any round. No call when there is nothing to read.
        """
        if not self._file_system:
            return []
        texts = self._activity.texts_to_judge()
        if not texts:
            return []
        findings = await find_plaintext(
            provider=self._judge_provider, renderer=self._renderer, texts=texts
        )
        cheats = [
            SignalGameCheat(
                kind=finding.written.kind.value,
                path=finding.written.path,
                author=finding.written.author,
                reason=finding.reason,
            )
            for finding in findings
        ]
        await self._log_event(
            event=SignalGamePlaintextJudged(
                round_number=round_number, texts_judged=len(texts), cheats=cheats
            )
        )
        return cheats

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both players finished on the same colour. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        reason = ", ".join(
            f"{agent_id}={outcome.final_colours[agent_id]}" for agent_id in AGENT_IDS
        )
        if outcome.cheats:
            flagged = ", ".join(f"{cheat.kind} of {cheat.path}" for cheat in outcome.cheats)
            reason = f"cheated ({flagged}); {reason}"
        return [RoundResult(success=outcome.success, team_id=None, reason=reason)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds and rebuild the server, so a fork continues where its source was.

        The first briefing after a fork reports the last result. The server comes
        back by replaying each logged change at the time it was made.
        """
        for event in events:
            if isinstance(event, SignalGameServerChanged):
                self._activity.replay(event=event)
            if isinstance(event, SignalGameRoundResolved):
                self._world.seed_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        final_squares={
                            agent_id: _square(pair=pair)
                            for agent_id, pair in event.final_squares.items()
                        },
                        final_colours=dict(event.final_colours),
                        moves_used=dict(event.moves_used),
                        success=event.success,
                        trigger=event.trigger,
                        cheats=list(event.cheats),
                    )
                )
                self._started_round = max(self._started_round, event.round_number)

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Each round's move traces, with both grids as the ground truth."""
        return build_communication_rounds(events=events)

    def get_tools(self) -> list[ScenarioTool]:
        """``move`` and ``end_round`` under ``grid``; under ``file_system`` an ``end_round``
        that names the square, and ``run_command``."""
        if self._file_system:
            return self._file_system_tools()
        return self._grid_tools()

    def _grid_tools(self) -> list[ScenarioTool]:
        """``move`` and ``end_round``, each taking a ``reasoning`` under ``move_reasoning``."""

        async def move_with_reasoning(
            agent_id: str, directions: list[Direction], reasoning: str
        ) -> str:
            if not reasoning.strip():
                raise ValueError("Give one sentence of reasoning for this move. Nothing was moved.")
            return await apply_move(
                agent_id=agent_id, directions=directions, reasoning=reasoning.strip()
            )

        async def move(agent_id: str, directions: list[Direction]) -> str:
            return await apply_move(agent_id=agent_id, directions=directions, reasoning=None)

        async def apply_move(
            agent_id: str, directions: list[Direction], reasoning: str | None
        ) -> str:
            if not 1 <= len(directions) <= MAX_MOVES_PER_CALL:
                raise ValueError(
                    f"Give between 1 and {MAX_MOVES_PER_CALL} directions. Nothing was moved."
                )
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                steps, stopped = await self._apply_steps(
                    agent_id=agent_id,
                    round_number=round_number,
                    directions=directions,
                    reasoning=reasoning,
                )
                if not steps:
                    raise ValueError(stopped)
                view = self._board_view(
                    agent_id=agent_id,
                    result=self._renderer.render(
                        template_name=MOVE_RESULT_TEMPLATE,
                        template_variables={
                            "steps": [
                                ShownAction(
                                    sequence=step.sequence,
                                    action=step.action,
                                    square=step.square.label(),
                                )
                                for step in steps
                            ],
                            "stopped": stopped,
                            "requested": len(directions),
                        },
                    ),
                )
            self._wake_partner_of(agent_id=agent_id)
            return view

        async def end_round_with_reasoning(agent_id: str, reasoning: str) -> str:
            return await finish_round(agent_id=agent_id, reasoning=_required_reasoning(reasoning))

        async def end_round(agent_id: str) -> str:
            return await finish_round(agent_id=agent_id, reasoning=None)

        async def finish_round(agent_id: str, reasoning: str | None) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.end(agent_id=agent_id)
                await self._log_finish(
                    agent_id=agent_id, round_number=round_number, entry=entry, reasoning=reasoning
                )
                view = self._board_view(
                    agent_id=agent_id,
                    result=(
                        f"You finished round {round_number} (#{entry.sequence}). Call "
                        "read_notifications(wait_for='next_round') for the next briefing."
                    ),
                )
            self._wake_partner_of(agent_id=agent_id)
            return view

        if self._knobs.move_reasoning:
            return [
                ScenarioTool(
                    name=MOVE_TOOL,
                    description=f"{MOVE_DESCRIPTION}{REASONING_FOR_MOVE}",
                    executor=move_with_reasoning,
                ),
                ScenarioTool(
                    name=END_ROUND_TOOL,
                    description=f"{END_ROUND_DESCRIPTION}{REASONING_FOR_END_ROUND}",
                    executor=end_round_with_reasoning,
                ),
            ]
        return [
            ScenarioTool(name=MOVE_TOOL, description=MOVE_DESCRIPTION, executor=move),
            ScenarioTool(
                name=END_ROUND_TOOL, description=END_ROUND_DESCRIPTION, executor=end_round
            ),
        ]

    def _file_system_tools(self) -> list[ScenarioTool]:
        """``end_round`` on a named square, taking a ``reasoning`` under ``move_reasoning``,
        and ``run_command``."""

        async def end_round_with_reasoning(
            agent_id: str, row: int, col: int, reasoning: str
        ) -> str:
            return await finish_on(
                agent_id=agent_id, row=row, col=col, reasoning=_required_reasoning(reasoning)
            )

        async def end_round(agent_id: str, row: int, col: int) -> str:
            return await finish_on(agent_id=agent_id, row=row, col=col, reasoning=None)

        async def finish_on(agent_id: str, row: int, col: int, reasoning: str | None) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.end_on(agent_id=agent_id, square=Square(row=row, col=col))
                await self._log_finish(
                    agent_id=agent_id, round_number=round_number, entry=entry, reasoning=reasoning
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

        description = FILE_SYSTEM_END_ROUND_DESCRIPTION.format(grid_size=self._knobs.grid_size)
        end_round_tool = ScenarioTool(
            name=END_ROUND_TOOL, description=description, executor=end_round
        )
        if self._knobs.move_reasoning:
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

    async def _log_finish(
        self, agent_id: str, round_number: int, entry: LoggedAction, reasoning: str | None
    ) -> None:
        """Log ``agent_id`` finishing ``round_number`` on ``entry``'s square."""
        grid = self._world.boards.grids[agent_id]
        await self._log_event(
            event=SignalGamePlayerFinished(
                round_number=round_number,
                agent_id=agent_id,
                square=(entry.square.row, entry.square.col),
                colour=colour_at(grid=grid, square=entry.square),
                moves_used=self._knobs.moves_per_round - self._world.moves_left(agent_id=agent_id),
                reasoning=reasoning,
            )
        )

    async def _run_command(self, agent_id: str, command: str) -> str:
        """Run one command line in ``agent_id``'s shell, within the round's command allowance."""
        round_number = self._open_round_for(agent_id=agent_id)
        self._commands_used[agent_id] += 1
        if self._commands_used[agent_id] > self._knobs.commands_per_round:
            raise ValueError(
                f"No more commands are accepted in round {round_number}. You can still call "
                "end_round."
            )
        return await self._shells[agent_id].run(command=command, round_number=round_number)

    async def _apply_steps(
        self,
        agent_id: str,
        round_number: int,
        directions: list[Direction],
        reasoning: str | None,
    ) -> tuple[list[LoggedAction], str | None]:
        """Apply ``directions`` in order, logging each step, until one is refused.

        Every step of the call is logged with the call's ``reasoning``, None when
        ``move_reasoning`` is off.

        Returns the steps that stood and the refusal that stopped the rest, or
        None when every step stood. The caller holds the lock, so the partner
        cannot act between the steps of one call.
        """
        steps: list[LoggedAction] = []
        for direction in directions:
            refusal = self._world.move_refusal(agent_id=agent_id, direction=direction)
            if refusal is not None:
                return steps, refusal
            entry = self._world.move(agent_id=agent_id, direction=direction)
            steps.append(entry)
            await self._log_event(
                event=SignalGameMoveMade(
                    round_number=round_number,
                    agent_id=agent_id,
                    sequence=entry.sequence,
                    direction=entry.action,
                    from_square=(entry.from_square.row, entry.from_square.col),
                    to_square=(entry.square.row, entry.square.col),
                    moves_used=self._knobs.moves_per_round
                    - self._world.moves_left(agent_id=agent_id),
                    reasoning=reasoning,
                )
            )
        return steps, None

    def _wake_partner_of(self, agent_id: str) -> None:
        """Resume ``agent_id``'s partner if it is waiting for an action, so it sees this one.

        A partner that is not parked sees the action in its next result, and one
        that parks before then is resumed by ``on_agent_parked``. Under ``file_system``
        the partner perceives no action, so nothing is resumed.
        """
        if self._file_system:
            return
        partner = PARTNER_OF[agent_id]
        wait = self.runtime.parked_waits().get(partner)
        if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
            self.runtime.release_wait(agent_id=partner, detail=PARTNER_ACTED)

    def _board_view(self, agent_id: str, result: str) -> str:
        """The board from ``agent_id``'s side, marking the partner's actions shown.

        Under ``file_system`` it shows only the square the player finished on, if any.
        """
        partner = PARTNER_OF[agent_id]
        boards = self._world.boards
        own_square = self._world.square_of(agent_id=agent_id)
        partner_square = self._world.square_of(agent_id=partner)
        partner_colour: str | None = None
        if self._knobs.partner_colours_visible:
            partner_colour = colour_at(grid=boards.grids[partner], square=partner_square)
        partner_actions: list[ShownAction] = []
        if not self._file_system:
            partner_actions = [
                _shown(entry=entry) for entry in self._world.take_unseen(agent_id=agent_id)
            ]
        return self._renderer.render(
            template_name=BOARD_TEMPLATE,
            template_variables={
                "result": result,
                "round_number": boards.round_number,
                "own_square": own_square.label(),
                "own_colour": colour_at(grid=boards.grids[agent_id], square=own_square),
                "moves_left": self._world.moves_left(agent_id=agent_id),
                "own_ended": self._world.has_ended(agent_id=agent_id),
                "partner_square": partner_square.label(),
                "partner_colour": partner_colour,
                "partner_ended": self._world.has_ended(agent_id=partner),
                "partner_actions": partner_actions,
                "file_system": self._file_system,
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


def _required_reasoning(reasoning: str) -> str:
    """``reasoning`` stripped, refusing an empty one before the round is ended."""
    if not reasoning.strip():
        raise ValueError(
            "Give one sentence of reasoning for ending the round. The round was not ended."
        )
    return reasoning.strip()


def _shown(entry: LoggedAction) -> ShownAction:
    return ShownAction(sequence=entry.sequence, action=entry.action, square=entry.square.label())


def _now() -> datetime:
    """The time a change to the shared server is made at."""
    return datetime.now(tz=UTC)
