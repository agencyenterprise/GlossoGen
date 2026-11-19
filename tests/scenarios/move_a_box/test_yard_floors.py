"""Floors as windows on one yard: landmark floors, the mirror, and the per-round shift."""

import re
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.move_a_box.depot import (
    MIN_START_SEPARATION,
    Cell,
    FloorView,
    RoundDepot,
    YardSetup,
    distances_from,
    floor_rows,
    generate_depots,
    landmark_floor_rows,
    manhattan,
    step,
)
from glossogen.scenarios.move_a_box.events import MoveABoxRoundResolved, MoveABoxRoundStarted
from glossogen.scenarios.move_a_box.ids import (
    CORNER_CELL,
    LANDMARK_CELL_WIDTH,
    LANDMARK_CRATE_MARK,
    OPERATOR_A,
    OPERATOR_B,
    BayIdentity,
    CrateStart,
    Direction,
)
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.move_a_box.move_a_box_play import (
    CRATE_A,
    CRATE_B,
    act,
    build,
    first_depot,
    play,
    read,
)
from tests.scenarios.move_a_box.move_a_box_play import step as act_step
from tests.scenarios.move_a_box.move_a_box_play import steps_along, wait_for_next_round

GRID_SIZE = 8
"""The floor size the landmark presets ship."""

MIRRORED = YardSetup(
    landmark_count=6, mirrored=True, view_shift=0, private_bays_outside_overlap=False
)
"""``knobs_landmarks``: both floors show the whole yard, the second mirrored."""

UNMIRRORED = YardSetup(
    landmark_count=6, mirrored=False, view_shift=0, private_bays_outside_overlap=False
)
"""Both floors show the whole yard as drawn."""

SHIFTED = YardSetup(
    landmark_count=10, mirrored=True, view_shift=4, private_bays_outside_overlap=False
)
"""``knobs_landmarks_shifted``: each floor a window on a 12x12 yard, the second mirrored."""

SHIFTED_UNMIRRORED = YardSetup(
    landmark_count=10, mirrored=False, view_shift=4, private_bays_outside_overlap=False
)

ONE_ROUND_UNASKED: dict[str, Any] = {"round_count": 1, "describe_protocol_at_end": False}
"""One round, with no closing question the scripts would have to answer."""

TWO_ROUNDS: dict[str, Any] = {"round_count": 2}

FINISH = act_step(action="finish", direction=None)


def landmark_depots(
    setup: YardSetup, round_count: int, crate_start: CrateStart
) -> list[RoundDepot]:
    """``round_count`` landmark rounds of ``setup`` on the presets' floor."""
    return generate_depots(
        seed=42,
        agent_ids=(OPERATOR_A, OPERATOR_B),
        bay_identities=(BayIdentity.LANDMARK,) * round_count,
        grid_size=GRID_SIZE,
        bay_count=6,
        bays_allowed_each=3,
        crates_each=1,
        bays_differ=True,
        crate_start=crate_start,
        pallet_density=0.0,
        yard_setup=setup,
    )


def yard_square(view: FloorView, cell: Cell) -> Cell:
    """The yard square under ``cell`` of the floor at ``view``."""
    col = cell.col
    if view.mirrored:
        col = GRID_SIZE + 1 - col
    return Cell(row=cell.row + view.row_offset, col=col + view.col_offset)


def yard_of(depot: RoundDepot, agent_id: str) -> dict[Cell, str]:
    """What ``agent_id``'s floor shows on each yard square: a landmark's kind, or bay."""
    view = depot.views[agent_id]
    shown = {
        yard_square(view=view, cell=landmark.cell): landmark.kind
        for landmark in depot.landmarks[agent_id]
    }
    for bay in depot.first_target.bays[agent_id]:
        shown[yard_square(view=view, cell=bay.cell)] = f"bay {bay.number}"
    return shown


def shared_number(depot: RoundDepot) -> int:
    """The bay on both operators' lists."""
    allowed = depot.first_target.allowed_bays
    [number] = set(allowed[OPERATOR_A]) & set(allowed[OPERATOR_B])
    return number


def bay_cell(depot: RoundDepot, agent_id: str, number: int) -> Cell:
    """Where bay ``number`` stands on ``agent_id``'s floor."""
    return next(bay.cell for bay in depot.first_target.bays[agent_id] if bay.number == number)


