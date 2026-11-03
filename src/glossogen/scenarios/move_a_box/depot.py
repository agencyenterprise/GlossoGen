"""The depot floor: cells, bays, each operator's assigned bays and pallets.

No runtime state. A bay number means the same thing on every floor, and
scoring compares bay numbers. Under ``BayIdentity.SQUARE`` every floor holds
every bay on the same square, and the square is how an operator names it.
Under ``BayIdentity.SYMBOL`` and ``BayIdentity.LETTER`` a floor holds only the
bays its operator was assigned, on squares no other floor's bays stand on, and
the bay's symbol or letter is how an operator names it. Either way the depot
assigns each operator a set, and with ``bays_differ`` exactly one bay is on
both lists. Neither operator is told the other's list.

Pallets are separate from that. They never close a bay, they only force a crate
to go around, and ``pallet_density`` decides how many a floor holds. A layout is
kept only when every bay is still reachable from that operator's own start.

Cells are ``(row, col)`` pairs counted from 1 at the top left, which is how
operators read them. ``up`` lowers the row and ``left`` lowers the column.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.move_a_box.ids import (
    BAY_LETTERS,
    BAY_SYMBOLS,
    CORNER_CELL,
    SQUARE_BAY_MARK,
    BayIdentity,
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


class Bay(NamedTuple):
    """A bay on one operator's floor: the number scoring compares across floors, and its square."""

    number: int
    cell: Cell


class RoundDepot(NamedTuple):
    """One round's floor.

    ``bays[agent_id]`` is every bay on that operator's floor, in reading order of
    their squares. ``starts[agent_id]`` is where that operator's crate is placed,
    ``allowed_bays[agent_id]`` the bay numbers that operator may deliver to, and
    ``pallets[agent_id]`` the squares its crate cannot cross.
    """

    round_number: int
    bay_identity: BayIdentity
    starts: dict[str, Cell]
    bays: dict[str, tuple[Bay, ...]]
    allowed_bays: dict[str, tuple[int, ...]]
    pallets: dict[str, frozenset[Cell]]

    def bay_at(self, agent_id: str, cell: Cell) -> int | None:
        """The bay number on ``agent_id``'s floor at ``cell``, or None when no bay stands there."""
        for bay in self.bays[agent_id]:
            if bay.cell == cell:
                return bay.number
        return None

    def bay_name(self, number: int) -> str:
        """What every operator calls bay ``number``: its square, its symbol or its letter."""
        if self.bay_identity is BayIdentity.SYMBOL:
            return BAY_SYMBOLS[number - 1].name
        if self.bay_identity is BayIdentity.LETTER:
            return BAY_LETTERS[number - 1]
        for bays in self.bays.values():
            for bay in bays:
                if bay.number == number:
                    return bay.cell.label()
        raise ValueError(f"Bay {number} stands on no floor in round {self.round_number}.")

    def bay_mark(self, number: int) -> str:
        """How the floor drawing marks bay ``number``."""
        if self.bay_identity is BayIdentity.SYMBOL:
            return BAY_SYMBOLS[number - 1].glyph
        if self.bay_identity is BayIdentity.LETTER:
            return BAY_LETTERS[number - 1]
        return SQUARE_BAY_MARK


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


