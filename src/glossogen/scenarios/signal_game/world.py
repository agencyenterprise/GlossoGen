"""Round state for signal_game: where each player stands, the turns both took, and verdicts.

Every ``move`` call, every passed turn and every finish goes into one ordered log
per round as a ``Turn``. Each player has a read position in it, so a tool result
or a wake shows the partner's turns it has not yet shown, in the order they
happened. Every change here is synchronous, so one ``move`` call's steps are
applied together and nothing lands between them.

Under ``turn_based`` the world also holds the turn. Whoever moves first takes the
round's first turn; after that a ``move`` call hands the turn to the partner, and
a player whose partner has finished moves freely.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.signal_game.board import (
    START_SQUARE,
    RoundBoards,
    Square,
    colour_at,
    step,
)
from glossogen.scenarios.signal_game.ids import (
    AGENT_IDS,
    PARTNER_OF,
    Direction,
    TurnKind,
    TurnState,
)


class AppliedStep(NamedTuple):
    """One square-to-square step. ``sequence`` orders both players' steps in the round."""

    sequence: int
    direction: Direction
    from_square: Square
    square: Square


class Turn(NamedTuple):
    """One entry of a round's log.

    ``number`` counts the player's own turns in the round from 1. ``steps`` is
    empty for a wait or a finish, and ``square`` is where the player stood after it.
    """

    number: int
    agent_id: str
    kind: TurnKind
    steps: list[AppliedStep]
    square: Square


class MoveOutcome(NamedTuple):
    """A ``move`` call that applied at least one step, and why it stopped early, if it did."""

    turn: Turn
    stopped: str | None


class PassOutcome(NamedTuple):
    """A passed turn. ``answers_a_pass`` is set when the partner's last turn was a pass too."""

    turn: Turn
    answers_a_pass: bool


class RoundOutcome(NamedTuple):
    """A resolved round."""

    round_number: int
    final_squares: dict[str, Square]
    final_colours: dict[str, str]
    moves_used: dict[str, int]
    success: bool
    trigger: str


class _OpenRound:
    """The mutable state of the round in progress."""

    def __init__(self, boards: RoundBoards) -> None:
        self.boards = boards
        self.squares = dict.fromkeys(AGENT_IDS, START_SQUARE)
        self.moves_used = dict.fromkeys(AGENT_IDS, 0)
        self.ended: set[str] = set()
        self.log: list[Turn] = []
        self.step_count = 0
        self.shown_up_to = dict.fromkeys(AGENT_IDS, 0)
        self.releases = dict.fromkeys(AGENT_IDS, 0)
        self.turn_holder: str | None = None
        self.observing: set[str] = set()