def route_around(start: Cell, end: Cell, blocked: frozenset[Cell]) -> list[str]:
    """A shortest list of hauls from ``start`` to ``end`` that goes around ``blocked``."""
    distances = distances_from(start=end, blocked=blocked, grid_size=GRID_SIZE)
    route: list[str] = []
    here = start
    while here != end:
        for direction in Direction:
            there = step(cell=here, direction=direction, grid_size=GRID_SIZE)
            if there is not None and distances.get(there) == distances[here] - 1:
                route.append(direction.value)
                here = there
                break
    return route


def drawn_word(rows: list[str], cell: Cell) -> str:
    """The word a landmark drawing shows on ``cell``."""
    start = (cell.col - 1) * LANDMARK_CELL_WIDTH
    return rows[cell.row - 1][start : start + LANDMARK_CELL_WIDTH].strip()


def drawing_after(text: str, heading: str) -> list[str]:
    """The drawing rows that follow the line ``heading`` in ``text``, without their indent."""
    lines = text.split("\n")
    first = lines.index(heading) + 1
    return [line[2:] for line in lines[first : first + GRID_SIZE]]


@pytest.mark.parametrize("setup", [MIRRORED, UNMIRRORED, SHIFTED, SHIFTED_UNMIRRORED])
def test_both_floors_show_one_yard(setup: YardSetup) -> None:
    """Where two floors overlap they show the same landmarks; each shows its own bays only."""
    for depot in landmark_depots(
        setup=setup, round_count=30, crate_start=CrateStart.SEPARATE_RANDOM
    ):
        yard_a = yard_of(depot=depot, agent_id=OPERATOR_A)
        yard_b = yard_of(depot=depot, agent_id=OPERATOR_B)
        shared_bay = f"bay {shared_number(depot=depot)}"
        for square in yard_a.keys() & yard_b.keys():
            if not yard_a[square].startswith("bay"):
                assert yard_a[square] == yard_b[square]
        assert [square for square, word in yard_a.items() if word == shared_bay] == [
            square for square, word in yard_b.items() if word == shared_bay
        ]
        assert depot.views[OPERATOR_A].mirrored is False
        assert depot.views[OPERATOR_B].mirrored is setup.mirrored


def test_without_a_shift_or_a_mirror_both_floors_are_drawn_alike() -> None:
    for depot in landmark_depots(
        setup=UNMIRRORED, round_count=10, crate_start=CrateStart.SEPARATE_RANDOM
    ):
        assert depot.landmarks[OPERATOR_A] == depot.landmarks[OPERATOR_B]
        number = shared_number(depot=depot)
        assert bay_cell(depot=depot, agent_id=OPERATOR_A, number=number) == bay_cell(
            depot=depot, agent_id=OPERATOR_B, number=number
        )


def test_without_a_shift_the_mirror_swaps_left_and_right() -> None:
    for depot in landmark_depots(
        setup=MIRRORED, round_count=10, crate_start=CrateStart.SEPARATE_RANDOM
    ):
        number = shared_number(depot=depot)
        cell_a = bay_cell(depot=depot, agent_id=OPERATOR_A, number=number)
        cell_b = bay_cell(depot=depot, agent_id=OPERATOR_B, number=number)
        assert cell_b == Cell(row=cell_a.row, col=GRID_SIZE + 1 - cell_a.col)


@pytest.mark.parametrize("setup", [SHIFTED, SHIFTED_UNMIRRORED])
def test_the_shift_places_the_floors_at_many_offsets_and_never_on_one_corner(
    setup: YardSetup,
) -> None:
    depots = landmark_depots(setup=setup, round_count=30, crate_start=CrateStart.SEPARATE_RANDOM)
    offsets: set[tuple[int, int]] = set()
    for depot in depots:
        view_a = depot.views[OPERATOR_A]
        view_b = depot.views[OPERATOR_B]
        for view in (view_a, view_b):
            assert 0 <= view.row_offset <= setup.view_shift
            assert 0 <= view.col_offset <= setup.view_shift
        offsets.add((view_b.row_offset - view_a.row_offset, view_b.col_offset - view_a.col_offset))
    assert len(offsets) > 5
    assert (0, 0) not in offsets


