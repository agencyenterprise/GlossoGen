"""The layout generator: which bays each operator is assigned, and what the lists share.

The scenario rests on these invariants. If the two lists were the same under
``bays_differ``, or if a pallet closed a bay off, a run would score matches that
needed nothing to cross between the operators.
"""

from collections.abc import Callable
from fractions import Fraction
from itertools import combinations

import pytest

from glossogen.scenarios.move_a_box.depot import (
    MIN_START_SEPARATION,
    Cell,
    RoundDepot,
    crate_tags,
    distances_from,
    floor_rows,
    generate_depots,
    humidity_series,
    manhattan,
)
from glossogen.scenarios.move_a_box.ids import (
    BAY_SYMBOLS,
    BayIdentity,
    CrateStart,
    operator_ids,
)
from glossogen.scenarios.move_a_box.knobs import MoveABoxKnobs
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario

GRID_SIZE = 7
BAY_COUNT = 6
BAYS_ALLOWED_EACH = 3
STEPS = 400
AGENT_IDS = operator_ids(operator_count=2)
"""These checks are about the two-operator geometry, so they name that roster."""


def depots(
    bays_differ: bool,
    bay_identity: BayIdentity,
    round_count: int,
    crate_start: CrateStart,
    pallet_density: float,
) -> list[RoundDepot]:
    return generate_depots(
        seed=42,
        agent_ids=AGENT_IDS,
        crates_each=1,
        bay_identities=(bay_identity,) * round_count,
        grid_size=GRID_SIZE,
        bay_count=BAY_COUNT,
        bays_allowed_each=BAYS_ALLOWED_EACH,
        bays_differ=bays_differ,
        crate_start=crate_start,
        pallet_density=pallet_density,
    )


def bay_cells(depot: RoundDepot, agent_id: str) -> set[Cell]:
    """The squares of every bay on ``agent_id``'s floor."""
    return {bay.cell for bay in depot.bays[agent_id]}


def test_a_clear_floor_holds_no_pallets_at_all() -> None:
    for depot in depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=40,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    ):
        for agent_id in AGENT_IDS:
            assert depot.pallets[agent_id] == frozenset()


def test_every_bay_stays_walkable_whatever_the_pallets() -> None:
    """Pallets cost an operator steps, never a delivery, so no bay is ever closed off."""
    for density in (0.0, 0.15, 0.3):
        layouts = depots(
            bays_differ=True,
            bay_identity=BayIdentity.SQUARE,
            round_count=20,
            crate_start=CrateStart.CORNER,
            pallet_density=density,
        )
        for depot in layouts:
            for agent_id in AGENT_IDS:
                distances = distances_from(
                    start=depot.starts[agent_id],
                    blocked=depot.pallets[agent_id],
                    grid_size=GRID_SIZE,
                )
                for cell in bay_cells(depot=depot, agent_id=agent_id):
                    assert cell in distances


def test_pallets_are_drawn_separately_for_each_operator() -> None:
    layouts = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=30,
        crate_start=CrateStart.CORNER,
        pallet_density=0.2,
    )
    differ = sum(depot.pallets[AGENT_IDS[0]] != depot.pallets[AGENT_IDS[1]] for depot in layouts)
    assert differ > len(layouts) // 2


def test_differing_floors_share_exactly_one_bay() -> None:
    for depot in depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=40,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    ):
        first, second = (set(depot.allowed_bays[agent_id]) for agent_id in AGENT_IDS)
        assert len(first) == len(second) == BAYS_ALLOWED_EACH
        assert len(first & second) == 1


def test_matching_floors_leave_both_operators_the_same_bays() -> None:
    for depot in depots(
        bays_differ=False,
        bay_identity=BayIdentity.SQUARE,
        round_count=20,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    ):
        first, second = (depot.allowed_bays[agent_id] for agent_id in AGENT_IDS)
        assert first == second
        assert len(first) == BAYS_ALLOWED_EACH


def test_the_corner_start_puts_both_crates_on_one_fixed_square() -> None:
    for depot in depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=20,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    ):
        assert set(depot.starts.values()) == {Cell(row=1, col=1)}
        for agent_id in AGENT_IDS:
            assert len(bay_cells(depot=depot, agent_id=agent_id)) == BAY_COUNT


