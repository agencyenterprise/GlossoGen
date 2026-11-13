"""The depot floor: cells, bays, each operator's assigned bays and pallets.

No runtime state. A round's floor holds one target or several: each target
assigns its own bays, and every target after the first is drawn around where
the crates stand once the one before it is done.

A bay number means the same thing on every floor of a target, and scoring
compares bay numbers. Under ``BayIdentity.SQUARE`` every floor holds every bay
on the same square, and the square is how an operator names it. Under
``BayIdentity.SYMBOL`` and ``BayIdentity.LETTER`` a floor holds only the bays
its operator was assigned, on squares no other floor's bays stand on, and the
bay's symbol or letter is how an operator names it. Either way the depot
assigns each operator a set, and with ``bays_differ`` exactly one bay is on
both lists. Neither operator is told the other's list.

Under ``BayIdentity.LANDMARK`` every floor is a window on one yard of
landmarks and bays. The windows can sit at different places in the yard, and
the second operator's can be drawn mirrored left to right. Each floor holds
only its operator's bays, so scoring compares bay numbers as it does for marked
bays, and every square, start and landmark of a floor is in that floor's own
drawing, which is the square its operator's actions move through.

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
    LANDMARK_BAY_MARK,
    LANDMARK_CELL_WIDTH,
    LANDMARK_KINDS,
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


class Landmark(NamedTuple):
    """A landmark on one operator's floor: the square it blocks and the word the drawing shows."""

    cell: Cell
    kind: str


class FloorView(NamedTuple):
    """Where one operator's floor sits in the yard, and whether it is drawn mirrored.

    A floor is the ``grid_size`` square of the yard whose top left corner is
    ``row_offset`` rows down and ``col_offset`` columns right of the yard's,
    drawn mirrored left to right when ``mirrored`` is set. Every identity but
    ``BayIdentity.LANDMARK`` gives each floor the whole yard as drawn.
    """

    row_offset: int
    col_offset: int
    mirrored: bool

    def from_yard(self, cell: Cell, grid_size: int) -> Cell | None:
        """The square of this floor over yard square ``cell``, or None when the floor misses it."""
        row = cell.row - self.row_offset
        col = cell.col - self.col_offset
        if not (1 <= row <= grid_size and 1 <= col <= grid_size):
            return None
        if self.mirrored:
            col = grid_size + 1 - col
        return Cell(row=row, col=col)


WHOLE_YARD_VIEW = FloorView(row_offset=0, col_offset=0, mirrored=False)
"""The view of a floor that shows the whole yard, as drawn."""


class YardSetup(NamedTuple):
    """How a round lays its floors over one yard.

    ``landmark_count`` landmarks stand in a landmark yard, each on one floor or
    more. ``mirrored`` draws the second operator's landmark floor mirrored left
    to right. ``view_shift`` makes the yard that many squares wider and taller
    than a floor, and puts each floor's top left corner up to that many squares
    down and right of the yard's, drawn for each operator and each round; it
    applies to square and landmark floors. ``private_bays_outside_overlap``
    puts each operator's private bays where no other floor reaches, so the only
    assigned bay two shifted floors both show is the shared one.
    """

    landmark_count: int
    mirrored: bool
    view_shift: int
    private_bays_outside_overlap: bool


