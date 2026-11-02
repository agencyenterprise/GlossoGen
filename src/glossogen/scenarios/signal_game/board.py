"""Grids, squares and moves: the geometry of signal_game, with no runtime state.

A square holds an item: a colour, a colour and a shape written ``"red circle"``, a
fill, a colour and a shape written ``"striped red circle"``, or a word. Also each player's colour,
shape and fill orders: the orders its prompt lists them in.

Squares are ``(row, col)`` pairs counted from 1 at the top left, which is how
agents read them. ``up`` lowers the row and ``left`` lowers the column.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.signal_game.ids import AGENT_IDS, FILLS, PALETTE, SHAPES, Direction
from glossogen.scenarios.signal_game.word_list import WORDS

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

    ``grids[agent_id][row - 1][col - 1]`` is an item; ``starts[agent_id]`` is
    where that player's figure begins the round.
    """

    round_number: int
    grids: dict[str, list[list[str]]]
    starts: dict[str, Square]


def item_at(grid: list[list[str]], square: Square) -> str:
    """The item on ``square`` of ``grid``."""
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


def shape_order(seed: int, shape_count: int, agent_id: str) -> list[str]:
    """The first ``shape_count`` shapes in the order ``agent_id`` reads them.

    Shuffled by a generator of its own, seeded from ``seed`` and the player, so it is
    independent of the partner's shape order and of both colour orders.
    """
    order = list(SHAPES[:shape_count])
    random.Random(f"signal_game shape order {seed} {agent_id}").shuffle(order)
    return order


def fill_order(seed: int, fill_count: int, agent_id: str) -> list[str]:
    """The first ``fill_count`` fills in the order ``agent_id`` reads them.

    Shuffled by a generator of its own, seeded from ``seed`` and the player, so it is
    independent of every other order.
    """
    order = list(FILLS[:fill_count])
    random.Random(f"signal_game fill order {seed} {agent_id}").shuffle(order)
    return order


class ItemParts(NamedTuple):
    """An item's parts. A word item has only ``word``; any other has ``colour``, and
    ``shape`` and ``fill`` when the run's items have them."""

    colour: str | None
    shape: str | None
    fill: str | None
    word: str | None


_WORD_SET = frozenset(WORDS)


def item_parts(item: str) -> ItemParts:
    """Split ``"striped red circle"``, ``"red circle"``, ``"red"`` or a word into its parts."""
    if item in _WORD_SET:
        return ItemParts(colour=None, shape=None, fill=None, word=item)
    words = item.split(" ")
    fill: str | None = None
    if words[0] in FILLS:
        fill = words.pop(0)
    shape: str | None = None
    if len(words) > 1:
        shape = words[1]
    return ItemParts(colour=words[0], shape=shape, fill=fill, word=None)


def items(colour_count: int, shape_count: int, fill_count: int) -> list[str]:
    """Every item a square can hold: each colour, each colour with each shape, or each
    fill with each colour and shape."""
    colours = PALETTE[:colour_count]
    if shape_count == 0:
        return list(colours)
    coloured_shapes = [f"{colour} {shape}" for colour in colours for shape in SHAPES[:shape_count]]
    if fill_count == 0:
        return coloured_shapes
    return [f"{fill} {item}" for fill in FILLS[:fill_count] for item in coloured_shapes]


def _draw_grid(
    rng: random.Random, choices: list[str], vocabulary: list[str], grid_size: int
) -> list[list[str]]:
    """One grid: different words when the run has a vocabulary, else an item per square
    drawn independently from ``choices``, repeats allowed."""
    if vocabulary:
        drawn = rng.sample(vocabulary, grid_size * grid_size)
        return [drawn[row * grid_size : (row + 1) * grid_size] for row in range(grid_size)]
    return [[rng.choice(choices) for _ in range(grid_size)] for _ in range(grid_size)]


def generate_boards(
    seed: int,
    round_count: int,
    grid_size: int,
    colour_count: int,
    shape_count: int,
    fill_count: int,
    word_count: int,
) -> list[RoundBoards]:
    """Every round's grids and start squares, drawn from ``seed``.

    Each square's item is drawn independently from ``items``, so an item can
    repeat on a grid or be missing from it. A pair of grids sharing no item is
    drawn again, so every round can be won. With no shapes the items are the
    colours, and a seed draws the boards it drew before shapes existed; with shapes
    and no fills, the boards it drew before fills existed.

    With words, each grid holds different words, drawn from the first ``word_count``
    words of the vocabulary, again redrawn until the two grids share one.

    Each player's start square is drawn separately, uniformly over its grid, as
    in the paper. Starts come from their own generator, so a seed gives the
    grids it gave before starts were random, and a round's start does not
    depend on ``round_count``.
    """
    rng = random.Random(seed)
    start_rng = random.Random(f"signal_game starts {seed}")
    choices = items(colour_count=colour_count, shape_count=shape_count, fill_count=fill_count)
    vocabulary = list(WORDS[:word_count])
    boards: list[RoundBoards] = []
    for round_number in range(1, round_count + 1):
        while True:
            grids = {
                agent_id: _draw_grid(
                    rng=rng, choices=choices, vocabulary=vocabulary, grid_size=grid_size
                )
                for agent_id in AGENT_IDS
            }
            first, second = (
                {item for row in grids[agent_id] for item in row} for agent_id in AGENT_IDS
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