def test_a_shared_random_start_is_one_square_that_moves_between_rounds() -> None:
    """Both crates share the drawn square, and the draw is not the corner every round."""
    layouts = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=40,
        crate_start=CrateStart.SHARED_RANDOM,
        pallet_density=0.0,
    )
    for depot in layouts:
        squares = set(depot.starts.values())
        assert len(squares) == 1
        [square] = squares
        for agent_id in AGENT_IDS:
            assert square not in bay_cells(depot=depot, agent_id=agent_id)
    drawn = {next(iter(depot.starts.values())) for depot in layouts}
    assert len(drawn) > 1
    assert drawn != {Cell(row=1, col=1)}


def test_a_drawn_start_keeps_its_distance_from_every_bay() -> None:
    """The floor _draw_bays enforces against the corner holds for a drawn square too."""
    for mode in (CrateStart.SHARED_RANDOM, CrateStart.SEPARATE_RANDOM):
        for depot in depots(
            bays_differ=True,
            bay_identity=BayIdentity.SQUARE,
            round_count=40,
            crate_start=mode,
            pallet_density=0.0,
        ):
            for agent_id in AGENT_IDS:
                for bay in bay_cells(depot=depot, agent_id=agent_id):
                    assert (
                        manhattan(first=depot.starts[agent_id], second=bay) >= MIN_START_SEPARATION
                    )


def test_separate_random_starts_place_the_crates_apart_and_off_the_bays() -> None:
    """Without a shared start the two crates are usually on different squares."""
    layouts = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=60,
        crate_start=CrateStart.SEPARATE_RANDOM,
        pallet_density=0.0,
    )
    apart = 0
    for depot in layouts:
        for agent_id in AGENT_IDS:
            assert depot.starts[agent_id] not in bay_cells(depot=depot, agent_id=agent_id)
        first, second = (depot.starts[agent_id] for agent_id in AGENT_IDS)
        apart += first != second
    assert apart > len(layouts) // 2


def test_separate_starts_still_leave_every_bay_walkable() -> None:
    for depot in depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=40,
        crate_start=CrateStart.SEPARATE_RANDOM,
        pallet_density=0.1,
    ):
        for agent_id in AGENT_IDS:
            distances = distances_from(
                start=depot.starts[agent_id],
                blocked=depot.pallets[agent_id],
                grid_size=GRID_SIZE,
            )
            for cell in bay_cells(depot=depot, agent_id=agent_id):
                assert cell in distances


def test_a_rule_over_the_numbers_matches_the_rate_the_readme_states() -> None:
    """The README's floor is a claim about the draw, so enumerate the draw and check it.

    With one shared bay and ``BAYS_ALLOWED_EACH`` per operator, the two lists are
    every way of dealing the private bays out. Taking an extreme of your own list
    agrees exactly one round in five; the middle of the list agrees two in
    fifteen. These are the numbers a channel has to beat, and the README prints
    them, so a change to the draw that moves them should fail here.
    """
    bays = range(1, BAY_COUNT + 1)
    private = BAYS_ALLOWED_EACH - 1
    rules: dict[str, Callable[[set[int]], int]] = {
        "lowest": lambda chosen: sorted(chosen)[0],
        "highest": lambda chosen: sorted(chosen)[-1],
        "middle": lambda chosen: sorted(chosen)[len(chosen) // 2],
    }
    agreed: dict[str, int] = dict.fromkeys(rules, 0)
    draws = 0
    for shared in bays:
        rest = [bay for bay in bays if bay != shared]
        for first_private in combinations(rest, private):
            left = [bay for bay in rest if bay not in first_private]
            for second_private in combinations(left, private):
                first = {shared, *first_private}
                second = {shared, *second_private}
                draws += 1
                for name, rule in rules.items():
                    agreed[name] += rule(first) == rule(second)

    assert Fraction(agreed["lowest"], draws) == Fraction(1, 5)
    assert Fraction(agreed["highest"], draws) == Fraction(1, 5)
    assert Fraction(agreed["middle"], draws) == Fraction(2, 15)


def test_the_shared_bay_is_not_always_the_lowest_numbered() -> None:
    """A rule over an operator's own set must not pick the shared bay every time.

    The lowest-numbered assigned bay is the rule a pair would fall into without
    a channel. It has to fail often enough that a run matching on every round
    cannot be explained by it.
    """
    agreed = 0
    layouts = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=100,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    )
    for depot in layouts:
        lowest = {min(depot.allowed_bays[agent_id]) for agent_id in AGENT_IDS}
        agreed += len(lowest) == 1
    assert agreed < len(layouts) // 2