def crate_tags(seed: int, crate_ids: tuple[str, ...]) -> dict[str, CrateTag]:
    """Every crate's markings, drawn from ``seed`` and fixed for the run.

    The markings are what an operator names a crate by, so they are drawn to be
    distinct across the whole depot rather than within one floor.
    """
    rng = random.Random(f"move_a_box crates {seed}")
    drawn: set[str] = set()
    tags: dict[str, CrateTag] = {}
    for crate_id in crate_ids:
        marking = f"CR-{rng.randint(1000, 9999)}"
        while marking in drawn:
            marking = f"CR-{rng.randint(1000, 9999)}"
        drawn.add(marking)
        tags[crate_id] = CrateTag(crate_id=marking, mass_kg=rng.randint(28, 55))
    return tags


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
    """The floor as ``agent_id`` sees it: the crate's start, ``#`` a pallet, each bay by its mark.

    Every bay on this operator's floor is drawn and none of them is numbered.
    Under ``BayIdentity.SQUARE`` that is every bay, each a ``B``, whether or not
    this operator may use it: which bays it may use is stated in the briefing,
    not in the drawing. Under a marked identity it is the operator's own bays,
    each drawn as its symbol or letter. The start is ``C``, or ``@`` on a floor
    of letters.
    """
    bays = {bay.cell: depot.bay_mark(number=bay.number) for bay in depot.bays[agent_id]}
    pallets = depot.pallets[agent_id]
    own_start = depot.starts[agent_id]
    rows: list[str] = []
    for row in range(1, grid_size + 1):
        marks: list[str] = []
        for col in range(1, grid_size + 1):
            cell = Cell(row=row, col=col)
            if cell in bays:
                marks.append(bays[cell])
            elif cell == own_start:
                marks.append(depot.bay_identity.crate_mark())
            elif cell in pallets:
                marks.append("#")
            else:
                marks.append(".")
        rows.append(" ".join(mark.ljust(2) for mark in marks).rstrip())
    return rows


def _draw_bays(
    rng: random.Random, grid_size: int, bay_count: int, corner: Cell, taken: frozenset[Cell]
) -> list[Cell] | None:
    """Bay squares spread apart, none on or beside the corner start square, none on ``taken``.

    The squares come back in the order they were drawn.
    """
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if manhattan(first=Cell(row=row, col=col), second=corner) >= MIN_START_SEPARATION
        and Cell(row=row, col=col) not in taken
    ]
    rng.shuffle(candidates)
    chosen: list[Cell] = []
    for cell in candidates:
        if all(manhattan(first=cell, second=other) >= MIN_BAY_SEPARATION for other in chosen):
            chosen.append(cell)
        if len(chosen) == bay_count:
            return chosen
    return None


def _draw_bay_squares(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    corner: Cell,
    bay_identity: BayIdentity,
) -> dict[str, list[Cell]] | None:
    """The squares of the bays on each operator's floor, or None when they do not fit.

    Under ``BayIdentity.SQUARE`` every floor gets the same ``bay_count``
    squares in reading order. Under a marked identity each floor gets
    ``bays_allowed_each`` squares of its own, in the order they were drawn, and
    no square is used on two floors.
    """
    if not bay_identity.is_marked():
        drawn = _draw_bays(
            rng=rng, grid_size=grid_size, bay_count=bay_count, corner=corner, taken=frozenset()
        )
        if drawn is None:
            return None
        return dict.fromkeys(agent_ids, sorted(drawn))
    squares: dict[str, list[Cell]] = {}
    taken: set[Cell] = set()
    for agent_id in agent_ids:
        drawn = _draw_bays(
            rng=rng,
            grid_size=grid_size,
            bay_count=bays_allowed_each,
            corner=corner,
            taken=frozenset(taken),
        )
        if drawn is None:
            return None
        squares[agent_id] = drawn
        taken.update(drawn)
    return squares


def _number_bays(
    squares: dict[str, list[Cell]],
    allowed: dict[str, frozenset[int]],
    bay_identity: BayIdentity,
) -> dict[str, tuple[Bay, ...]]:
    """Give every bay square on every floor its bay number.

    Under ``BayIdentity.SQUARE`` the squares are numbered in reading order, the
    same on every floor. Under a marked identity each floor's squares take that
    operator's assigned numbers in the order the squares were drawn, so which
    mark stands where is random on every floor.
    """
    numbered: dict[str, tuple[Bay, ...]] = {}
    for agent_id, cells in squares.items():
        if bay_identity.is_marked():
            numbers = sorted(allowed[agent_id])
        else:
            numbers = list(range(1, len(cells) + 1))
        bays = [Bay(number=number, cell=cell) for number, cell in zip(numbers, cells, strict=True)]
        numbered[agent_id] = tuple(sorted(bays, key=lambda bay: bay.cell))
    return numbered


