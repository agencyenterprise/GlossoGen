"""Two players on separate coloured grids who can affect each other only by moving.

An adaptation of the Embodied Communication Game (Scott-Phillips, Kirby & Ritchie
2009). Each player sees its own grid's colours, the partner's square and every
move the partner makes, and nothing else of the partner. A round scores when both
finish on squares of the same colour. There is no channel and no tool that takes
free text, so anything one player tells the other is built out of moves.

The geometry is in ``board``, the round state in ``world``. This module wires
them to the platform. Every change to the world is applied synchronously; the
lock only keeps the events in the order the changes happened.
"""

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import Field

from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.signal_game.board import (
    START_SQUARE,
    Square,
    colour_at,
    generate_boards,
)
from glossogen.scenarios.signal_game.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.signal_game.evaluation.excess_moves_metric import ExcessMovesMetric
from glossogen.scenarios.signal_game.events import (
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)
from glossogen.scenarios.signal_game.ids import (
    AGENT_IDS,
    BOARD_TEMPLATE,
    BOTH_FINISHED_TRIGGER,
    DESCRIPTION_TEMPLATE,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    MAX_MOVES_PER_CALL,
    MOVE_RESULT_TEMPLATE,
    MOVE_TOOL,
    OBSERVE_TOOL,
    PALETTE,
    PARTNER_OF,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    SYSTEM_TEMPLATE,
    UNSEEN_REFUSAL_TEMPLATE,
    Direction,
)
from glossogen.scenarios.signal_game.knobs import SignalGameKnobs
from glossogen.scenarios.signal_game.turn_events import turn_events
from glossogen.scenarios.signal_game.wake_package import SignalGameWake
from glossogen.scenarios.signal_game.world import RoundOutcome, SignalGameWorld, Turn
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per round a player is released from a wait nothing can end. Past it the
player stays parked, and the round ends once both are."""

PARTNER_ACTED = "partner_acted"
"""The release detail that wakes a parked player when its partner has acted. The
wake renders it as a reason and shows the board, not as a notice."""

MOVE_DESCRIPTION = (
    f"Move your figure through 1 to {MAX_MOVES_PER_CALL} steps, applied in order. Each step "
    "is up, down, left or right (one square) and spends one of your moves for the round. "
    "A step off the grid, or past your last move, stops the sequence there: the steps before "
    "it stand. Returns the board and your partner's actions since you last looked."
)
TURN_BASED_MOVE_DESCRIPTION = (
    " One call is one turn: after it, wait for your partner's turn with "
    "read_notifications(wait_for='message') "
    "before moving again."
)
OBSERVE_DESCRIPTION = (
    "Return the board with every action your partner has made this round. Spends no move "
    "and is not one of your actions."
)
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup. "
    "read_notifications(wait_for='message') waits until your partner acts, then returns the "
    "board with its actions. read_notifications(wait_for='next_round') finishes your round "
    "on your current square, which then cannot change, and waits for the next briefing. "
    "The result is a wake "
    "package: the reasons, any briefings, the board, and a notice when the wait was cut "
    "short; type done ends the game. Must be the only tool call in its response."
)
TURN_BASED_READ_NOTIFICATIONS_DESCRIPTION = (
    " On your own turn, read_notifications(wait_for='message') passes the turn to your "
    "partner instead."
)


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
    """One of the partner's turns, as the board view reads it."""

    number: int
    kind: str
    directions: list[str]
    square: str


def _square(pair: tuple[int, int]) -> Square:
    return Square(row=pair[0], col=pair[1])