def test_a_floor_too_small_for_its_bays_is_refused() -> None:
    with pytest.raises(ValueError, match="No move_a_box layout"):
        generate_depots(
            seed=42,
            agent_ids=AGENT_IDS,
            crates_each=1,
            bay_identities=(BayIdentity.SQUARE,),
            grid_size=3,
            bay_count=BAY_COUNT,
            bays_allowed_each=BAYS_ALLOWED_EACH,
            bays_differ=True,
            crate_start=CrateStart.CORNER,
            pallet_density=0.0,
        )


def test_the_floor_drawing_marks_the_start_and_every_bay() -> None:
    """Every bay is drawn and none is numbered: a bay is named by its square."""
    [depot] = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=1,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    )
    rows = floor_rows(depot=depot, agent_id=AGENT_IDS[0], grid_size=GRID_SIZE)
    assert len(rows) == GRID_SIZE
    drawing = "\n".join(rows)
    assert drawing.startswith("C")
    assert drawing.count("B") == BAY_COUNT
    for number in range(1, BAY_COUNT + 1):
        assert f"B{number}" not in drawing
    assert "#" not in drawing


def test_the_floor_drawing_marks_pallets_when_the_floor_has_them() -> None:
    [depot] = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=1,
        crate_start=CrateStart.CORNER,
        pallet_density=0.2,
    )
    drawing = "\n".join(floor_rows(depot=depot, agent_id=AGENT_IDS[0], grid_size=GRID_SIZE))
    assert "#" in drawing


def test_the_inert_readings_do_not_answer_to_either_operator() -> None:
    """Crate markings never change, and the humidity walk comes from the seed alone."""
    tags = crate_tags(seed=42, crate_ids=AGENT_IDS)
    assert tags == crate_tags(seed=42, crate_ids=AGENT_IDS)
    assert len({tag.crate_id for tag in tags.values()}) == len(AGENT_IDS)
    series = humidity_series(seed=42, round_number=1, length=STEPS)
    assert series == humidity_series(seed=42, round_number=1, length=STEPS)
    assert len(series) == STEPS + 1
    assert all(40 <= reading <= 60 for reading in series)


def test_four_operators_share_exactly_one_bay_and_keep_the_rest_apart() -> None:
    """The shared bay is the only thing any pair holds in common, however many run."""
    four = operator_ids(operator_count=4)
    layouts = generate_depots(
        seed=42,
        agent_ids=four,
        crates_each=1,
        bay_identities=(BayIdentity.SQUARE,) * 40,
        grid_size=9,
        bay_count=9,
        bays_allowed_each=3,
        bays_differ=True,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    )
    for depot in layouts:
        assert sorted(depot.allowed_bays) == sorted(four)
        lists: list[set[int]] = [set(depot.allowed_bays[agent_id]) for agent_id in four]
        assert all(len(bays) == 3 for bays in lists)
        on_every_list = lists[0]
        for bays in lists[1:]:
            on_every_list = on_every_list & bays
        assert len(on_every_list) == 1
        for index, bays in enumerate(lists):
            for other in lists[index + 1 :]:
                assert len(bays & other) == 1


def test_a_bay_count_too_small_for_the_roster_is_refused() -> None:
    """Five operators at three bays each need 11 bays; nine cannot seat them."""
    config = MoveABoxScenario.load_knobs_preset(preset_name="knobs_default")
    config.update({"operator_count": 5, "bays_allowed_each": 3, "bay_count": 9, "grid_size": 9})
    with pytest.raises(ValueError, match="bay_count must be at least 11"):
        MoveABoxKnobs.model_validate(config)


def test_two_crates_each_share_one_bay_per_slot() -> None:
    """Every crate slot needs a meeting place, so the shared set grows with crates_each."""
    pair = operator_ids(operator_count=2)
    layouts = generate_depots(
        seed=42,
        agent_ids=pair,
        crates_each=2,
        bay_identities=(BayIdentity.SQUARE,) * 30,
        grid_size=8,
        bay_count=6,
        bays_allowed_each=3,
        bays_differ=True,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    )
    for depot in layouts:
        lists: list[set[int]] = [set(depot.allowed_bays[agent_id]) for agent_id in pair]
        on_every_list = lists[0]
        for bays in lists[1:]:
            on_every_list = on_every_list & bays
        assert len(on_every_list) == 2