class SignalGameWorld(ScenarioWorld):
    """The open round's positions, turns and log, and every resolved round's outcome."""

    def __init__(self, grid_size: int, moves_per_round: int, turn_based: bool) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._grid_size = grid_size
        self._moves_per_round = moves_per_round
        self._turn_based = turn_based
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, boards: RoundBoards) -> None:
        """Put both players on the start square with a full move budget and no turn taken."""
        self._open = _OpenRound(boards=boards)

    @property
    def round_open(self) -> bool:
        """Whether a round has started and has not been resolved."""
        return self._open is not None

    def _round(self) -> _OpenRound:
        if self._open is None:
            raise ValueError("No round is in progress.")
        return self._open

    @property
    def boards(self) -> RoundBoards:
        """The open round's grids."""
        return self._round().boards

    def square_of(self, agent_id: str) -> Square:
        """Where ``agent_id`` stands now."""
        return self._round().squares[agent_id]

    def moves_left(self, agent_id: str) -> int:
        """Moves ``agent_id`` may still make this round."""
        return self._moves_per_round - self._round().moves_used[agent_id]

    def has_ended(self, agent_id: str) -> bool:
        """Whether ``agent_id`` finished this round."""
        return agent_id in self._round().ended

    def is_finished(self, agent_id: str) -> bool:
        """Whether ``agent_id`` can no longer move: it finished the round or spent every move."""
        return self.has_ended(agent_id=agent_id) or self.moves_left(agent_id=agent_id) <= 0

    def both_finished(self) -> bool:
        """Whether neither player can move again this round."""
        return self._open is not None and all(
            self.is_finished(agent_id=agent_id) for agent_id in AGENT_IDS
        )

    def move_refusal(self, agent_id: str) -> str | None:
        """Why ``agent_id`` cannot make a ``move`` call now, or None when it can."""
        state = self._round()
        if agent_id in state.ended:
            return "You finished this round; your square is final."
        if self.moves_left(agent_id=agent_id) <= 0:
            return (
                "You have no moves left this round. Call "
                "read_notifications(wait_for='next_round') to finish."
            )
        if state.turn_holder == PARTNER_OF[agent_id]:
            return (
                "It is your partner's turn. Call read_notifications(wait_for='message') "
                "to wait for it. Nothing was moved."
            )
        return None

    def move(self, agent_id: str, directions: list[Direction]) -> MoveOutcome:
        """Apply ``directions`` in order until one leaves the grid or the moves run out.

        Raises ``ValueError`` when ``move_refusal`` gives a reason or the first step
        is refused; neither uses a turn.
        """
        refusal = self.move_refusal(agent_id=agent_id)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        steps: list[AppliedStep] = []
        stopped: str | None = None
        for direction in directions:
            stopped = self._step_refusal(agent_id=agent_id, direction=direction)
            if stopped is not None:
                break
            steps.append(self._apply(agent_id=agent_id, direction=direction))
        if not steps:
            assert stopped is not None
            raise ValueError(f"{stopped} Nothing was moved.")
        turn = self._record(agent_id=agent_id, kind=TurnKind.MOVE, steps=steps)
        if self._turn_based:
            state.turn_holder = PARTNER_OF[agent_id]
            if self.is_finished(agent_id=agent_id) or self.is_finished(
                agent_id=PARTNER_OF[agent_id]
            ):
                state.turn_holder = None
        return MoveOutcome(turn=turn, stopped=stopped)

    def _step_refusal(self, agent_id: str, direction: Direction) -> str | None:
        if self.moves_left(agent_id=agent_id) <= 0:
            return "You have no moves left this round."
        here = self._round().squares[agent_id]
        if step(square=here, direction=direction, grid_size=self._grid_size) is None:
            return f"Moving {direction.value} from {here.label()} leaves the grid."
        return None

    def _apply(self, agent_id: str, direction: Direction) -> AppliedStep:
        state = self._round()
        here = state.squares[agent_id]
        there = step(square=here, direction=direction, grid_size=self._grid_size)
        assert there is not None
        state.squares[agent_id] = there
        state.moves_used[agent_id] += 1
        state.step_count += 1
        return AppliedStep(
            sequence=state.step_count, direction=direction, from_square=here, square=there
        )

    def finish(self, agent_id: str) -> Turn:
        """Fix ``agent_id``'s square for the round; raises ``ValueError`` on a second call."""
        state = self._round()
        if agent_id in state.ended:
            raise ValueError("You already finished this round.")
        state.ended.add(agent_id)
        state.turn_holder = None
        return self._record(agent_id=agent_id, kind=TurnKind.FINISH, steps=[])

    def holds_turn(self, agent_id: str) -> bool:
        """Whether ``agent_id`` holds the turn under ``turn_based``."""
        return self._open is not None and self._open.turn_holder == agent_id

    def pass_turn(self, agent_id: str) -> PassOutcome:
        """Hand the turn ``agent_id`` holds to its partner without moving."""
        state = self._round()
        if state.turn_holder != agent_id:
            raise ValueError("It is not your turn.")
        partner = PARTNER_OF[agent_id]
        answers_a_pass = False
        if state.log:
            previous = state.log[-1]
            answers_a_pass = previous.agent_id == partner and previous.kind is TurnKind.WAIT
        turn = self._record(agent_id=agent_id, kind=TurnKind.WAIT, steps=[])
        state.turn_holder = partner
        return PassOutcome(turn=turn, answers_a_pass=answers_a_pass)

    def turn_state(self, agent_id: str) -> TurnState | None:
        """Who may act next from ``agent_id``'s side, or None without turns or once it finished."""
        if not self._turn_based or self.is_finished(agent_id=agent_id):
            return None
        holder = self._round().turn_holder
        if holder == agent_id:
            return TurnState.YOURS
        if holder is not None:
            return TurnState.PARTNERS
        if self.is_finished(agent_id=PARTNER_OF[agent_id]):
            return TurnState.FREE
        return TurnState.OPEN

    def _record(self, agent_id: str, kind: TurnKind, steps: list[AppliedStep]) -> Turn:
        state = self._round()
        turn = Turn(
            number=sum(1 for entry in state.log if entry.agent_id == agent_id) + 1,
            agent_id=agent_id,
            kind=kind,
            steps=steps,
            square=state.squares[agent_id],
        )
        state.log.append(turn)
        state.observing.discard(agent_id)
        return turn

    def start_observing(self, agent_id: str) -> None:
        """Mark ``agent_id`` as observing until it next acts or waits."""
        self._round().observing.add(agent_id)

    def stop_observing(self, agent_id: str) -> None:
        """Clear ``agent_id``'s observing mark."""
        if self._open is not None:
            self._open.observing.discard(agent_id)

    def is_observing(self, agent_id: str) -> bool:
        """Whether ``agent_id``'s last call this round was ``observe``."""
        return self._open is not None and agent_id in self._open.observing

    def take_unseen(self, agent_id: str) -> list[Turn]:
        """The partner's turns not yet shown to ``agent_id``, marking them shown.

        The read position covers the whole log, so the agent's own turns pass it
        without being returned.
        """
        if self._open is None:
            return []
        return self._take_partner_turns(agent_id=agent_id, start=self._open.shown_up_to[agent_id])

    def take_round(self, agent_id: str) -> list[Turn]:
        """Every partner turn of the open round, marking them shown to ``agent_id``."""
        if self._open is None:
            return []
        return self._take_partner_turns(agent_id=agent_id, start=0)

    def _take_partner_turns(self, agent_id: str, start: int) -> list[Turn]:
        state = self._round()
        turns = [entry for entry in state.log[start:] if entry.agent_id != agent_id]
        state.shown_up_to[agent_id] = len(state.log)
        return turns

    def has_unseen(self, agent_id: str) -> bool:
        """Whether the partner has taken a turn since ``agent_id`` was last shown the board."""
        if self._open is None:
            return False
        state = self._open
        return any(entry.agent_id != agent_id for entry in state.log[state.shown_up_to[agent_id] :])

    def claim_release(self, agent_id: str, limit: int) -> bool:
        """Count one release of ``agent_id`` from a wait; False once ``limit`` are spent."""
        if self._open is None:
            return False
        releases = self._open.releases
        if releases[agent_id] >= limit:
            return False
        releases[agent_id] += 1
        return True

    def resolve(self, round_number: int, trigger: str) -> RoundOutcome:
        """Close the round: the colour under each player decides it."""
        state = self._round()
        final_colours = {
            agent_id: colour_at(grid=state.boards.grids[agent_id], square=square)
            for agent_id, square in state.squares.items()
        }
        outcome = RoundOutcome(
            round_number=round_number,
            final_squares=dict(state.squares),
            final_colours=final_colours,
            moves_used=dict(state.moves_used),
            success=len(set(final_colours.values())) == 1,
            trigger=trigger,
        )
        self._outcomes[round_number] = outcome
        self._open = None
        return outcome

    def outcome(self, round_number: int) -> RoundOutcome | None:
        """The resolved round, or None."""
        return self._outcomes.get(round_number)

    def seed_outcome(self, outcome: RoundOutcome) -> None:
        """Restore a round resolved before a fork or resume."""
        self._outcomes[outcome.round_number] = outcome

    def rounds_won(self) -> int:
        """Rounds resolved with matching colours."""
        return sum(outcome.success for outcome in self._outcomes.values())
