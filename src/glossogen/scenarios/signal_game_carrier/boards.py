"""The grids signal_game_carrier deals: squares, colours and the per-round draw.

Squares are ``(row, col)`` pairs counted from 1 at the top left, which is how agents
read them. Each player's grid is private; the pair always shares at least one colour,
so every round can be won.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.signal_game_carrier.ids import AGENT_IDS, PALETTE


class Square(NamedTuple):
    """A square on a grid, 1-based."""

    row: int
    col: int

    def label(self) -> str:
        """The square as agents read it."""
        return f"row {self.row}, col {self.col}"


def colour_at(grid: list[list[str]], square: Square) -> str:
    """The colour of ``square`` on ``grid``."""
    return grid[square.row - 1][square.col - 1]


def off_grid(square: Square, grid_size: int) -> bool:
    """Whether ``square`` falls outside a grid of ``grid_size`` squares a side."""
    return not (1 <= square.row <= grid_size and 1 <= square.col <= grid_size)


def draw_grids(rng: random.Random, grid_size: int, colour_count: int) -> dict[str, list[list[str]]]:
    """One grid per player, redrawn until the two share a colour.

    Each square is coloured independently from the first ``colour_count`` colours, so a
    colour can repeat on a grid or be missing from it.
    """
    colours = PALETTE[:colour_count]
    while True:
        grids = {
            agent_id: [[rng.choice(colours) for _ in range(grid_size)] for _ in range(grid_size)]
            for agent_id in AGENT_IDS
        }
        held = [{colour for row in grids[agent_id] for colour in row} for agent_id in AGENT_IDS]
        if held[0] & held[1]:
            return grids