def test_a_crate_cannot_have_more_crates_than_bays_on_its_list() -> None:
    """Three crates at two bays each leaves a slot with nowhere of its own to meet."""
    config = MoveABoxScenario.load_knobs_preset(preset_name="knobs_default")
    config.update({"crates_each": 3, "bays_allowed_each": 2})
    with pytest.raises(ValueError, match="bays_allowed_each must be at least crates_each=3"):
        MoveABoxKnobs.model_validate(config)


MARKED = (BayIdentity.SYMBOL, BayIdentity.LETTER)
"""The identities under which each floor holds its own bays, named by the mark they carry."""


def marked_depots(
    bay_identity: BayIdentity, round_count: int, pallet_density: float
) -> list[RoundDepot]:
    """Marked bays on the default floor, each crate from a square of its own."""
    return depots(
        bays_differ=True,
        bay_identity=bay_identity,
        round_count=round_count,
        crate_start=CrateStart.SEPARATE_RANDOM,
        pallet_density=pallet_density,
    )


@pytest.mark.parametrize("bay_identity", MARKED)
def test_a_marked_floor_holds_only_the_bays_its_operator_was_assigned(
    bay_identity: BayIdentity,
) -> None:
    for depot in marked_depots(bay_identity=bay_identity, round_count=40, pallet_density=0.1):
        for agent_id in AGENT_IDS:
            numbers = [bay.number for bay in depot.bays[agent_id]]
            assert sorted(numbers) == list(depot.allowed_bays[agent_id])
            assert len(numbers) == BAYS_ALLOWED_EACH


@pytest.mark.parametrize("bay_identity", MARKED)
def test_no_two_marked_floors_put_a_bay_on_the_same_square(bay_identity: BayIdentity) -> None:
    """The square says nothing about the other floor, so the mark is all that matches."""
    for depot in marked_depots(bay_identity=bay_identity, round_count=40, pallet_density=0.1):
        first, second = (bay_cells(depot=depot, agent_id=agent_id) for agent_id in AGENT_IDS)
        assert not first & second
        shared = set(depot.allowed_bays[AGENT_IDS[0]]) & set(depot.allowed_bays[AGENT_IDS[1]])
        assert len(shared) == 1


@pytest.mark.parametrize("bay_identity", MARKED)
def test_a_marked_floor_keeps_every_bay_walkable_and_clear_of_the_start(
    bay_identity: BayIdentity,
) -> None:
    for depot in marked_depots(bay_identity=bay_identity, round_count=40, pallet_density=0.2):
        for agent_id in AGENT_IDS:
            start = depot.starts[agent_id]
            distances = distances_from(
                start=start, blocked=depot.pallets[agent_id], grid_size=GRID_SIZE
            )
            for cell in bay_cells(depot=depot, agent_id=agent_id):
                assert cell in distances
                assert manhattan(first=start, second=cell) >= MIN_START_SEPARATION


def test_where_a_mark_stands_does_not_follow_its_number() -> None:
    """Marks are dealt to a floor's squares at random, so reading order names no mark.

    Were the lowest-numbered mark always the topmost bay, a pair reading the
    floor top to bottom would agree as often as a pair sorting the marks.
    """
    topmost_is_lowest = 0
    layouts = marked_depots(bay_identity=BayIdentity.SYMBOL, round_count=200, pallet_density=0.0)
    for depot in layouts:
        bays = depot.bays[AGENT_IDS[0]]
        topmost_is_lowest += bays[0].number == min(bay.number for bay in bays)
    assert 0 < topmost_is_lowest < len(layouts) // 2


@pytest.mark.parametrize("bay_identity", MARKED)
def test_a_marked_floor_draws_its_own_bays_by_their_marks_and_nothing_else(
    bay_identity: BayIdentity,
) -> None:
    """The only marks on the drawing are the crate's start and this operator's bays."""
    for depot in marked_depots(bay_identity=bay_identity, round_count=10, pallet_density=0.0):
        for agent_id in AGENT_IDS:
            rows = floor_rows(depot=depot, agent_id=agent_id, grid_size=GRID_SIZE)
            marks = [mark for row in rows for mark in row.split() if mark != "."]
            expected = [bay_identity.crate_mark()] + [
                depot.bay_mark(number=number) for number in depot.allowed_bays[agent_id]
            ]
            assert sorted(marks) == sorted(expected)