def _shown(turn: Turn) -> ShownAction:
    return ShownAction(
        number=turn.number,
        kind=turn.kind.value,
        directions=[applied.direction.value for applied in turn.steps],
        square=turn.square.label(),
    )


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
    def get_available_metric_names(cls) -> list[str]:
        """Every generic metric, plus ``excess_moves``, which only reads signal_game runs."""
        return sorted(set(super().get_available_metric_names()) | {ExcessMovesMetric.name})

    def __init__(self, knobs: SignalGameKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = SignalGameWorld(
            grid_size=knobs.grid_size,
            moves_per_round=knobs.moves_per_round,
            turn_based=knobs.turn_based,
        )
        self._boards = generate_boards(
            seed=knobs.seed,
            round_count=knobs.round_count,
            grid_size=knobs.grid_size,
            colour_count=knobs.colour_count,
        )
        self._lock = asyncio.Lock()
        self._background_logs: set[asyncio.Task[None]] = set()
        # The round each player's current model request was issued in, so a
        # move it makes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each player has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def get_knobs(self) -> SignalGameKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> SignalGameWorld:
        """Return the round state: positions, turns, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "turn_based": self._knobs.turn_based,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per player, in no channel, offered move and, if enabled, observe."""
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(),
                channel_ids=[],
                tool_names=self._tool_names(),
                model=default_model,
                provider=Provider(default_provider),
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _tool_names(self) -> list[str]:
        """The scenario tools each player is offered."""
        if self._knobs.observe_enabled:
            return [MOVE_TOOL, OBSERVE_TOOL]
        return [MOVE_TOOL]

    def _system_prompt(self) -> str:
        """The rules. Both players read the same text: the game is symmetric."""
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "colours": list(PALETTE[: self._knobs.colour_count]),
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "max_moves_per_call": MAX_MOVES_PER_CALL,
                "turn_based": self._knobs.turn_based,
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
        """The move protocol, with no mention of messages."""
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={
                    "max_moves_per_call": MAX_MOVES_PER_CALL,
                    "observe_enabled": self._knobs.observe_enabled,
                    "turn_based": self._knobs.turn_based,
                },
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
        if self._knobs.turn_based:
            return READ_NOTIFICATIONS_DESCRIPTION + TURN_BASED_READ_NOTIFICATIONS_DESCRIPTION
        return READ_NOTIFICATIONS_DESCRIPTION

    def default_any_wait_timeout_s(self) -> float | None:
        """A plain wait ends only when something arrives: only the players change the board."""
        return None

    def allows_parallel_tool_calls(self) -> bool:
        """One action per response: a player must see its partner's reply before its next move.

        With parallel calls a model can move and wait for the next round in one
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
            board = self._board_view(agent_id=agent_id, result="Board.", whole_round=False)
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
        """Act on a player's wait: finish its round, pass its turn, or resume it.

        ``wait_for="next_round"`` finishes the player's round on its square. A
        plain wait resumes at once when the partner has acted unseen. Under
        ``turn_based``, a plain wait on the player's own turn passes the turn.
        Otherwise a player waiting on a partner that has finished, or is parked
        too, is released with a notice, at most ``RELEASE_LIMIT`` times a round.
        """
        current = self.runtime.current_round
        if not self._world.round_open or self._briefed_round.get(agent_id) != current:
            return
        if self._request_round.get(agent_id, current) != current:
            return
        wait = self.runtime.parked_waits().get(agent_id)
        if wait is None:
            return
        self._world.stop_observing(agent_id=agent_id)
        if wait.wait_for is WaitFor.NEXT_ROUND:
            self._finish(agent_id=agent_id, round_number=current)
            return
        if self._world.has_unseen(agent_id=agent_id):
            self.runtime.release_wait(agent_id=agent_id, detail=PARTNER_ACTED)
            return
        if self._world.is_finished(agent_id=agent_id):
            return
        if self._world.holds_turn(agent_id=agent_id):
            self._pass_turn(agent_id=agent_id, round_number=current)
            return
        self._release_if_nothing_can_arrive(agent_id=agent_id)

    def _finish(self, agent_id: str, round_number: int) -> None:
        """Fix ``agent_id``'s square for the round and tell its partner."""
        if self._world.has_ended(agent_id=agent_id):
            return
        turn = self._world.finish(agent_id=agent_id)
        self._wake_partner_of(agent_id=agent_id)
        self._log_in_background(
            events=self._events_of(agent_id=agent_id, round_number=round_number, turn=turn)
        )

    def _pass_turn(self, agent_id: str, round_number: int) -> None:
        """Hand ``agent_id``'s turn to its partner; a pass answering a pass wakes no one."""
        outcome = self._world.pass_turn(agent_id=agent_id)
        if not outcome.answers_a_pass:
            self._wake_partner_of(agent_id=agent_id)
        self._log_in_background(
            events=self._events_of(agent_id=agent_id, round_number=round_number, turn=outcome.turn)
        )

    def _release_if_nothing_can_arrive(self, agent_id: str) -> None:
        """Release ``agent_id`` with a notice when its partner has finished or is parked too."""
        partner = PARTNER_OF[agent_id]
        partner_finished = self._world.is_finished(agent_id=partner)
        if not partner_finished and partner not in self.runtime.parked_waits():
            return
        if not self._world.claim_release(agent_id=agent_id, limit=RELEASE_LIMIT):
            return
        self.runtime.release_wait(
            agent_id=agent_id,
            detail=self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={"partner_finished": partner_finished},
            ),
        )

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
        """Put both players on the start square and log the round's grids."""
        if round_number <= self._started_round:
            return
        boards = self._boards[round_number - 1]
        self._world.start_round(boards=boards)
        self._started_round = round_number
        await self._log_events(
            events=[
                SignalGameRoundStarted(
                    round_number=round_number,
                    grids=boards.grids,
                    start_square=(START_SQUARE.row, START_SQUARE.col),
                    moves_per_round=self._knobs.moves_per_round,
                    partner_colours_visible=self._knobs.partner_colours_visible,
                )
            ]
        )

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once neither player can move."""
        if self._world.both_finished():
            return BOTH_FINISHED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the squares the players stand on."""
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            outcome = self._world.resolve(round_number=round_number, trigger=trigger)
            await self.runtime.event_logger.log(
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
                )
            )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both players finished on the same colour. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        reason = ", ".join(
            f"{agent_id}={outcome.final_colours[agent_id]}" for agent_id in AGENT_IDS
        )
        return [RoundResult(success=outcome.success, team_id=None, reason=reason)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds, so the first briefing after a fork reports the last result."""
        for event in events:
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
                    )
                )
                self._started_round = max(self._started_round, event.round_number)

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Each round's move traces, with both grids as the ground truth."""
        return build_communication_rounds(events=events)

    def get_tools(self) -> list[ScenarioTool]:
        """``move`` and ``observe``; a player is offered observe only when it is enabled."""

        async def move(
            agent_id: str,
            directions: Annotated[
                list[Direction], Field(min_length=1, max_length=MAX_MOVES_PER_CALL)
            ],
        ) -> str:
            return await self._move(agent_id=agent_id, directions=directions)

        async def observe(agent_id: str) -> str:
            self._open_round_for(agent_id=agent_id)
            self._world.start_observing(agent_id=agent_id)
            return self._board_view(agent_id=agent_id, result="Board.", whole_round=True)

        move_description = MOVE_DESCRIPTION
        if self._knobs.turn_based:
            move_description = MOVE_DESCRIPTION + TURN_BASED_MOVE_DESCRIPTION
        return [
            ScenarioTool(name=MOVE_TOOL, description=move_description, executor=move),
            ScenarioTool(name=OBSERVE_TOOL, description=OBSERVE_DESCRIPTION, executor=observe),
        ]

    async def _move(self, agent_id: str, directions: list[Direction]) -> str:
        """Apply one ``move`` call, wake the partner, and log its steps.

        Under ``turn_based`` a call made with partner actions still unseen is
        refused with the board, so every accepted move answers what the player saw.
        """
        round_number = self._open_round_for(agent_id=agent_id)
        if (
            self._knobs.turn_based
            and self._world.move_refusal(agent_id=agent_id) is None
            and self._world.has_unseen(agent_id=agent_id)
        ):
            raise ValueError(
                self._board_view(
                    agent_id=agent_id,
                    result=self._renderer.render(
                        template_name=UNSEEN_REFUSAL_TEMPLATE, template_variables={}
                    ),
                    whole_round=False,
                )
            )
        outcome = self._world.move(agent_id=agent_id, directions=directions)
        view = self._board_view(
            agent_id=agent_id,
            result=self._renderer.render(
                template_name=MOVE_RESULT_TEMPLATE,
                template_variables={
                    "number": outcome.turn.number,
                    "directions": [applied.direction.value for applied in outcome.turn.steps],
                    "square": outcome.turn.square.label(),
                    "stopped": outcome.stopped,
                    "requested": len(directions),
                },
            ),
            whole_round=False,
        )
        self._wake_partner_of(agent_id=agent_id)
        await self._log_events(
            events=self._events_of(agent_id=agent_id, round_number=round_number, turn=outcome.turn)
        )
        return view

    def _events_of(self, agent_id: str, round_number: int, turn: Turn) -> list[EventBase]:
        return turn_events(
            round_number=round_number,
            turn=turn,
            moves_used=self._knobs.moves_per_round - self._world.moves_left(agent_id=agent_id),
            grid=self._world.boards.grids[agent_id],
        )

    def _wake_partner_of(self, agent_id: str) -> None:
        """Resume ``agent_id``'s partner if it is waiting for an action, so it sees this one.

        A partner that is not parked sees the action in its next result, and one
        that parks before then is resumed by ``on_agent_parked``.
        """
        partner = PARTNER_OF[agent_id]
        wait = self.runtime.parked_waits().get(partner)
        if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
            self.runtime.release_wait(agent_id=partner, detail=PARTNER_ACTED)

    def _board_view(self, agent_id: str, result: str, whole_round: bool) -> str:
        """The board from ``agent_id``'s side, marking the partner's actions shown.

        Lists the partner's actions not yet shown, or every one of the round when
        ``whole_round`` is set, whether both players are observing, and whose turn it is.
        """
        partner = PARTNER_OF[agent_id]
        boards = self._world.boards
        own_square = self._world.square_of(agent_id=agent_id)
        partner_square = self._world.square_of(agent_id=partner)
        partner_colour: str | None = None
        if self._knobs.partner_colours_visible:
            partner_colour = colour_at(grid=boards.grids[partner], square=partner_square)
        if whole_round:
            partner_turns = self._world.take_round(agent_id=agent_id)
        else:
            partner_turns = self._world.take_unseen(agent_id=agent_id)
        turn_state: str | None = None
        state = self._world.turn_state(agent_id=agent_id)
        if state is not None:
            turn_state = state.value
        return self._renderer.render(
            template_name=BOARD_TEMPLATE,
            template_variables={
                "result": result,
                "round_number": boards.round_number,
                "own_square": own_square.label(),
                "own_colour": colour_at(grid=boards.grids[agent_id], square=own_square),
                "own_ended": self._world.has_ended(agent_id=agent_id),
                "partner_square": partner_square.label(),
                "partner_colour": partner_colour,
                "partner_ended": self._world.has_ended(agent_id=partner),
                "partner_actions": [_shown(turn=turn) for turn in partner_turns],
                "whole_round": whole_round,
                "both_observing": self._world.is_observing(agent_id=agent_id)
                and self._world.is_observing(agent_id=partner),
                "turn_state": turn_state,
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

    async def _log_events(self, events: list[EventBase]) -> None:
        """Log ``events`` in order, behind any events already waiting to be logged."""
        async with self._lock:
            for event in events:
                await self.runtime.event_logger.log(event=event)

    def _log_in_background(self, events: list[EventBase]) -> None:
        """Log ``events`` from a synchronous hook, in the order the hook ran."""
        task = asyncio.get_running_loop().create_task(self._log_events(events=events))
        self._background_logs.add(task)
        task.add_done_callback(self._on_background_log_done)

    def _on_background_log_done(self, task: asyncio.Task[None]) -> None:
        self._background_logs.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("signal_game could not log a turn's events")
