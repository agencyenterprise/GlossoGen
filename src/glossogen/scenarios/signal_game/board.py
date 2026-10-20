"""Grids, squares and moves: the geometry of signal_game, with no runtime state.

Also each player's colour order: the order its prompt lists the colours in.

Squares are ``(row, col)`` pairs counted from 1 at the top left, which is how
agents read them. ``up`` lowers the row and ``left`` lowers the column.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.signal_game.ids import AGENT_IDS, PALETTE, Direction

_STEPS: dict[Direction, tuple[int, int]] = {
    Direction.UP: (-1, 0),
    Direction.DOWN: (1, 0),
    Direction.LEFT: (0, -1),
    Direction.RIGHT: (0, 1),
}


class Square(NamedTuple):
    """A square on a grid, 1-based."""

    row: int
    col: int

    def label(self) -> str:
        """The square as agents read it."""
        return f"row {self.row}, col {self.col}"


class RoundBoards(NamedTuple):
    """Each player's grid and start square for one round.

    ``grids[agent_id][row - 1][col - 1]`` is a colour; ``starts[agent_id]`` is
    where that player's figure begins the round.
    """

    round_number: int
    grids: dict[str, list[list[str]]]
    starts: dict[str, Square]


def colour_at(grid: list[list[str]], square: Square) -> str:
    """The colour of ``square`` on ``grid``."""
    return grid[square.row - 1][square.col - 1]


def step(square: Square, direction: Direction, grid_size: int) -> Square | None:
    """The square ``direction`` leads to, or None when it leaves the grid."""
    row_step, col_step = _STEPS[direction]
    row = square.row + row_step
    col = square.col + col_step
    if not (1 <= row <= grid_size and 1 <= col <= grid_size):
        return None
    return Square(row=row, col=col)


def path_length(start: Square, end: Square) -> int:
    """The fewest moves from ``start`` to ``end``: their Manhattan distance."""
    return abs(start.row - end.row) + abs(start.col - end.col)


def colour_order(seed: int, colour_count: int, agent_id: str) -> list[str]:
    """The first ``colour_count`` colours of the palette in the order ``agent_id`` reads them.

    Each player's order is shuffled by a generator of its own, seeded from ``seed`` and
    the player, so the two orders are independent of each other and of the boards.
    """
    order = list(PALETTE[:colour_count])
    random.Random(f"signal_game colour order {seed} {agent_id}").shuffle(order)
    return order


def generate_boards(
    seed: int, round_count: int, grid_size: int, colour_count: int
) -> list[RoundBoards]:
    """Every round's grids and start squares, drawn from ``seed``.

    Each square is coloured independently from the first ``colour_count``
    colours, so a colour can repeat on a grid or be missing from it. A pair of
    grids sharing no colour is drawn again, so every round can be won.

    Each player's start square is drawn separately, uniformly over its grid, as
    in the paper. Starts come from their own generator, so a seed gives the
    grids it gave before starts were random, and a round's start does not
    depend on ``round_count``.
    """
    rng = random.Random(seed)
    start_rng = random.Random(f"signal_game starts {seed}")
    colours = PALETTE[:colour_count]
    boards: list[RoundBoards] = []
    for round_number in range(1, round_count + 1):
        while True:
            grids = {
                agent_id: [
                    [rng.choice(colours) for _ in range(grid_size)] for _ in range(grid_size)
                ]
                for agent_id in AGENT_IDS
            }
            first, second = (
                {colour for row in grids[agent_id] for colour in row} for agent_id in AGENT_IDS
            )
            if first & second:
                break
        starts = {
            agent_id: Square(
                row=start_rng.randint(1, grid_size), col=start_rng.randint(1, grid_size)
            )
            for agent_id in AGENT_IDS
        }
        boards.append(RoundBoards(round_number=round_number, grids=grids, starts=starts))
    return boards
