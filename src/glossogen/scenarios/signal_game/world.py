"""Round state for signal_game: where each player stands, the moves both made, and verdicts.

Every move and every end_round goes into one ordered log per round. Each player
has a read position in it, so a tool result or a wake shows the partner's
actions it has not yet shown, in the order they happened.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.signal_game.board import (
    RoundBoards,
    Square,
    colour_at,
    step,
)
from glossogen.scenarios.signal_game.events import SignalGameCheat
from glossogen.scenarios.signal_game.ids import AGENT_IDS, END_ROUND_TOOL, Direction


class LoggedAction(NamedTuple):
    """One entry of a round's log: a move (``action`` is its direction) or an end_round."""

    sequence: int
    agent_id: str
    action: str
    from_square: Square
    square: Square


class RoundOutcome(NamedTuple):
    """A resolved round. ``success`` needs matching colours and no ``cheats``."""

    round_number: int
    final_squares: dict[str, Square]
    final_colours: dict[str, str]
    moves_used: dict[str, int]
    success: bool
    trigger: str
    cheats: list[SignalGameCheat]


class _OpenRound(NamedTuple):
    boards: RoundBoards
    squares: dict[str, Square]
    moves_used: dict[str, int]
    ended: set[str]
    log: list[LoggedAction]
    shown_up_to: dict[str, int]
    releases: dict[str, int]


class SignalGameWorld(ScenarioWorld):
    """The open round's positions, moves and log, and every resolved round's outcome."""

    def __init__(self, grid_size: int, moves_per_round: int) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._grid_size = grid_size
        self._moves_per_round = moves_per_round
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, boards: RoundBoards) -> None:
        """Put each player on its start square with a full move budget."""
        self._open = _OpenRound(
            boards=boards,
            squares=dict(boards.starts),
            moves_used=dict.fromkeys(AGENT_IDS, 0),
            ended=set(),
            log=[],
            shown_up_to=dict.fromkeys(AGENT_IDS, 0),
            releases=dict.fromkeys(AGENT_IDS, 0),
        )

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
        """Whether ``agent_id`` called end_round this round."""
        return agent_id in self._round().ended

    def is_finished(self, agent_id: str) -> bool:
        """Whether ``agent_id`` can no longer move: it ended the round or spent every move."""
        return self.has_ended(agent_id=agent_id) or self.moves_left(agent_id=agent_id) <= 0

    def both_finished(self) -> bool:
        """Whether neither player can move again this round."""
        return self._open is not None and all(
            self.is_finished(agent_id=agent_id) for agent_id in AGENT_IDS
        )

    def move_refusal(self, agent_id: str, direction: Direction) -> str | None:
        """Why ``agent_id`` cannot move ``direction`` now, or None when it can."""
        state = self._round()
        if agent_id in state.ended:
            return "You ended this round; your square is final."
        if self.moves_left(agent_id=agent_id) <= 0:
            return "You have no moves left this round. Call end_round."
        here = state.squares[agent_id]
        if step(square=here, direction=direction, grid_size=self._grid_size) is None:
            return (
                f"Moving {direction.value} from {here.label()} leaves the grid. No move was spent."
            )
        return None

    def move(self, agent_id: str, direction: Direction) -> LoggedAction:
        """Apply one move; raises ``ValueError`` when ``move_refusal`` gives a reason."""
        refusal = self.move_refusal(agent_id=agent_id, direction=direction)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        here = state.squares[agent_id]
        there = step(square=here, direction=direction, grid_size=self._grid_size)
        assert there is not None
        state.squares[agent_id] = there
        state.moves_used[agent_id] += 1
        return self._append(agent_id=agent_id, action=direction.value, from_square=here)

    def end(self, agent_id: str) -> LoggedAction:
        """Fix ``agent_id``'s square for the round; raises ``ValueError`` on a second call."""
        state = self._round()
        if agent_id in state.ended:
            raise ValueError("You already ended this round.")
        state.ended.add(agent_id)
        return self._append(
            agent_id=agent_id, action=END_ROUND_TOOL, from_square=state.squares[agent_id]
        )

    def end_on(self, agent_id: str, square: Square) -> LoggedAction:
        """Fix ``agent_id``'s square for the round at ``square``, with no moves.

        Raises ``ValueError`` when ``square`` is off the grid or on a second call.
        """
        state = self._round()
        if agent_id in state.ended:
            raise ValueError("You already ended this round.")
        if not (1 <= square.row <= self._grid_size and 1 <= square.col <= self._grid_size):
            raise ValueError(
                f"Rows and columns run from 1 to {self._grid_size}. The round was not ended."
            )
        state.squares[agent_id] = square
        return self.end(agent_id=agent_id)

    def _append(self, agent_id: str, action: str, from_square: Square) -> LoggedAction:
        state = self._round()
        entry = LoggedAction(
            sequence=len(state.log) + 1,
            agent_id=agent_id,
            action=action,
            from_square=from_square,
            square=state.squares[agent_id],
        )
        state.log.append(entry)
        return entry

    def take_unseen(self, agent_id: str) -> list[LoggedAction]:
        """The partner's actions not yet shown to ``agent_id``, marking them shown.

        The read position covers the whole log, so the agent's own actions pass
        it without being returned.
        """
        if self._open is None:
            return []
        state = self._open
        unseen = [
            entry
            for entry in state.log[state.shown_up_to[agent_id] :]
            if entry.agent_id != agent_id
        ]
        state.shown_up_to[agent_id] = len(state.log)
        return unseen

    def has_unseen(self, agent_id: str) -> bool:
        """Whether the partner has acted since ``agent_id`` was last shown the board."""
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

    def resolve(
        self, round_number: int, trigger: str, cheats: list[SignalGameCheat]
    ) -> RoundOutcome:
        """Close the round: the colour under each player decides it, unless it was cheated."""
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
            success=len(set(final_colours.values())) == 1 and not cheats,
            trigger=trigger,
            cheats=cheats,
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
        """Rounds that scored."""
        return sum(outcome.success for outcome in self._outcomes.values())

    def cheated_round(self) -> int | None:
        """The first resolved round the plaintext judge took, or None."""
        cheated = [number for number, outcome in self._outcomes.items() if outcome.cheats]
        if not cheated:
            return None
        return min(cheated)