@pytest.mark.parametrize("crate_start", [CrateStart.CORNER, CrateStart.SHARED_RANDOM])
def test_a_corner_or_shared_start_puts_both_crates_on_one_yard_square_away_from_the_bays(
    crate_start: CrateStart,
) -> None:
    for depot in landmark_depots(setup=MIRRORED, round_count=10, crate_start=crate_start):
        yard_starts = {
            yard_square(view=depot.views[agent_id], cell=depot.starts[agent_id])
            for agent_id in (OPERATOR_A, OPERATOR_B)
        }
        assert len(yard_starts) == 1
        if crate_start is CrateStart.CORNER:
            assert yard_starts == {Cell(row=CORNER_CELL[0], col=CORNER_CELL[1])}
        for agent_id in (OPERATOR_A, OPERATOR_B):
            assert depot.starts[agent_id] not in depot.pallets[agent_id]
            for bay in depot.first_target.bays[agent_id]:
                assert (
                    manhattan(first=depot.starts[agent_id], second=bay.cell) >= MIN_START_SEPARATION
                )


def test_a_haul_off_a_landmark_floor_names_no_square() -> None:
    scenario = build(preset_name="knobs_landmarks", overrides=ONE_ROUND_UNASKED)
    depot = first_depot(scenario=scenario)
    edge = next(
        Cell(row=1, col=col)
        for col in range(1, GRID_SIZE + 1)
        if Cell(row=1, col=col) not in depot.pallets[OPERATOR_A]
    )
    world = scenario.get_world()
    world.start_round(depot=depot._replace(starts={**depot.starts, OPERATOR_A: edge}))

    refusal = world.haul_refusal(crate_id=CRATE_A, direction=Direction.UP)

    assert refusal == "Hauling up from here leaves the floor. No step spent."


@pytest.mark.parametrize("setup", [MIRRORED, SHIFTED, SHIFTED_UNMIRRORED])
def test_every_bay_stands_beside_a_landmark_and_the_shared_one_beside_one_both_floors_show(
    setup: YardSetup,
) -> None:
    for depot in landmark_depots(
        setup=setup, round_count=30, crate_start=CrateStart.SEPARATE_RANDOM
    ):
        target = depot.first_target
        for agent_id in (OPERATOR_A, OPERATOR_B):
            assert sorted(bay.number for bay in target.bays[agent_id]) == list(
                target.allowed_bays[agent_id]
            )
            for bay in target.bays[agent_id]:
                assert bay.cell not in depot.pallets[agent_id]
                assert any(
                    manhattan(first=bay.cell, second=landmark.cell) == 1
                    for landmark in depot.landmarks[agent_id]
                )
        yard_a = yard_of(depot=depot, agent_id=OPERATOR_A)
        yard_b = yard_of(depot=depot, agent_id=OPERATOR_B)
        [shared] = [
            square for square, word in yard_a.items() if word == f"bay {shared_number(depot)}"
        ]
        assert any(
            manhattan(first=square, second=shared) == 1 and not word.startswith("bay")
            for square, word in yard_a.items()
            if square in yard_b
        )


@pytest.mark.parametrize("setup", [MIRRORED, SHIFTED])
def test_every_assigned_bay_is_reachable_around_the_landmarks(setup: YardSetup) -> None:
    for depot in landmark_depots(
        setup=setup, round_count=30, crate_start=CrateStart.SEPARATE_RANDOM
    ):
        for agent_id in (OPERATOR_A, OPERATOR_B):
            reached = distances_from(
                start=depot.starts[agent_id],
                blocked=depot.pallets[agent_id],
                grid_size=GRID_SIZE,
            )
            assert all(bay.cell in reached for bay in depot.first_target.bays[agent_id])


@pytest.mark.parametrize(
    "preset_name",
    ["knobs_landmarks", "knobs_landmarks_shifted", "knobs_landmarks_shifted_partner_floor"],
)
def test_the_briefing_numbers_no_square(preset_name: str) -> None:
    scenario = build(preset_name=preset_name, overrides={})
    depot = first_depot(scenario=scenario)
    for agent_id in (OPERATOR_A, OPERATOR_B):
        text = scenario.get_injection(round_number=1, agent_id=agent_id)
        assert "row 1" not in text
        assert re.search(r"\d,\d", text) is None
        rows = drawing_after(text=text, heading="Your floor this round:")
        assert drawn_word(rows=rows, cell=depot.starts[agent_id]) == "crate"
        for bay in depot.first_target.bays[agent_id]:
            assert drawn_word(rows=rows, cell=bay.cell) == "bay"
        for landmark in depot.landmarks[agent_id]:
            assert drawn_word(rows=rows, cell=landmark.cell) == landmark.kind