class TargetLayout(NamedTuple):
    """The bays one target of a round puts on each floor, and which of them each operator may use.

    ``bays[agent_id]`` is every bay on that operator's floor, in reading order of
    their squares, and ``allowed_bays[agent_id]`` the bay numbers it may deliver
    to.
    """

    bay_identity: BayIdentity
    bays: dict[str, tuple[Bay, ...]]
    allowed_bays: dict[str, tuple[int, ...]]

    def bay_at(self, agent_id: str, cell: Cell) -> int | None:
        """The bay number on ``agent_id``'s floor at ``cell``, or None when no bay stands there."""
        for bay in self.bays[agent_id]:
            if bay.cell == cell:
                return bay.number
        return None

    def bay_name(self, number: int, agent_id: str) -> str:
        """What ``agent_id`` calls bay ``number``: its square on that floor, its symbol or letter.

        A square bay is named by the square ``agent_id``'s floor shows it on,
        which differs between floors when the floors are shifted over a yard. A
        landmark bay has no name an operator reads, so the log names it by its
        number and no prompt shows it.
        """
        if self.bay_identity is BayIdentity.SYMBOL:
            return BAY_SYMBOLS[number - 1].name
        if self.bay_identity is BayIdentity.LETTER:
            return BAY_LETTERS[number - 1]
        if self.bay_identity is BayIdentity.LANDMARK:
            return str(number)
        for bay in self.bays[agent_id]:
            if bay.number == number:
                return bay.cell.label()
        raise ValueError(f"Bay {number} is not on {agent_id}'s floor.")

    def bay_mark(self, number: int) -> str:
        """How the floor drawing marks bay ``number``."""
        if self.bay_identity is BayIdentity.SYMBOL:
            return BAY_SYMBOLS[number - 1].glyph
        if self.bay_identity is BayIdentity.LETTER:
            return BAY_LETTERS[number - 1]
        if self.bay_identity is BayIdentity.LANDMARK:
            return LANDMARK_BAY_MARK
        return SQUARE_BAY_MARK


class RoundDepot(NamedTuple):
    """One round's floor and its first target.

    ``starts[agent_id]`` is where that operator's crate is placed and
    ``pallets[agent_id]`` the squares its crate cannot cross, for every target of
    the round. Under ``BayIdentity.LANDMARK`` those squares are the landmarks,
    ``landmarks[agent_id]`` names what stands on each, and ``views[agent_id]``
    places the floor in the yard; every other identity leaves ``landmarks``
    empty and gives every floor ``WHOLE_YARD_VIEW``. Later targets are drawn by
    ``draw_next_target`` once the crates have moved.
    """

    round_number: int
    starts: dict[str, Cell]
    pallets: dict[str, frozenset[Cell]]
    landmarks: dict[str, tuple[Landmark, ...]]
    views: dict[str, FloorView]
    first_target: TargetLayout


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


def floor_rows(
    target: TargetLayout,
    pallets: frozenset[Cell],
    crate: Cell,
    agent_id: str,
    grid_size: int,
) -> list[str]:
    """``agent_id``'s floor for one target: the crate, ``#`` a pallet, each bay by its mark.

    Every bay on this operator's floor is drawn and none of them is numbered.
    Under ``BayIdentity.SQUARE`` that is every bay, each a ``B``, whether or not
    this operator may use it: which bays it may use is stated in the briefing,
    not in the drawing. Under a marked identity it is the operator's own bays,
    each drawn as its symbol or letter. ``crate`` is the square the crate stands
    on as the target begins, drawn ``C``, or ``@`` on a floor of letters.
    """
    bays = {bay.cell: target.bay_mark(number=bay.number) for bay in target.bays[agent_id]}
    rows: list[str] = []
    for row in range(1, grid_size + 1):
        marks: list[str] = []
        for col in range(1, grid_size + 1):
            cell = Cell(row=row, col=col)
            if cell in bays:
                marks.append(bays[cell])
            elif cell == crate:
                marks.append(target.bay_identity.crate_mark())
            elif cell in pallets:
                marks.append("#")
            else:
                marks.append(".")
        rows.append(" ".join(mark.ljust(2) for mark in marks).rstrip())
    return rows