def _draw_allowed_sets(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    bay_count: int,
    bays_allowed_each: int,
    crates_each: int,
    bays_differ: bool,
) -> dict[str, frozenset[int]]:
    """Which bay numbers the depot assigns each operator.

    Each operator gets ``bays_allowed_each`` bays either way, so the two
    conditions differ only in how far the lists overlap.

    With ``bays_differ`` on, ``crates_each`` bays are on every list and the rest
    of each list is that operator's alone. One shared bay per crate slot is the
    fewest that lets every slot meet somewhere, and the depot never says which
    shared bay belongs to which slot: that is left to the operators. Every bay
    is equally likely to be shared, so a rule any operator could apply to its
    own list names a shared bay no more often than the draw puts it there.

    Off, every operator gets the same list: the control, where they hold the
    same information and need nothing from each other.
    """
    numbers = list(range(1, bay_count + 1))
    rng.shuffle(numbers)
    if not bays_differ:
        shared_set = frozenset(numbers[:bays_allowed_each])
        return dict.fromkeys(agent_ids, shared_set)
    private = bays_allowed_each - crates_each
    shared = set(numbers[:crates_each])
    rest = numbers[crates_each:]
    return {
        agent_id: frozenset(shared | set(rest[index * private : (index + 1) * private]))
        for index, agent_id in enumerate(agent_ids)
    }


def _draw_starts(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    grid_size: int,
    bays: frozenset[Cell],
    crate_start: CrateStart,
) -> dict[str, Cell]:
    """Where each operator's crate is placed, as ``crate_start`` describes it.

    A drawn square stands at least ``MIN_START_SEPARATION`` from every bay on
    every floor, the same floor the corner square keeps. ``SHARED_RANDOM`` draws one and gives it
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
    bays: frozenset[Cell],
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
    crates_each: int,
    bays_differ: bool,
    bay_identity: BayIdentity,
    crate_start: CrateStart,
    pallet_density: float,
) -> list[RoundDepot]:
    """Every round's bays, start squares, assigned bays and pallets, drawn from ``seed``.

    A layout is kept only when every bay on an operator's floor is reachable
    from its own start square around its own pallets, so the only thing keeping
    an operator off a bay on its floor is that the depot did not assign it.
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
            crates_each=crates_each,
            bays_differ=bays_differ,
            bay_identity=bay_identity,
            crate_start=crate_start,
            pallet_density=pallet_density,
        )
        if depot is None:
            raise ValueError(
                f"No move_a_box layout for round {round_number} after {LAYOUT_ATTEMPTS} draws: "
                f"grid_size={grid_size} holds no {bay_count} bays far enough apart under "
                f"bay_identity={bay_identity.value}, or "
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
    crates_each: int,
    bays_differ: bool,
    bay_identity: BayIdentity,
    crate_start: CrateStart,
    pallet_density: float,
) -> RoundDepot | None:
    """One round's layout, or None when ``LAYOUT_ATTEMPTS`` draws all failed.

    A draw fails when the bays do not fit on the floor, or when a pallet closes a
    bay off.
    """
    for _ in range(LAYOUT_ATTEMPTS):
        squares = _draw_bay_squares(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            corner=corner,
            bay_identity=bay_identity,
        )
        if squares is None:
            continue
        every_bay = frozenset(cell for cells in squares.values() for cell in cells)
        starts = _draw_starts(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=grid_size,
            bays=every_bay,
            crate_start=crate_start,
        )
        allowed = _draw_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            crates_each=crates_each,
            bays_differ=bays_differ,
        )
        bays = _number_bays(squares=squares, allowed=allowed, bay_identity=bay_identity)
        pallets: dict[str, frozenset[Cell]] = {}
        for agent_id in agent_ids:
            drawn_pallets = _draw_pallets(
                rng=rng,
                grid_size=grid_size,
                bays=frozenset(squares[agent_id]),
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
            bay_identity=bay_identity,
            starts=starts,
            bays=bays,
            allowed_bays={agent_id: tuple(sorted(allowed[agent_id])) for agent_id in agent_ids},
            pallets=pallets,
        )
    return None
