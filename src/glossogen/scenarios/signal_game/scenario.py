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
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import SCENARIO_TOOL_TIMEOUT_SECONDS, ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.signal_game.board import (
    Square,
    colour_at,
    generate_boards,
)
from glossogen.scenarios.signal_game.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.signal_game.evaluation.excess_moves_metric import ExcessMovesMetric
from glossogen.scenarios.signal_game.evaluation.longest_streak_metric import LongestStreakMetric
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGamePlayerFinished,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
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
    PALETTE,
    PARTNER_OF,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    SYSTEM_TEMPLATE,
    Direction,
)
from glossogen.scenarios.signal_game.knobs import SignalGameKnobs
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
MOVE_WITH_REASONING_DESCRIPTION = (
    f"{MOVE_DESCRIPTION} reasoning is one sentence on why you are moving this way; your "
    "partner never sees it."
)
END_ROUND_DESCRIPTION = (
    "Finish this round on the square you are on. Your square cannot change after this. "
    "Returns the board."
)
END_ROUND_WITH_REASONING_DESCRIPTION = (
    f"{END_ROUND_DESCRIPTION} reasoning is one sentence on why you are finishing on this "
    "square; your partner never sees it."
)
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "during a round it waits until your partner acts, then returns the board with its "
    "actions. read_notifications(wait_for='next_round') declares you are done with this round "
    "and waits for the next briefing. The result is a wake package: the reasons, any "
    "briefings, the board, and a notice when the wait was cut short; type done ends the game. "
    "Must be the only tool call in its response."
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
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """The metrics that only read signal_game runs."""
        return (ExcessMovesMetric, LongestStreakMetric)

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
        self._lock = asyncio.Lock()
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
        """Return the round state: positions, moves, verdicts."""
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
        """One agent per player, in no channel, offered only move and end_round."""
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(),
                channel_ids=[],
                tool_names=[MOVE_TOOL, END_ROUND_TOOL],
                model=default_model,
                provider=Provider(default_provider),
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self) -> str:
        """The rules. Both players read the same text: the game is symmetric."""
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "colours": list(PALETTE[: self._knobs.colour_count]),
                "partner_colours_visible": self._knobs.partner_colours_visible,
                "moves_per_round": self._knobs.moves_per_round,
                "max_moves_per_call": MAX_MOVES_PER_CALL,
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
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
                    "move_reasoning": self._knobs.move_reasoning,
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
        """
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
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Put each player on its start square and log the round's grids and starts."""
        if round_number <= self._started_round:
            return
        boards = self._boards[round_number - 1]
        self._world.start_round(boards=boards)
        self._started_round = round_number
        await self._log_event(
            event=SignalGameRoundStarted(
                round_number=round_number,
                grids=boards.grids,
                start_squares={
                    agent_id: (square.row, square.col) for agent_id, square in boards.starts.items()
                },
                moves_per_round=self._knobs.moves_per_round,
                partner_colours_visible=self._knobs.partner_colours_visible,
            )
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
        """``move`` and ``end_round``; under ``move_reasoning`` each takes a ``reasoning``."""

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
            if not reasoning.strip():
                raise ValueError(
                    "Give one sentence of reasoning for ending the round. The round was not "
                    "ended."
                )
            return await finish_round(agent_id=agent_id, reasoning=reasoning.strip())

        async def end_round(agent_id: str) -> str:
            return await finish_round(agent_id=agent_id, reasoning=None)

        async def finish_round(agent_id: str, reasoning: str | None) -> str:
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.end(agent_id=agent_id)
                grid = self._world.boards.grids[agent_id]
                await self._log_event(
                    event=SignalGamePlayerFinished(
                        round_number=round_number,
                        agent_id=agent_id,
                        square=(entry.square.row, entry.square.col),
                        colour=colour_at(grid=grid, square=entry.square),
                        moves_used=self._knobs.moves_per_round
                        - self._world.moves_left(agent_id=agent_id),
                        reasoning=reasoning,
                    )
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
                    description=MOVE_WITH_REASONING_DESCRIPTION,
                    executor=move_with_reasoning,
                    timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
                ),
                ScenarioTool(
                    name=END_ROUND_TOOL,
                    description=END_ROUND_WITH_REASONING_DESCRIPTION,
                    executor=end_round_with_reasoning,
                    timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
                ),
            ]
        return [
            ScenarioTool(
                name=MOVE_TOOL,
                description=MOVE_DESCRIPTION,
                executor=move,
                timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
            ),
            ScenarioTool(
                name=END_ROUND_TOOL,
                description=END_ROUND_DESCRIPTION,
                executor=end_round,
                timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
            ),
        ]

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
        that parks before then is resumed by ``on_agent_parked``.
        """
        partner = PARTNER_OF[agent_id]
        wait = self.runtime.parked_waits().get(partner)
        if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
            self.runtime.release_wait(agent_id=partner, detail=PARTNER_ACTED)

    def _board_view(self, agent_id: str, result: str) -> str:
        """The board from ``agent_id``'s side, marking the partner's actions shown."""
        partner = PARTNER_OF[agent_id]
        boards = self._world.boards
        own_square = self._world.square_of(agent_id=agent_id)
        partner_square = self._world.square_of(agent_id=partner)
        partner_colour: str | None = None
        if self._knobs.partner_colours_visible:
            partner_colour = colour_at(grid=boards.grids[partner], square=partner_square)
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
                "partner_actions": [
                    _shown(entry=entry) for entry in self._world.take_unseen(agent_id=agent_id)
                ],
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


def _shown(entry: LoggedAction) -> ShownAction:
    return ShownAction(sequence=entry.sequence, action=entry.action, square=entry.square.label())