def landmark_floor_rows(
    landmarks: tuple[Landmark, ...],
    bays: tuple[Bay, ...],
    crates: dict[Cell, str],
    grid_size: int,
) -> list[str]:
    """One landmark floor, one word per square: each landmark by its kind, each bay, the crates.

    Every square is ``LANDMARK_CELL_WIDTH`` characters wide, so a square holding a
    word stands in the same column as the dots above and below it. No row or
    column is numbered. ``crates`` maps each square a crate is drawn on to the
    word it is drawn as, which covers a bay standing on the same square.
    """
    marks = {landmark.cell: landmark.kind for landmark in landmarks}
    for bay in bays:
        marks[bay.cell] = LANDMARK_BAY_MARK
    marks.update(crates)
    rows: list[str] = []
    for row in range(1, grid_size + 1):
        words = [marks.get(Cell(row=row, col=col), ".") for col in range(1, grid_size + 1)]
        rows.append("".join(word.ljust(LANDMARK_CELL_WIDTH) for word in words).rstrip())
    return rows


def _every_square(grid_size: int) -> frozenset[Cell]:
    """Every square of a ``grid_size`` floor."""
    return frozenset(
        Cell(row=row, col=col) for row in range(1, grid_size + 1) for col in range(1, grid_size + 1)
    )


