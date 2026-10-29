"""The layout generator: which bays each operator is assigned, and what the lists share.

The scenario rests on these invariants. If the two lists were the same under
``bays_differ``, or if a pallet closed a bay off, a run would score matches that
needed nothing to cross between the operators.
"""

import pytest

from glossogen.scenarios.move_a_box.depot import (
    Cell,
    RoundDepot,
    crate_tags,
    distances_from,
    floor_rows,
    generate_depots,
    humidity_series,
)
from glossogen.scenarios.move_a_box.ids import AGENT_IDS, CrateStart

GRID_SIZE = 7
BAY_COUNT = 6
REACH = 3
STEPS = 400


def depots(
    bays_differ: bool, round_count: int, crate_start: CrateStart, pallet_density: float
) -> list[RoundDepot]:
    return generate_depots(
        seed=42,
        round_count=round_count,
        grid_size=GRID_SIZE,
        bay_count=BAY_COUNT,
        bays_allowed_each=REACH,
        bays_differ=bays_differ,
        crate_start=crate_start,
        pallet_density=pallet_density,
    )


def test_a_clear_floor_holds_no_pallets_at_all() -> None:
    for depot in depots(
        bays_differ=True, round_count=40, crate_start=CrateStart.CORNER, pallet_density=0.0
    ):
        for agent_id in AGENT_IDS:
            assert depot.pallets[agent_id] == frozenset()


def test_every_bay_stays_walkable_whatever_the_pallets() -> None:
    """Pallets cost an operator steps, never a delivery, so no bay is ever closed off."""
    for density in (0.0, 0.15, 0.3):
        layouts = depots(
            bays_differ=True, round_count=20, crate_start=CrateStart.CORNER, pallet_density=density
        )
        for depot in layouts:
            for agent_id in AGENT_IDS:
                distances = distances_from(
                    start=depot.starts[agent_id],
                    blocked=depot.pallets[agent_id],
                    grid_size=GRID_SIZE,
                )
                for cell in depot.bays:
                    assert cell in distances


def test_pallets_are_drawn_separately_for_each_operator() -> None:
    layouts = depots(
        bays_differ=True, round_count=30, crate_start=CrateStart.CORNER, pallet_density=0.2
    )
    differ = sum(depot.pallets[AGENT_IDS[0]] != depot.pallets[AGENT_IDS[1]] for depot in layouts)
    assert differ > len(layouts) // 2


def test_differing_floors_share_exactly_one_bay() -> None:
    for depot in depots(
        bays_differ=True, round_count=40, crate_start=CrateStart.CORNER, pallet_density=0.0
    ):
        first, second = (set(depot.allowed_bays[agent_id]) for agent_id in AGENT_IDS)
        assert len(first) == len(second) == REACH
        assert len(first & second) == 1


def test_matching_floors_leave_both_operators_the_same_bays() -> None:
    for depot in depots(
        bays_differ=False, round_count=20, crate_start=CrateStart.CORNER, pallet_density=0.0
    ):
        first, second = (depot.allowed_bays[agent_id] for agent_id in AGENT_IDS)
        assert first == second
        assert len(first) == REACH


def test_a_shared_start_puts_both_crates_on_one_square() -> None:
    for depot in depots(
        bays_differ=True, round_count=20, crate_start=CrateStart.CORNER, pallet_density=0.0
    ):
        assert set(depot.starts.values()) == {Cell(row=1, col=1)}
        assert len(set(depot.bays)) == BAY_COUNT


def test_separate_random_starts_place_the_crates_apart_and_off_the_bays() -> None:
    """Without a shared start the two crates are usually on different squares."""
    layouts = depots(
        bays_differ=True, round_count=60, crate_start=CrateStart.SEPARATE_RANDOM, pallet_density=0.0
    )
    apart = 0
    for depot in layouts:
        for agent_id in AGENT_IDS:
            assert depot.starts[agent_id] not in depot.bays
        first, second = (depot.starts[agent_id] for agent_id in AGENT_IDS)
        apart += first != second
    assert apart > len(layouts) // 2


def test_separate_starts_still_leave_every_bay_walkable() -> None:
    for depot in depots(
        bays_differ=True, round_count=40, crate_start=CrateStart.SEPARATE_RANDOM, pallet_density=0.1
    ):
        for agent_id in AGENT_IDS:
            distances = distances_from(
                start=depot.starts[agent_id],
                blocked=depot.pallets[agent_id],
                grid_size=GRID_SIZE,
            )
            for cell in depot.bays:
                assert cell in distances


def test_the_shared_bay_is_not_always_the_lowest_numbered() -> None:
    """A rule over an operator's own set must not pick the shared bay every time.

    The lowest-numbered assigned bay is the rule a pair would fall into without
    a channel. It has to fail often enough that a run matching on every round
    cannot be explained by it.
    """
    agreed = 0
    layouts = depots(
        bays_differ=True, round_count=100, crate_start=CrateStart.CORNER, pallet_density=0.0
    )
    for depot in layouts:
        lowest = {min(depot.allowed_bays[agent_id]) for agent_id in AGENT_IDS}
        agreed += len(lowest) == 1
    assert agreed < len(layouts) // 2


def test_a_floor_too_small_for_its_bays_is_refused() -> None:
    with pytest.raises(ValueError, match="No move_a_box layout"):
        generate_depots(
            seed=42,
            round_count=1,
            grid_size=3,
            bay_count=BAY_COUNT,
            bays_allowed_each=REACH,
            bays_differ=True,
            crate_start=CrateStart.CORNER,
            pallet_density=0.0,
        )


def test_the_floor_drawing_marks_the_start_and_every_bay() -> None:
    """Every bay is drawn, including the ones the depot assigned the other operator."""
    [depot] = depots(
        bays_differ=True, round_count=1, crate_start=CrateStart.CORNER, pallet_density=0.0
    )
    rows = floor_rows(depot=depot, agent_id=AGENT_IDS[0], grid_size=GRID_SIZE)
    assert len(rows) == GRID_SIZE
    drawing = "\n".join(rows)
    assert drawing.startswith("C")
    for number in range(1, BAY_COUNT + 1):
        assert f"B{number}" in drawing
    assert "#" not in drawing


def test_the_floor_drawing_marks_pallets_when_the_floor_has_them() -> None:
    [depot] = depots(
        bays_differ=True, round_count=1, crate_start=CrateStart.CORNER, pallet_density=0.2
    )
    drawing = "\n".join(floor_rows(depot=depot, agent_id=AGENT_IDS[0], grid_size=GRID_SIZE))
    assert "#" in drawing


def test_the_inert_readings_do_not_answer_to_either_operator() -> None:
    """Crate markings never change, and the humidity walk comes from the seed alone."""
    tags = crate_tags(seed=42)
    assert tags == crate_tags(seed=42)
    assert len({tag.crate_id for tag in tags.values()}) == len(AGENT_IDS)
    series = humidity_series(seed=42, round_number=1, length=STEPS)
    assert series == humidity_series(seed=42, round_number=1, length=STEPS)
    assert len(series) == STEPS + 1
    assert all(40 <= reading <= 60 for reading in series)