@pytest.mark.parametrize(
    "preset_name",
    ["knobs_landmarks", "knobs_landmarks_shifted", "knobs_landmarks_shifted_partner_floor"],
)
def test_the_system_prompt_says_nothing_of_the_mirror_the_shift_or_the_squares(
    preset_name: str,
) -> None:
    """The operators have to find out how the other floor relates to theirs."""
    for overrides in ({}, {"channel_disclosed": True}):
        scenario = build(preset_name=preset_name, overrides=overrides)
        prompt = scenario.get_agents(default_model="model", default_provider="openai")[0]
        assert "mirror" not in prompt.system_prompt
        assert "shift" not in prompt.system_prompt
        assert "Row 1 is the top row" not in prompt.system_prompt


def briefing_after(bays: dict[str, int | None], matched: bool) -> str:
    """Round 2's briefing for operator_a, once round 1 left the crates on ``bays``."""
    scenario = build(preset_name="knobs_landmarks", overrides=TWO_ROUNDS)
    depot = first_depot(scenario=scenario)
    own = depot.first_target.bays[OPERATOR_A][0].cell
    matched_slots: tuple[int, ...] = ()
    if matched:
        matched_slots = (1,)
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={CRATE_A: (own.row, own.col), CRATE_B: (1, 1)},
                final_bays=bays,
                temperatures={CRATE_A: 23, CRATE_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 20, OPERATOR_B: 20},
                matched_slots=matched_slots,
                matched=matched,
                success=matched,
                trigger="all_finished",
            )
        ]
    )
    return scenario.get_injection(round_number=2, agent_id=OPERATOR_A)


def test_a_missed_round_says_only_that_the_other_crate_went_elsewhere() -> None:
    depot = first_depot(scenario=build(preset_name="knobs_landmarks", overrides={}))
    own_numbers = set(depot.first_target.allowed_bays[OPERATOR_A])
    other = next(
        bay.number for bay in depot.first_target.bays[OPERATOR_B] if bay.number not in own_numbers
    )
    text = briefing_after(
        bays={CRATE_A: depot.first_target.bays[OPERATOR_A][0].number, CRATE_B: other},
        matched=False,
    )
    assert "you left a crate on one of your bays. The other crates were left in other spots." in (
        text
    )
    assert "Round 1's floor" not in text
    assert "other " not in text.split("Your floor this round:")[1]


def test_a_matched_round_says_the_crates_met() -> None:
    depot = first_depot(scenario=build(preset_name="knobs_landmarks", overrides={}))
    number = shared_number(depot=depot)
    text = briefing_after(bays={CRATE_A: number, CRATE_B: number}, matched=True)
    assert "Every other crate was left on the same bay" in text


def test_landmark_knob_combinations_are_refused() -> None:
    with pytest.raises(ValueError, match="apply only with bay_identity=landmark"):
        build(preset_name="knobs_default", overrides={"landmark_count": 3})
    with pytest.raises(ValueError, match="apply only with bay_identity=landmark"):
        build(preset_name="knobs_default", overrides={"landmark_mirrored": True})
    for landmark_count in (0, 1):
        with pytest.raises(ValueError, match="needs landmark_count of at least 2"):
            build(preset_name="knobs_landmarks", overrides={"landmark_count": landmark_count})
    with pytest.raises(ValueError, match="needs crates_each=1 and targets_per_round=1"):
        build(preset_name="knobs_landmarks", overrides={"crates_each": 2})
    with pytest.raises(ValueError, match="needs crates_each=1 and targets_per_round=1"):
        build(preset_name="knobs_landmarks", overrides={"targets_per_round": 2})
    with pytest.raises(ValueError, match="has too few squares for 6 bays, 30 landmarks"):
        build(preset_name="knobs_landmarks", overrides={"grid_size": 6, "landmark_count": 30})
    with pytest.raises(ValueError, match="landmark_count=40 on a 8x8 floor"):
        build(preset_name="knobs_landmarks", overrides={"landmark_count": 40})
    with pytest.raises(ValueError, match="needs pallet_density=0"):
        build(preset_name="knobs_landmarks", overrides={"pallet_density": 0.1})
    with pytest.raises(ValueError, match="needs operator_count=2"):
        build(preset_name="knobs_landmarks", overrides={"operator_count": 3, "bay_count": 7})
    with pytest.raises(ValueError, match="needs partner_bay_disclosed=false"):
        build(preset_name="knobs_landmarks", overrides={"partner_bay_disclosed": True})
    with pytest.raises(ValueError, match="view_shift can be at most 4"):
        build(preset_name="knobs_landmarks", overrides={"view_shift": 5})
    with pytest.raises(ValueError, match="needs crate_start=separate_random"):
        build(preset_name="knobs_landmarks_shifted", overrides={"crate_start": "corner"})
    with pytest.raises(ValueError, match="switches only between symbol and letter"):
        build(preset_name="knobs_landmarks", overrides={"bay_identity_from_round": {"2": "symbol"}})