def _draw_bays(
    rng: random.Random,
    grid_size: int,
    bay_count: int,
    away_from: frozenset[Cell],
    open_squares: frozenset[Cell],
) -> list[Cell] | None:
    """Bay squares spread apart, on ``open_squares``, none on or beside a square of ``away_from``.

    The squares come back in the order they were drawn.
    """
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if Cell(row=row, col=col) in open_squares
        and all(
            manhattan(first=Cell(row=row, col=col), second=kept) >= MIN_START_SEPARATION
            for kept in away_from
        )
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
    bay_identity: BayIdentity,
    away_from: frozenset[Cell],
    open_squares: dict[str, frozenset[Cell]],
) -> dict[str, list[Cell]] | None:
    """The squares of the bays on each operator's floor, or None when they do not fit.

    Under ``BayIdentity.SQUARE`` every floor gets the same ``bay_count``
    squares in reading order, on squares open on every floor. Under a marked
    identity each floor gets ``bays_allowed_each`` squares of its own, open on
    that floor, in the order they were drawn, and no square is used on two
    floors. No bay stands on or beside a square of ``away_from``.
    """
    if not bay_identity.is_marked():
        open_everywhere = _every_square(grid_size=grid_size)
        for floor_squares in open_squares.values():
            open_everywhere = open_everywhere & floor_squares
        drawn = _draw_bays(
            rng=rng,
            grid_size=grid_size,
            bay_count=bay_count,
            away_from=away_from,
            open_squares=open_everywhere,
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
            away_from=away_from,
            open_squares=open_squares[agent_id] - taken,
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
    blocked: frozenset[Cell],
    crate_start: CrateStart,
) -> dict[str, Cell]:
    """Where each operator's crate is placed, as ``crate_start`` describes it.

    A drawn square stands at least ``MIN_START_SEPARATION`` from every bay on
    every floor, the same floor the corner square keeps, and off ``blocked``.
    ``SHARED_RANDOM`` draws one and gives it to both operators;
    ``SEPARATE_RANDOM`` draws one each, so the bay nearest one operator's crate
    is not the bay nearest the other's.
    """
    if crate_start is CrateStart.CORNER:
        return dict.fromkeys(agent_ids, Cell(row=CORNER_CELL[0], col=CORNER_CELL[1]))
    candidates = [
        Cell(row=row, col=col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
        if Cell(row=row, col=col) not in blocked
        and all(
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
    bay_identities: tuple[BayIdentity, ...],
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    crates_each: int,
    bays_differ: bool,
    crate_start: CrateStart,
    pallet_density: float,
    yard_setup: YardSetup,
) -> list[RoundDepot]:
    """Every round's bays, start squares, assigned bays and pallets, drawn from ``seed``.

    ``bay_identities`` holds one identity per round, round 1 first, so its
    length is the number of rounds. Symbol and letter floors share one draw, so
    a round switched between them keeps its squares and changes only its marks.

    A layout is kept only when every bay on an operator's floor is reachable
    from its own start square around its own pallets, so the only thing keeping
    an operator off a bay on its floor is that the depot did not assign it.
    """
    rng = random.Random(f"move_a_box depots {seed}")
    corner = Cell(row=CORNER_CELL[0], col=CORNER_CELL[1])
    depots: list[RoundDepot] = []
    for round_number, bay_identity in enumerate(bay_identities, start=1):
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
            yard_setup=yard_setup,
        )
        if depot is None:
            raise ValueError(
                f"No move_a_box layout for round {round_number} after {LAYOUT_ATTEMPTS} draws: "
                f"grid_size={grid_size} holds no {bay_count} bays far enough apart under "
                f"bay_identity={bay_identity.value}, "
                f"pallet_density={pallet_density} closes one off every time, or no layout "
                f"fits {yard_setup}."
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
    yard_setup: YardSetup,
) -> RoundDepot | None:
    """One round's layout, or None when ``LAYOUT_ATTEMPTS`` draws all failed.

    A draw fails when the bays do not fit on the floor, or when a pallet closes a
    bay off.
    """
    if bay_identity is BayIdentity.SQUARE and yard_setup.view_shift:
        return _draw_shifted_square_depot(
            rng=rng,
            agent_ids=agent_ids,
            round_number=round_number,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
            pallet_density=pallet_density,
            setup=yard_setup,
        )
    if bay_identity.is_landmark():
        return _draw_landmark_depot(
            rng=rng,
            agent_ids=agent_ids,
            round_number=round_number,
            corner=corner,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
            crate_start=crate_start,
            setup=yard_setup,
        )
    whole_floor = dict.fromkeys(agent_ids, _every_square(grid_size=grid_size))
    for _ in range(LAYOUT_ATTEMPTS):
        squares = _draw_bay_squares(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bay_identity=bay_identity,
            away_from=frozenset({corner}),
            open_squares=whole_floor,
        )
        if squares is None:
            continue
        every_bay = frozenset(cell for cells in squares.values() for cell in cells)
        starts = _draw_starts(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=grid_size,
            bays=every_bay,
            blocked=frozenset(),
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
            starts=starts,
            pallets=pallets,
            landmarks=dict.fromkeys(agent_ids, ()),
            views=dict.fromkeys(agent_ids, WHOLE_YARD_VIEW),
            first_target=TargetLayout(
                bay_identity=bay_identity,
                bays=bays,
                allowed_bays={agent_id: tuple(sorted(allowed[agent_id])) for agent_id in agent_ids},
            ),
        )
    return None


def _draw_landmark_depot(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    round_number: int,
    corner: Cell,
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    crate_start: CrateStart,
    setup: YardSetup,
) -> RoundDepot | None:
    """One round's landmark yard and floors, or None when ``LAYOUT_ATTEMPTS`` draws all failed.

    Each draw places the floors in the yard first, then the landmarks and
    ``bay_count`` bays on squares some floor shows, each bay beside a landmark
    and numbered in reading order of the yard. A draw fails when the bays do not
    fit, when an assigned bay is off its operator's floor, when a bay on every
    list has no landmark beside it that every floor shows, or when the landmarks
    close an assigned bay off from its operator's start.
    """
    yard_size = grid_size + setup.view_shift
    for _ in range(LAYOUT_ATTEMPTS):
        views = _draw_views(rng=rng, agent_ids=agent_ids, setup=setup)
        windows = {
            agent_id: _window(view=views[agent_id], grid_size=grid_size) for agent_id in agent_ids
        }
        shown = frozenset[Cell]().union(*windows.values())
        landmarks = tuple(
            sorted(
                Landmark(cell=cell, kind=rng.choice(LANDMARK_KINDS))
                for cell in rng.sample(sorted(shown - {corner}), setup.landmark_count)
            )
        )
        blocked = frozenset(landmark.cell for landmark in landmarks)
        drawn = _draw_bays(
            rng=rng,
            grid_size=yard_size,
            bay_count=bay_count,
            away_from=frozenset({corner}),
            open_squares=(_beside(cells=blocked, grid_size=yard_size) - blocked) & shown,
        )
        if drawn is None:
            continue
        bay_cells = sorted(drawn)
        starts = _draw_window_starts(
            rng=rng,
            agent_ids=agent_ids,
            windows=windows,
            yard_size=yard_size,
            bays=frozenset(bay_cells),
            blocked=blocked,
            crate_start=crate_start,
        )
        allowed = _draw_window_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
            bay_cells=bay_cells,
            windows=windows,
            setup=setup,
        )
        if allowed is None:
            continue
        if starts is None or not _shared_bays_beside_a_shown_landmark(
            views=views,
            landmarks=landmarks,
            bay_cells=bay_cells,
            allowed=allowed,
            grid_size=grid_size,
        ):
            continue
        depot = _landmark_depot(
            round_number=round_number,
            grid_size=grid_size,
            views=views,
            landmarks=landmarks,
            bay_cells=bay_cells,
            starts=starts,
            allowed=allowed,
        )
        if depot is not None and _every_floor_bay_reachable(depot=depot, grid_size=grid_size):
            return depot
    return None


