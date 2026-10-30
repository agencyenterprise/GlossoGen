"""The depot floor: cells, bays, each operator's assigned bays and pallets.

No runtime state. The bays stand on the same squares for both operators, so a
bay number means the same thing to both. What differs is which bays each
operator may use: the depot assigns each a set, and with ``bays_differ`` exactly
one bay is on both lists. Neither operator is told the other's list.

Pallets are separate from that. They never close a bay, they only force a crate
to go around, and ``pallet_density`` decides how many a floor holds. A layout is
kept only when every bay is still reachable from that operator's own start.

Cells are ``(row, col)`` pairs counted from 1 at the top left, which is how
operators read them. ``up`` lowers the row and ``left`` lowers the column.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.move_a_box.ids import (
    CORNER_CELL,
    CrateStart,
    Direction,
)

_STEPS: dict[Direction, tuple[int, int]] = {
    Direction.UP: (-1, 0),
    Direction.DOWN: (1, 0),
    Direction.LEFT: (0, -1),
    Direction.RIGHT: (0, 1),
}

MIN_BAY_SEPARATION = 2
"""Fewest squares between two bays, so no two share an approach square."""

MIN_START_SEPARATION = 2
"""Fewest squares between a crate's start square and any bay."""

LAYOUT_ATTEMPTS = 2000
"""Draws allowed for one round's layout before the knobs are declared unsatisfiable."""


class Cell(NamedTuple):
    """A square of the depot floor, 1-based."""

    row: int
    col: int

    def label(self) -> str:
        """The square as operators read it: row then column, as in ``3,5``."""
        return f"{self.row},{self.col}"


class CrateTag(NamedTuple):
    """The markings on one operator's crate, the same in every round."""

    crate_id: str
    mass_kg: int


class RoundDepot(NamedTuple):
    """One round's floor.

    ``bays[i]`` is the square of bay ``i + 1``, the same square for both
    operators. ``starts[agent_id]`` is where that operator's crate is placed,
    ``allowed_bays[agent_id]`` the bay numbers that operator may deliver to, and
    ``pallets[agent_id]`` the squares its crate cannot cross.
    """

    round_number: int
    starts: dict[str, Cell]
    bays: tuple[Cell, ...]
    allowed_bays: dict[str, tuple[int, ...]]
    pallets: dict[str, frozenset[Cell]]


def step(cell: Cell, direction: Direction, grid_size: int) -> Cell | None:
    """The square ``direction`` leads to, or None when it leaves the floor."""
    row_step, col_step = _STEPS[direction]
    row = cell.row + row_step
    col = cell.col + col_step
    if not (1 <= row <= grid_size and 1 <= col <= grid_size):
        return None
    return Cell(row=row, col=col)


def manhattan(first: Cell, second: Cell) -> int:
    """Squares between ``first`` and ``second`` on an empty floor."""
    return abs(first.row - second.row) + abs(first.col - second.col)


def distances_from(start: Cell, blocked: frozenset[Cell], grid_size: int) -> dict[Cell, int]:
    """Steps from ``start`` to every square reachable around ``blocked``."""
    distances = {start: 0}
    frontier = [start]
    while frontier:
        nearer: list[Cell] = []
        for cell in frontier:
            for direction in Direction:
                neighbour = step(cell=cell, direction=direction, grid_size=grid_size)
                if neighbour is None or neighbour in blocked or neighbour in distances:
                    continue
                distances[neighbour] = distances[cell] + 1
                nearer.append(neighbour)
        frontier = nearer
    return distances


def crate_tags(seed: int, agent_ids: tuple[str, ...]) -> dict[str, CrateTag]:
    """Each operator's crate markings, drawn from ``seed`` and fixed for the run."""
    rng = random.Random(f"move_a_box crates {seed}")
    return {
        agent_id: CrateTag(crate_id=f"CR-{rng.randint(1000, 9999)}", mass_kg=rng.randint(28, 55))
        for agent_id in agent_ids
    }