def test_a_letter_floor_draws_the_crate_as_an_at_sign_because_c_is_a_bay() -> None:
    assert BayIdentity.LETTER.crate_mark() == "@"
    assert BayIdentity.SYMBOL.crate_mark() == "C"
    assert BayIdentity.SQUARE.crate_mark() == "C"


def test_a_bay_is_named_by_its_symbol_its_letter_or_its_square() -> None:
    [symbol_depot] = marked_depots(
        bay_identity=BayIdentity.SYMBOL, round_count=1, pallet_density=0.0
    )
    assert symbol_depot.bay_name(number=1) == BAY_SYMBOLS[0].name
    assert symbol_depot.bay_mark(number=1) == BAY_SYMBOLS[0].glyph
    [letter_depot] = marked_depots(
        bay_identity=BayIdentity.LETTER, round_count=1, pallet_density=0.0
    )
    assert letter_depot.bay_name(number=4) == "D"
    assert letter_depot.bay_mark(number=4) == "D"
    [square_depot] = depots(
        bays_differ=True,
        bay_identity=BayIdentity.SQUARE,
        round_count=1,
        crate_start=CrateStart.CORNER,
        pallet_density=0.0,
    )
    first = square_depot.bays[AGENT_IDS[0]][0]
    assert square_depot.bay_name(number=first.number) == first.cell.label()


@pytest.mark.parametrize("preset_name", ["knobs_symbol_bays", "knobs_letter_bays"])
def test_a_marked_floor_too_small_for_one_operator_s_bays_is_refused(preset_name: str) -> None:
    """Under marked bays the floor only has to hold one operator's list."""
    config = MoveABoxScenario.load_knobs_preset(preset_name=preset_name)
    config.update({"grid_size": 4, "bays_allowed_each": 5, "bay_count": 9, "steps_per_round": 10})
    with pytest.raises(ValueError, match="grid_size is too small for 5 bays on one floor"):
        MoveABoxKnobs.model_validate(config)


def test_a_switch_from_letters_to_symbols_keeps_every_square_and_changes_only_the_marks() -> None:
    """Symbol and letter floors share one draw, so a switched round is the same floor relabelled."""
    letters = (BayIdentity.LETTER,) * 10
    switched = (BayIdentity.LETTER,) * 5 + (BayIdentity.SYMBOL,) * 5
    plain, mixed = (
        generate_depots(
            seed=42,
            agent_ids=AGENT_IDS,
            bay_identities=identities,
            grid_size=GRID_SIZE,
            bay_count=BAY_COUNT,
            bays_allowed_each=BAYS_ALLOWED_EACH,
            crates_each=1,
            bays_differ=True,
            crate_start=CrateStart.SEPARATE_RANDOM,
            pallet_density=0.1,
        )
        for identities in (letters, switched)
    )
    for before, after, identity in zip(plain, mixed, switched, strict=True):
        assert after.bay_identity is identity
        assert after.bays == before.bays
        assert after.starts == before.starts
        assert after.allowed_bays == before.allowed_bays
        assert after.pallets == before.pallets


def letters_then(overrides: dict[str, object]) -> dict[str, object]:
    """The letters-then-symbols preset with ``overrides`` applied."""
    config = MoveABoxScenario.load_knobs_preset(preset_name="knobs_letters_then_symbols")
    config.update(overrides)
    return config


def test_the_identity_switches_at_the_round_the_knob_names() -> None:
    knobs = MoveABoxKnobs.model_validate(letters_then(overrides={}))
    assert [knobs.bay_identity_of(round_number=n) for n in (1, 5, 6, 10)] == [
        BayIdentity.LETTER,
        BayIdentity.LETTER,
        BayIdentity.SYMBOL,
        BayIdentity.SYMBOL,
    ]


def test_a_switch_to_square_bays_is_refused() -> None:
    """Square bays lay out every floor differently, which no briefing can announce midway."""
    with pytest.raises(ValueError, match="switches only between symbol and letter"):
        MoveABoxKnobs.model_validate(
            letters_then(overrides={"bay_identity_from_round": {6: "square"}})
        )


def test_a_switch_outside_the_run_is_refused() -> None:
    for start in (1, 11):
        with pytest.raises(ValueError, match="a switch takes effect at a round between 2"):
            MoveABoxKnobs.model_validate(
                letters_then(overrides={"bay_identity_from_round": {start: "symbol"}})
            )