def _draw_window_allowed_sets(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    bay_cells: list[Cell],
    windows: dict[str, frozenset[Cell]],
    setup: YardSetup,
) -> dict[str, frozenset[int]] | None:
    """Which bays each operator of a yard may use; None when the bays cannot be placed apart.

    Without ``setup.private_bays_outside_overlap`` the lists are drawn as on any
    floor. With it, the shared bay is drawn from the bays every floor shows and
    each operator's private bays from the bays only its own floor shows.
    ``bay_cells[n - 1]`` is where bay ``n`` stands in the yard.
    """
    if not setup.private_bays_outside_overlap:
        return _draw_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            crates_each=1,
            bays_differ=bays_differ,
        )
    everywhere = frozenset[Cell].intersection(*windows.values())
    shared_candidates = [
        number for number, cell in enumerate(bay_cells, start=1) if cell in everywhere
    ]
    if not shared_candidates:
        return None
    shared = rng.choice(shared_candidates)
    allowed: dict[str, frozenset[int]] = {}
    for agent_id in agent_ids:
        elsewhere = frozenset[Cell]().union(
            *(window for other, window in windows.items() if other != agent_id)
        )
        own_only = [
            number
            for number, cell in enumerate(bay_cells, start=1)
            if cell in windows[agent_id] and cell not in elsewhere
        ]
        if len(own_only) < bays_allowed_each - 1:
            return None
        allowed[agent_id] = frozenset({shared, *rng.sample(own_only, bays_allowed_each - 1)})
    return allowed


def _draw_views(
    rng: random.Random, agent_ids: tuple[str, ...], setup: YardSetup
) -> dict[str, FloorView]:
    """Where each floor sits in the yard this round; with no shift, every floor is the yard.

    With ``setup.view_shift`` above 0 each floor's corner is drawn on its own,
    so the floors overlap by a different amount every round, and a draw that
    puts every corner on one square is drawn again: two floors never sit on
    the same part of the yard.
    """
    while True:
        views = {
            agent_id: _draw_view(rng=rng, setup=setup, mirrored=setup.mirrored and index % 2 == 1)
            for index, agent_id in enumerate(agent_ids)
        }
        corners = {(view.row_offset, view.col_offset) for view in views.values()}
        if not setup.view_shift or len(corners) > 1:
            return views


def _draw_view(rng: random.Random, setup: YardSetup, mirrored: bool) -> FloorView:
    """One floor's corner in the yard, drawn up to ``setup.view_shift`` down and right."""
    if not setup.view_shift:
        return FloorView(row_offset=0, col_offset=0, mirrored=mirrored)
    return FloorView(
        row_offset=rng.randint(0, setup.view_shift),
        col_offset=rng.randint(0, setup.view_shift),
        mirrored=mirrored,
    )