def humidity_series(seed: int, round_number: int, length: int) -> tuple[int, ...]:
    """The floor humidity an operator reads over one round: ``length`` + 1 values.

    A bounded random walk from ``seed``. It is the same series for every
    operator and each reads it at its own action count, so nothing one does
    changes what another reads.
    """
    rng = random.Random(f"move_a_box humidity {seed} {round_number}")
    reading = 50
    series = [reading]
    for _ in range(length):
        reading = max(40, min(60, reading + rng.choice([-1, 0, 1])))
        series.append(reading)
    return tuple(series)


def floor_rows(depot: RoundDepot, agent_id: str, grid_size: int) -> list[str]:
    """The floor as ``agent_id`` sees it: ``C`` the crate's start, ``#`` a pallet, ``B`` a bay.

    Every bay is drawn, whether or not this operator may use it, and none of them
    is numbered: a bay is named by the square it stands on. Which bays an
    operator may use is stated in the briefing, not in the drawing, because an
    operator reads the same floor either way.
    """
    bays = set(depot.bays)
    pallets = depot.pallets[agent_id]
    own_start = depot.starts[agent_id]
    rows: list[str] = []
    for row in range(1, grid_size + 1):
        marks: list[str] = []
        for col in range(1, grid_size + 1):
            cell = Cell(row=row, col=col)
            if cell in bays:
                marks.append("B")
            elif cell == own_start:
                marks.append("C")
            elif cell in pallets:
                marks.append("#")
            else:
                marks.append(".")
        rows.append(" ".join(mark.ljust(2) for mark in marks).rstrip())
    return rows


def _draw_bays(
    rng: random.Random, grid_size: int, bay_count: int, corner: Cell
) -> list[Cell] | None:
    """Bay squares spread apart, none of them on or beside the corner start square."""
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if manhattan(first=Cell(row=row, col=col), second=corner) >= MIN_START_SEPARATION
    ]
    rng.shuffle(candidates)
    chosen: list[Cell] = []
    for cell in candidates:
        if all(manhattan(first=cell, second=taken) >= MIN_BAY_SEPARATION for taken in chosen):
            chosen.append(cell)
        if len(chosen) == bay_count:
            return sorted(chosen)
    return None


def _draw_allowed_sets(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
) -> dict[str, frozenset[int]]:
    """Which bay numbers the depot assigns each operator.

    Each operator gets ``bays_allowed_each`` bays either way, so the two
    conditions differ only in how far the lists overlap.

    With ``bays_differ`` on, exactly one bay is on every list and the rest of
    each list is that operator's alone. Every bay is equally likely to be the
    shared one, so a rule any operator could apply to its own list, the lowest
    number or the bay nearest its crate, names the shared bay no more often than
    the draw puts it there.

    Off, every operator gets the same list: the control, where they hold the
    same information and need nothing from each other.
    """
    numbers = list(range(1, bay_count + 1))
    rng.shuffle(numbers)
    if not bays_differ:
        shared_set = frozenset(numbers[:bays_allowed_each])
        return dict.fromkeys(agent_ids, shared_set)
    private = bays_allowed_each - 1
    shared = numbers[0]
    rest = numbers[1:]
    return {
        agent_id: frozenset({shared} | set(rest[index * private : (index + 1) * private]))
        for index, agent_id in enumerate(agent_ids)
    }


def _draw_starts(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    grid_size: int,
    bays: tuple[Cell, ...],
    crate_start: CrateStart,
) -> dict[str, Cell]:
    """Where each operator's crate is placed, as ``crate_start`` describes it.

    A drawn square stands at least ``MIN_START_SEPARATION`` from every bay, the
    same floor the corner square keeps. ``SHARED_RANDOM`` draws one and gives it
    to both operators; ``SEPARATE_RANDOM`` draws one each, so the bay nearest one
    operator's crate is not the bay nearest the other's.
    """
    if crate_start is CrateStart.CORNER:
        return dict.fromkeys(agent_ids, Cell(row=CORNER_CELL[0], col=CORNER_CELL[1]))
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if all(
            manhattan(first=Cell(row=row, col=col), second=bay) >= MIN_START_SEPARATION
            for bay in bays
        )
    ]
    if crate_start is CrateStart.SHARED_RANDOM:
        return dict.fromkeys(agent_ids, rng.choice(candidates))
    return {agent_id: rng.choice(candidates) for agent_id in agent_ids}