@pytest.mark.parametrize("preset_name", ["knobs_landmarks", "knobs_landmarks_shifted"])
async def test_an_act_call_redraws_the_floor_and_a_landmark_stops_the_crate(
    preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator_a hauls into the landmark beside the shared bay, which stops its list there."""
    scenario = build(preset_name=preset_name, overrides=ONE_ROUND_UNASKED)
    depot = first_depot(scenario=scenario)
    number = shared_number(depot=depot)
    shared = {
        agent_id: bay_cell(depot=depot, agent_id=agent_id, number=number)
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    landmark_cells = {landmark.cell: landmark.kind for landmark in depot.landmarks[OPERATOR_A]}
    into_landmark, blocked_kind = next(
        (direction, landmark_cells[neighbour])
        for direction in Direction
        if (neighbour := step(cell=shared[OPERATOR_A], direction=direction, grid_size=GRID_SIZE))
        is not None
        and neighbour in landmark_cells
    )
    routes = {
        agent_id: route_around(
            start=depot.starts[agent_id], end=shared[agent_id], blocked=depot.pallets[agent_id]
        )
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    route_a = steps_along(directions=routes[OPERATOR_A], method="cart")
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act(steps=[*route_a, act_step(action="cart", direction=into_landmark.value)]),
            act(steps=[FINISH]),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act(steps=steps_along(directions=routes[OPERATOR_B], method="cart")),
            act(steps=[FINISH]),
            wait_for_next_round(),
        ],
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    assert started.floor_views[OPERATOR_B].mirrored
    route_result, finish_result = [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == OPERATOR_A and event.tool_name == "act"
    ]
    assert f"A {blocked_kind} stands there, so the crate cannot go {into_landmark.value}" in (
        route_result
    )
    rows = drawing_after(text=route_result, heading="Your floor now:")
    assert drawn_word(rows=rows, cell=shared[OPERATOR_A]) == "crate"
    assert "on one of your bays, left there for the round." in finish_result
    assert re.search(r"\d,\d", route_result + finish_result) is None


SHIFTED_SQUARE = YardSetup(
    landmark_count=0, mirrored=False, view_shift=4, private_bays_outside_overlap=False
)
"""``knobs_shifted``: the default square floor as a window on a 12x12 yard."""


def shifted_square_depots(round_count: int) -> list[RoundDepot]:
    """``round_count`` rounds of ``knobs_shifted``'s square floors."""
    return generate_depots(
        seed=42,
        agent_ids=(OPERATOR_A, OPERATOR_B),
        bay_identities=(BayIdentity.SQUARE,) * round_count,
        grid_size=GRID_SIZE,
        bay_count=6,
        bays_allowed_each=3,
        crates_each=1,
        bays_differ=True,
        crate_start=CrateStart.SEPARATE_RANDOM,
        pallet_density=0.1,
        yard_setup=SHIFTED_SQUARE,
    )


def square_yard_of(depot: RoundDepot, agent_id: str) -> dict[Cell, str]:
    """What ``agent_id``'s square floor shows on each yard square: a pallet, or a numbered bay."""
    view = depot.views[agent_id]
    shown = {yard_square(view=view, cell=cell): "#" for cell in depot.pallets[agent_id]}
    for bay in depot.first_target.bays[agent_id]:
        shown[yard_square(view=view, cell=bay.cell)] = f"bay {bay.number}"
    return shown


def test_shifted_square_floors_show_one_yard_of_bays_and_pallets() -> None:
    """Where the windows overlap, both floors show the same bays and pallets."""
    offsets: set[tuple[int, int]] = set()
    for depot in shifted_square_depots(round_count=30):
        view_a = depot.views[OPERATOR_A]
        view_b = depot.views[OPERATOR_B]
        assert not view_a.mirrored and not view_b.mirrored
        offsets.add((view_b.row_offset - view_a.row_offset, view_b.col_offset - view_a.col_offset))
        assert (view_a.row_offset, view_a.col_offset) != (view_b.row_offset, view_b.col_offset)
        window_a = {
            Cell(row=view_a.row_offset + row, col=view_a.col_offset + col)
            for row in range(1, GRID_SIZE + 1)
            for col in range(1, GRID_SIZE + 1)
        }
        window_b = {
            Cell(row=view_b.row_offset + row, col=view_b.col_offset + col)
            for row in range(1, GRID_SIZE + 1)
            for col in range(1, GRID_SIZE + 1)
        }
        yard_a = square_yard_of(depot=depot, agent_id=OPERATOR_A)
        yard_b = square_yard_of(depot=depot, agent_id=OPERATOR_B)
        for square in window_a & window_b:
            assert yard_a.get(square) == yard_b.get(square)
    assert len(offsets) > 5


def test_shifted_square_floors_hold_every_assigned_bay_and_name_it_by_their_own_square() -> None:
    for depot in shifted_square_depots(round_count=30):
        target = depot.first_target
        for agent_id in (OPERATOR_A, OPERATOR_B):
            on_floor = {bay.number: bay.cell for bay in target.bays[agent_id]}
            assert set(target.allowed_bays[agent_id]) <= on_floor.keys()
            for number, cell in on_floor.items():
                assert target.bay_name(number=number, agent_id=agent_id) == cell.label()
            reached = distances_from(
                start=depot.starts[agent_id], blocked=depot.pallets[agent_id], grid_size=GRID_SIZE
            )
            assert all(cell in reached for cell in on_floor.values())


def test_a_shift_is_refused_where_floors_are_not_windows_on_one_yard() -> None:
    with pytest.raises(ValueError, match="view_shift applies only with bay_identity=square"):
        build(preset_name="knobs_symbol_bays", overrides={"view_shift": 2})
    with pytest.raises(ValueError, match="needs operator_count=2, crates_each=1"):
        build(preset_name="knobs_shifted", overrides={"crates_each": 2})


def test_the_shifted_square_prompt_counts_no_bays_and_mentions_no_shift() -> None:
    """A shifted floor shows only part of the yard's bays, so the prompt does not count them."""
    scenario = build(preset_name="knobs_shifted", overrides={"channel_disclosed": True})
    prompt = scenario.get_agents(default_model="model", default_provider="openai")[0].system_prompt
    assert "move it to one of the loading bays on that floor." in prompt
    assert "shift" not in prompt


def test_the_shifted_square_briefing_lists_assigned_bays_by_the_readers_own_squares() -> None:
    scenario = build(preset_name="knobs_shifted", overrides={})
    target = first_depot(scenario=scenario).first_target
    for agent_id in (OPERATOR_A, OPERATOR_B):
        squares = "  ".join(
            bay.cell.label()
            for bay in target.bays[agent_id]
            if bay.number in target.allowed_bays[agent_id]
        )
        text = scenario.get_injection(round_number=1, agent_id=agent_id)
        assert f"Bays the depot assigns you this round: {squares}." in text


async def test_a_shifted_square_round_plays_to_a_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each operator walks to the shared bay at its own square for it, and the round matches."""
    scenario = build(preset_name="knobs_shifted", overrides=ONE_ROUND_UNASKED)
    depot = first_depot(scenario=scenario)
    number = shared_number(depot=depot)
    scripts: dict[str, list[ScriptedTurn]] = {}
    for agent_id in (OPERATOR_A, OPERATOR_B):
        route = route_around(
            start=depot.starts[agent_id],
            end=bay_cell(depot=depot, agent_id=agent_id, number=number),
            blocked=depot.pallets[agent_id],
        )
        scripts[agent_id] = [
            read(),
            act(steps=[*steps_along(directions=route, method="cart"), FINISH]),
            wait_for_next_round(),
        ]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    corners = {(view.row_offset, view.col_offset) for view in started.floor_views.values()}
    assert len(corners) == 2


APART = YardSetup(landmark_count=0, mirrored=False, view_shift=4, private_bays_outside_overlap=True)
"""``knobs_shifted_apart``: shifted square floors whose private bays the other floor never shows."""


def test_private_bays_stand_where_the_other_floor_does_not_reach() -> None:
    depots = generate_depots(
        seed=42,
        agent_ids=(OPERATOR_A, OPERATOR_B),
        bay_identities=(BayIdentity.SQUARE,) * 30,
        grid_size=GRID_SIZE,
        bay_count=6,
        bays_allowed_each=3,
        crates_each=1,
        bays_differ=True,
        crate_start=CrateStart.SEPARATE_RANDOM,
        pallet_density=0.1,
        yard_setup=APART,
    )
    for depot in depots:
        allowed = depot.first_target.allowed_bays
        shown = {
            agent_id: {bay.number for bay in depot.first_target.bays[agent_id]}
            for agent_id in (OPERATOR_A, OPERATOR_B)
        }
        shared = shared_number(depot=depot)
        assert shared in shown[OPERATOR_A] and shared in shown[OPERATOR_B]
        for agent_id, other in ((OPERATOR_A, OPERATOR_B), (OPERATOR_B, OPERATOR_A)):
            private = set(allowed[agent_id]) - {shared}
            assert len(private) == 2
            assert private <= shown[agent_id]
            assert not private & shown[other]


def test_private_bays_apart_needs_a_shift_and_private_bays() -> None:
    with pytest.raises(ValueError, match="private_bays_outside_overlap needs view_shift above 0"):
        build(preset_name="knobs_default", overrides={"private_bays_outside_overlap": True})
    with pytest.raises(ValueError, match="private_bays_outside_overlap needs bays_differ"):
        build(preset_name="knobs_shifted_apart", overrides={"bays_differ": False})


def test_a_disclosed_bay_on_shifted_floors_is_named_on_the_other_operators_floor() -> None:
    """The square comes from the other floor, so the result says whose floor it is."""
    scenario = build(
        preset_name="knobs_shifted_apart",
        overrides={**TWO_ROUNDS, "partner_bay_disclosed": True},
    )
    depot = first_depot(scenario=scenario)
    target = depot.first_target
    own = target.bays[OPERATOR_A][0]
    other_private = next(
        bay
        for bay in target.bays[OPERATOR_B]
        if bay.number in target.allowed_bays[OPERATOR_B]
        and bay.number not in target.allowed_bays[OPERATOR_A]
    )
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={
                    CRATE_A: (own.cell.row, own.cell.col),
                    CRATE_B: (other_private.cell.row, other_private.cell.col),
                },
                final_bays={CRATE_A: own.number, CRATE_B: other_private.number},
                temperatures={CRATE_A: 23, CRATE_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 10, OPERATOR_B: 10},
                matched_slots=(),
                matched=False,
                success=False,
                trigger="all_finished",
            )
        ]
    )
    text = scenario.get_injection(round_number=2, agent_id=OPERATOR_A)
    square = other_private.cell.label()
    assert f"The other crates were left on the bay at {square} of the other operator's floor." in (
        text
    )


def test_the_result_draws_the_other_operators_floor_as_that_operator_saw_it() -> None:
    """With partner_floor_disclosed, round 2's briefing shows operator_b's round 1 floor."""
    scenario = build(preset_name="knobs_shifted_partner_floor", overrides=TWO_ROUNDS)
    depot = first_depot(scenario=scenario)
    target = depot.first_target
    own = target.bays[OPERATOR_A][0]
    other = next(
        bay
        for bay in target.bays[OPERATOR_B]
        if bay.number in target.allowed_bays[OPERATOR_B]
        and bay.number not in target.allowed_bays[OPERATOR_A]
    )
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={
                    CRATE_A: (own.cell.row, own.cell.col),
                    CRATE_B: (other.cell.row, other.cell.col),
                },
                final_bays={CRATE_A: own.number, CRATE_B: other.number},
                temperatures={CRATE_A: 23, CRATE_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 10, OPERATOR_B: 10},
                matched_slots=(),
                matched=False,
                success=False,
                trigger="all_finished",
            )
        ]
    )
    text = scenario.get_injection(round_number=2, agent_id=OPERATOR_A)
    expected = floor_rows(
        target=target,
        pallets=depot.pallets[OPERATOR_B],
        crate=other.cell,
        agent_id=OPERATOR_B,
        grid_size=GRID_SIZE,
    )
    heading = (
        "The other operator's floor in round 1, as that operator saw it, "
        "with C where its crate ended:"
    )
    lines = text.split("\n")
    first = lines.index(heading) + 1
    assert lines[first : first + GRID_SIZE] == [
        f"  row {index}:  {row}" for index, row in enumerate(expected, start=1)
    ]
    assert expected[other.cell.row - 1].split()[other.cell.col - 1] == "C"


def test_on_landmark_floors_the_other_floor_is_drawn_as_the_readers_own_is() -> None:
    """One word per square, the crate over the bay it ended on, and no row or column numbers."""
    scenario = build(preset_name="knobs_landmarks_shifted_partner_floor", overrides=TWO_ROUNDS)
    depot = first_depot(scenario=scenario)
    target = depot.first_target
    own = target.bays[OPERATOR_A][0]
    other = next(
        bay for bay in target.bays[OPERATOR_B] if bay.number not in target.allowed_bays[OPERATOR_A]
    )
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={
                    CRATE_A: (own.cell.row, own.cell.col),
                    CRATE_B: (other.cell.row, other.cell.col),
                },
                final_bays={CRATE_A: own.number, CRATE_B: other.number},
                temperatures={CRATE_A: 23, CRATE_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 10, OPERATOR_B: 10},
                matched_slots=(),
                matched=False,
                success=False,
                trigger="all_finished",
            )
        ]
    )
    text = scenario.get_injection(round_number=2, agent_id=OPERATOR_A)
    heading = (
        "The other operator's floor in round 1, as that operator saw it, "
        "with crate where its crate ended:"
    )
    rows = drawing_after(text=text, heading=heading)
    assert rows == landmark_floor_rows(
        landmarks=depot.landmarks[OPERATOR_B],
        bays=target.bays[OPERATOR_B],
        crates={other.cell: LANDMARK_CRATE_MARK},
        grid_size=GRID_SIZE,
    )
    assert drawn_word(rows=rows, cell=other.cell) == LANDMARK_CRATE_MARK
    assert "row 1" not in text
    assert re.search(r"\d,\d", text) is None


def test_the_other_floor_is_refused_where_it_would_not_be_drawn_as_the_readers_own() -> None:
    with pytest.raises(
        ValueError, match="partner_floor_disclosed needs bay_identity=square or landmark"
    ):
        build(preset_name="knobs_symbol_bays", overrides={"partner_floor_disclosed": True})
    with pytest.raises(ValueError, match="partner_floor_disclosed needs operator_count=2"):
        build(
            preset_name="knobs_default",
            overrides={"partner_floor_disclosed": True, "crates_each": 2},
        )
    with pytest.raises(ValueError, match="partner_floor_disclosed needs partner_disclosed"):
        build(
            preset_name="knobs_shifted_partner_floor",
            overrides={"partner_disclosed": False, "channel_disclosed": False},
        )


SHIFT_SENTENCE = (
    "Their floor shows a different part of the same yard than yours, and how the two floors "
    "overlap can change from one round to the next."
)


TOLD_DESCRIPTION = (
    "The system prompt tells the operators that the two floors show different parts of one yard "
    "and that how they overlap can change from one round to the next, and gives no offset."
)


@pytest.mark.parametrize(
    ("preset_name", "untold_description"),
    [
        ("knobs_shifted_partner_floor", "Nothing an operator reads mentions the shift."),
        (
            "knobs_landmarks_shifted_partner_floor",
            "Nothing an operator reads says how the floors relate.",
        ),
    ],
)
def test_the_shift_is_told_only_when_view_shift_disclosed_is_on(
    preset_name: str, untold_description: str
) -> None:
    """The system prompt carries the sentence, and the description says which was played."""
    told = build(preset_name=preset_name, overrides={"view_shift_disclosed": True})
    untold = build(preset_name=preset_name, overrides={})
    told_prompt = told.get_agents(default_model="model", default_provider="openai")[0].system_prompt
    untold_prompt = untold.get_agents(default_model="model", default_provider="openai")[0]
    assert SHIFT_SENTENCE in told_prompt
    assert SHIFT_SENTENCE not in untold_prompt.system_prompt
    assert TOLD_DESCRIPTION in told.scenario_description()
    assert untold_description not in told.scenario_description()
    assert untold_description in untold.scenario_description()
    assert TOLD_DESCRIPTION not in untold.scenario_description()


def test_view_shift_disclosed_needs_a_shift_a_named_partner_and_no_mirror() -> None:
    with pytest.raises(ValueError, match="view_shift_disclosed needs view_shift above 0"):
        build(preset_name="knobs_default", overrides={"view_shift_disclosed": True})
    with pytest.raises(ValueError, match="view_shift_disclosed needs partner_disclosed"):
        build(
            preset_name="knobs_shifted",
            overrides={
                "view_shift_disclosed": True,
                "partner_disclosed": False,
                "channel_disclosed": False,
            },
        )
    with pytest.raises(ValueError, match="view_shift_disclosed needs landmark_mirrored=false"):
        build(preset_name="knobs_landmarks_shifted", overrides={"view_shift_disclosed": True})