def _window(view: FloorView, grid_size: int) -> frozenset[Cell]:
    """The yard squares the floor at ``view`` shows."""
    return frozenset(
        Cell(row=view.row_offset + row, col=view.col_offset + col)
        for row in range(1, grid_size + 1)
        for col in range(1, grid_size + 1)
    )


def _draw_window_starts(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    windows: dict[str, frozenset[Cell]],
    yard_size: int,
    bays: frozenset[Cell],
    blocked: frozenset[Cell],
    crate_start: CrateStart,
) -> dict[str, Cell] | None:
    """Each crate's start, as a yard square on its operator's floor, or None when one has none.

    ``SEPARATE_RANDOM`` draws each operator's square from its own floor, off the
    landmarks and at least ``MIN_START_SEPARATION`` from every bay. The other
    starts need every floor to be the whole yard, and are drawn as on any floor.
    """
    if crate_start is not CrateStart.SEPARATE_RANDOM:
        return _draw_starts(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=yard_size,
            bays=bays,
            blocked=blocked,
            crate_start=crate_start,
        )
    starts: dict[str, Cell] = {}
    for agent_id in agent_ids:
        candidates = [
            cell
            for cell in sorted(windows[agent_id])
            if cell not in blocked
            and all(manhattan(first=cell, second=bay) >= MIN_START_SEPARATION for bay in bays)
        ]
        if not candidates:
            return None
        starts[agent_id] = rng.choice(candidates)
    return starts


def _draw_shifted_square_depot(
    rng: random.Random,
    agent_ids: tuple[str, ...],
    round_number: int,
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    pallet_density: float,
    setup: YardSetup,
) -> RoundDepot | None:
    """One round's square yard and the shifted floors over it, or None when every draw failed.

    Each draw places the floors in the yard first, then ``bay_count`` bays and
    the pallets on squares some floor shows, so where two floors overlap they
    show the same bays and pallets. A draw fails when the bays do not fit, when
    an assigned bay is off its operator's floor, or when pallets close a bay on
    a floor off from that floor's start.
    """
    yard_size = grid_size + setup.view_shift
    for _ in range(LAYOUT_ATTEMPTS):
        views = _draw_views(rng=rng, agent_ids=agent_ids, setup=setup)
        windows = {
            agent_id: _window(view=views[agent_id], grid_size=grid_size) for agent_id in agent_ids
        }
        shown = frozenset[Cell]().union(*windows.values())
        drawn = _draw_bays(
            rng=rng,
            grid_size=yard_size,
            bay_count=bay_count,
            away_from=frozenset(),
            open_squares=shown,
        )
        if drawn is None:
            continue
        bay_cells = sorted(drawn)
        pallets = frozenset(
            cell for cell in sorted(shown - set(drawn)) if rng.random() < pallet_density
        )
        starts = _draw_window_starts(
            rng=rng,
            agent_ids=agent_ids,
            windows=windows,
            yard_size=yard_size,
            bays=frozenset(drawn),
            blocked=pallets,
            crate_start=CrateStart.SEPARATE_RANDOM,
        )
        allowed = _draw_window_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bays_differ=bays_differ,
            bay_cells=bay_cells,
            windows=windows,
            setup=setup,
        )
        if starts is None or allowed is None:
            continue
        depot = _shifted_square_depot(
            round_number=round_number,
            grid_size=grid_size,
            views=views,
            bay_cells=bay_cells,
            pallets=pallets,
            starts=starts,
            allowed=allowed,
        )
        if depot is not None and _every_floor_bay_reachable(depot=depot, grid_size=grid_size):
            return depot
    return None


