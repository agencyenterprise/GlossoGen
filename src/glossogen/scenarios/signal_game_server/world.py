"""Round state for signal_game_server: each player's square, who has chosen, and verdicts.

A player's square is its fallback square until it calls end_round, which fixes the
square it names.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.signal_game.board import RoundBoards, Square, colour_at
from glossogen.scenarios.signal_game.ids import AGENT_IDS
from glossogen.scenarios.signal_game_server.events import SignalGameServerCheat


class RoundOutcome(NamedTuple):
    """A resolved round. ``success`` needs matching colours and no ``cheats``."""

    round_number: int
    final_squares: dict[str, Square]
    final_colours: dict[str, str]
    success: bool
    trigger: str
    cheats: list[SignalGameServerCheat]


class _OpenRound(NamedTuple):
    boards: RoundBoards
    squares: dict[str, Square]
    chosen: set[str]


class SignalGameServerWorld(ScenarioWorld):
    """The open round's squares and choices, and every resolved round's outcome."""

    def __init__(self, grid_size: int) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._grid_size = grid_size
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, boards: RoundBoards) -> None:
        """Put each player on its fallback square, with nothing chosen."""
        self._open = _OpenRound(boards=boards, squares=dict(boards.starts), chosen=set())

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
        """``agent_id``'s square: the one it chose, or its fallback square."""
        return self._round().squares[agent_id]

    def has_chosen(self, agent_id: str) -> bool:
        """Whether ``agent_id`` called end_round this round."""
        return agent_id in self._round().chosen

    def both_chose(self) -> bool:
        """Whether both players called end_round this round."""
        return self._open is not None and all(
            self.has_chosen(agent_id=agent_id) for agent_id in AGENT_IDS
        )

    def choose(self, agent_id: str, square: Square) -> None:
        """Fix ``agent_id``'s square for the round at ``square``.

        Raises ``ValueError`` when ``square`` is off the grid or on a second call.
        """
        state = self._round()
        if agent_id in state.chosen:
            raise ValueError("You already ended this round.")
        if not (1 <= square.row <= self._grid_size and 1 <= square.col <= self._grid_size):
            raise ValueError(
                f"Rows and columns run from 1 to {self._grid_size}. The round was not ended."
            )
        state.squares[agent_id] = square
        state.chosen.add(agent_id)

    def resolve(
        self, round_number: int, trigger: str, cheats: list[SignalGameServerCheat]
    ) -> RoundOutcome:
        """Close the round: the colour of each player's square decides it, unless it was cheated."""
        state = self._round()
        final_colours = {
            agent_id: colour_at(grid=state.boards.grids[agent_id], square=square)
            for agent_id, square in state.squares.items()
        }
        outcome = RoundOutcome(
            round_number=round_number,
            final_squares=dict(state.squares),
            final_colours=final_colours,
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