def _draw_pallets(
    rng: random.Random,
    grid_size: int,
    bays: tuple[Cell, ...],
    start: Cell,
    pallet_density: float,
) -> frozenset[Cell] | None:
    """Pallets on one operator's floor, or None when they would close a bay off.

    A pallet never stands on a bay or on the crate's start square. The draw is
    kept only when every bay is still reachable from the start, so pallets cost
    an operator steps and never a delivery.
    """
    if pallet_density <= 0.0:
        return frozenset()
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if Cell(row=row, col=col) not in bays and Cell(row=row, col=col) != start
    ]
    pallets = frozenset(cell for cell in candidates if rng.random() < pallet_density)
    reached = distances_from(start=start, blocked=pallets, grid_size=grid_size)
    if any(bay not in reached for bay in bays):
        return None
    return pallets


def generate_depots(
    seed: int,
    agent_ids: tuple[str, ...],
    round_count: int,
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    crate_start: CrateStart,
    pallet_density: float,
) -> list[RoundDepot]:
    """Every round's bays, start squares, assigned bays and pallets, drawn from ``seed``.

    The bays stand on the same squares for every operator. A layout is kept
    only when every bay is reachable from each operator's own start square
    around its own pallets, so the only thing keeping an operator off a bay is
    that the depot did not assign it.
    """
    rng = random.Random(f"move_a_box depots {seed}")
    corner = Cell(row=CORNER_CELL[0], col=CORNER_CELL[1])
    depots: list[RoundDepot] = []
    for round_number in range(1, round_count + 1):
        depot = _draw_depot(
            rng=rng,
            agent_ids=agent_ids,
            round_number=round_number,
            corner=corner,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
            crate_start=crate_start,
            pallet_density=pallet_density,
        )
        if depot is None:
            raise ValueError(
                f"No move_a_box layout for round {round_number} after {LAYOUT_ATTEMPTS} draws: "
                f"grid_size={grid_size} holds no {bay_count} bays far enough apart, or "
                f"pallet_density={pallet_density} closes one off every time."
            )
        depots.append(depot)
    return depots


def _draw_depot(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    round_number: int,
    corner: Cell,
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    crate_start: CrateStart,
    pallet_density: float,
) -> RoundDepot | None:
    """One round's layout, or None when ``LAYOUT_ATTEMPTS`` draws all closed a bay off."""
    for _ in range(LAYOUT_ATTEMPTS):
        drawn = _draw_bays(rng=rng, grid_size=grid_size, bay_count=bay_count, corner=corner)
        if drawn is None:
            return None
        bays = tuple(drawn)
        starts = _draw_starts(
            rng=rng, agent_ids=agent_ids, grid_size=grid_size, bays=bays, crate_start=crate_start
        )
        allowed = _draw_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
        )
        pallets: dict[str, frozenset[Cell]] = {}
        for agent_id in agent_ids:
            drawn_pallets = _draw_pallets(
                rng=rng,
                grid_size=grid_size,
                bays=bays,
                start=starts[agent_id],
                pallet_density=pallet_density,
            )
            if drawn_pallets is None:
                break
            pallets[agent_id] = drawn_pallets
        if len(pallets) != len(agent_ids):
            continue
        return RoundDepot(
            round_number=round_number,
            starts=starts,
            bays=bays,
            allowed_bays={agent_id: tuple(sorted(allowed[agent_id])) for agent_id in agent_ids},
            pallets=pallets,
        )
    return None