def _shifted_square_depot(
    round_number: int,
    grid_size: int,
    views: dict[str, FloorView],
    bay_cells: list[Cell],
    pallets: frozenset[Cell],
    starts: dict[str, Cell],
    allowed: dict[str, frozenset[int]],
) -> RoundDepot | None:
    """Each operator's floor of one square yard, or None when an assigned bay is off its floor.

    A floor draws every bay and pallet its window covers. ``bay_cells[n - 1]``
    is where bay ``n`` stands in the yard, numbered in reading order of the
    yard, and ``starts`` are yard squares.
    """
    floor_bays: dict[str, tuple[Bay, ...]] = {}
    floor_pallets: dict[str, frozenset[Cell]] = {}
    floor_starts: dict[str, Cell] = {}
    for agent_id, view in views.items():
        start = view.from_yard(cell=starts[agent_id], grid_size=grid_size)
        bays = tuple(
            Bay(number=number, cell=cell)
            for number, yard_cell in enumerate(bay_cells, start=1)
            if (cell := view.from_yard(cell=yard_cell, grid_size=grid_size)) is not None
        )
        on_floor = {bay.number for bay in bays}
        if start is None or not allowed[agent_id] <= on_floor:
            return None
        floor_starts[agent_id] = start
        floor_bays[agent_id] = tuple(sorted(bays, key=lambda bay: bay.cell))
        floor_pallets[agent_id] = frozenset(
            cell
            for pallet in pallets
            if (cell := view.from_yard(cell=pallet, grid_size=grid_size)) is not None
        )
    return RoundDepot(
        round_number=round_number,
        starts=floor_starts,
        pallets=floor_pallets,
        landmarks=dict.fromkeys(views, ()),
        views=views,
        first_target=TargetLayout(
            bay_identity=BayIdentity.SQUARE,
            bays=floor_bays,
            allowed_bays={
                agent_id: tuple(sorted(numbers)) for agent_id, numbers in allowed.items()
            },
        ),
    )


def _shared_bays_beside_a_shown_landmark(
    views: dict[str, FloorView],
    landmarks: tuple[Landmark, ...],
    bay_cells: list[Cell],
    allowed: dict[str, frozenset[int]],
    grid_size: int,
) -> bool:
    """Whether every bay on every list has a landmark beside it that every floor shows."""
    lists = list(allowed.values())
    shared = lists[0].intersection(*lists[1:])
    for number in shared:
        beside = [
            landmark
            for landmark in landmarks
            if manhattan(first=landmark.cell, second=bay_cells[number - 1]) == 1
            and all(
                view.from_yard(cell=landmark.cell, grid_size=grid_size) is not None
                for view in views.values()
            )
        ]
        if not beside:
            return False
    return True


def _beside(cells: frozenset[Cell], grid_size: int) -> frozenset[Cell]:
    """Every square next to a square of ``cells``, up, down, left or right."""
    return frozenset(
        neighbour
        for cell in cells
        for direction in Direction
        if (neighbour := step(cell=cell, direction=direction, grid_size=grid_size)) is not None
    )


def _every_floor_bay_reachable(depot: RoundDepot, grid_size: int) -> bool:
    """Whether every crate can reach every bay on its floor around that floor's obstacles."""
    for agent_id, start in depot.starts.items():
        reached = distances_from(start=start, blocked=depot.pallets[agent_id], grid_size=grid_size)
        if any(bay.cell not in reached for bay in depot.first_target.bays[agent_id]):
            return False
    return True


def _landmark_depot(
    round_number: int,
    grid_size: int,
    views: dict[str, FloorView],
    landmarks: tuple[Landmark, ...],
    bay_cells: list[Cell],
    starts: dict[str, Cell],
    allowed: dict[str, frozenset[int]],
) -> RoundDepot | None:
    """Each operator's floor of one yard, holding its own bays only, or None when one does not fit.

    ``bay_cells[n - 1]`` is where bay ``n`` stands in the yard, and ``starts``
    are yard squares too. A floor shows the landmarks its window covers. None
    when a crate's start or an assigned bay is off its floor, or a bay on a
    floor has no landmark beside it on that floor.
    """
    floor_landmarks: dict[str, tuple[Landmark, ...]] = {}
    floor_bays: dict[str, tuple[Bay, ...]] = {}
    floor_starts: dict[str, Cell] = {}
    for agent_id, view in views.items():
        start = view.from_yard(cell=starts[agent_id], grid_size=grid_size)
        bays = tuple(
            Bay(number=number, cell=cell)
            for number in sorted(allowed[agent_id])
            if (cell := view.from_yard(cell=bay_cells[number - 1], grid_size=grid_size)) is not None
        )
        shown = tuple(
            sorted(
                Landmark(cell=cell, kind=landmark.kind)
                for landmark in landmarks
                if (cell := view.from_yard(cell=landmark.cell, grid_size=grid_size)) is not None
            )
        )
        if start is None or len(bays) != len(allowed[agent_id]):
            return None
        if not all(
            any(manhattan(first=bay.cell, second=landmark.cell) == 1 for landmark in shown)
            for bay in bays
        ):
            return None
        floor_starts[agent_id] = start
        floor_bays[agent_id] = tuple(sorted(bays, key=lambda bay: bay.cell))
        floor_landmarks[agent_id] = shown
    return RoundDepot(
        round_number=round_number,
        starts=floor_starts,
        pallets={
            agent_id: frozenset(landmark.cell for landmark in floor)
            for agent_id, floor in floor_landmarks.items()
        },
        landmarks=floor_landmarks,
        views=views,
        first_target=TargetLayout(
            bay_identity=BayIdentity.LANDMARK,
            bays=floor_bays,
            allowed_bays={
                agent_id: tuple(sorted(numbers)) for agent_id, numbers in allowed.items()
            },
        ),
    )


def draw_next_target(
    seed: int,
    round_number: int,
    target_number: int,
    agent_ids: tuple[str, ...],
    crates: dict[str, Cell],
    pallets: dict[str, frozenset[Cell]],
    grid_size: int,
    bay_count: int,
    bays_allowed_each: int,
    bays_differ: bool,
    bay_identity: BayIdentity,
) -> TargetLayout:
    """Target ``target_number`` of a round, drawn around the squares the crates stand on now.

    ``crates[agent_id]`` is where that operator's one crate stands. Every bay
    stands at least ``MIN_START_SEPARATION`` from every crate, off the pallets,
    and where its floor's crate can reach it, so a target never begins with a
    crate on or beside a bay. The draw comes from ``seed``, the round and the
    target, so the same crate squares give the same target.
    """
    rng = random.Random(f"move_a_box target {seed} {round_number} {target_number}")
    reachable = {
        agent_id: frozenset(
            distances_from(start=crates[agent_id], blocked=pallets[agent_id], grid_size=grid_size)
        )
        for agent_id in agent_ids
    }
    for _ in range(LAYOUT_ATTEMPTS):
        squares = _draw_bay_squares(
            rng=rng,
            agent_ids=agent_ids,
            grid_size=grid_size,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            bay_identity=bay_identity,
            away_from=frozenset(crates.values()),
            open_squares=reachable,
        )
        if squares is None:
            continue
        allowed = _draw_allowed_sets(
            rng=rng,
            agent_ids=agent_ids,
            bay_count=bay_count,
            bays_allowed_each=bays_allowed_each,
            crates_each=1,
            bays_differ=bays_differ,
        )
        return TargetLayout(
            bay_identity=bay_identity,
            bays=_number_bays(squares=squares, allowed=allowed, bay_identity=bay_identity),
            allowed_bays={agent_id: tuple(sorted(allowed[agent_id])) for agent_id in agent_ids},
        )
    raise ValueError(
        f"No move_a_box layout for round {round_number} target {target_number} after "
        f"{LAYOUT_ATTEMPTS} draws: no {bay_count} bays fit away from the crates on a "
        f"{grid_size}x{grid_size} floor."
    )
