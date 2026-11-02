"""The grid geometry and the boards drawn from the seed."""

import pytest
from pydantic import ValidationError

from glossogen.scenarios.signal_game.board import (
    ItemParts,
    Square,
    colour_order,
    fill_order,
    generate_boards,
    item_parts,
    items,
    path_length,
    shape_order,
    step,
)
from glossogen.scenarios.signal_game.ids import (
    AGENT_IDS,
    FILLS,
    PALETTE,
    PLAYER_A,
    PLAYER_B,
    SHAPES,
    Direction,
)
from glossogen.scenarios.signal_game.knobs import SignalGameKnobs
from glossogen.scenarios.signal_game.scenario import SignalGameScenario

TOP_LEFT = Square(row=1, col=1)


def test_a_move_off_the_grid_goes_nowhere() -> None:
    assert step(square=TOP_LEFT, direction=Direction.UP, grid_size=2) is None
    assert step(square=TOP_LEFT, direction=Direction.LEFT, grid_size=2) is None
    assert step(square=TOP_LEFT, direction=Direction.RIGHT, grid_size=2) == Square(row=1, col=2)


def test_the_shortest_path_is_the_manhattan_distance() -> None:
    assert path_length(start=TOP_LEFT, end=Square(row=2, col=2)) == 2
    assert path_length(start=TOP_LEFT, end=TOP_LEFT) == 0


def test_every_round_shares_a_colour_and_uses_only_the_palette() -> None:
    boards = generate_boards(
        seed=42, round_count=200, grid_size=2, colour_count=3, shape_count=0, fill_count=0
    )
    for round_boards in boards:
        first, second = (
            {colour for row in round_boards.grids[agent_id] for colour in row}
            for agent_id in AGENT_IDS
        )
        assert first & second
        assert first | second <= set(PALETTE[:3])


def test_each_player_starts_on_its_own_random_square() -> None:
    boards = generate_boards(
        seed=42, round_count=200, grid_size=3, colour_count=4, shape_count=0, fill_count=0
    )
    every_square = {Square(row=row, col=col) for row in range(1, 4) for col in range(1, 4)}
    for round_boards in boards:
        assert set(round_boards.starts) == set(AGENT_IDS)
        assert set(round_boards.starts.values()) <= every_square
    for agent_id in AGENT_IDS:
        assert {round_boards.starts[agent_id] for round_boards in boards} == every_square
    pairs = [
        tuple(round_boards.starts[agent_id] for agent_id in AGENT_IDS) for round_boards in boards
    ]
    assert any(first == second for first, second in pairs)
    assert any(first != second for first, second in pairs)


def test_the_same_seed_draws_the_same_boards() -> None:
    first = generate_boards(
        seed=7, round_count=5, grid_size=3, colour_count=4, shape_count=0, fill_count=0
    )
    second = generate_boards(
        seed=7, round_count=5, grid_size=3, colour_count=4, shape_count=0, fill_count=0
    )
    assert first == second


def test_each_player_lists_the_palette_in_its_own_order() -> None:
    orders = [
        tuple(colour_order(seed=seed, colour_count=4, agent_id=agent_id) for agent_id in AGENT_IDS)
        for seed in range(50)
    ]
    for pair in orders:
        for order in pair:
            assert sorted(order) == sorted(PALETTE[:4])
    assert any(first != second for first, second in orders)
    assert len({tuple(first) for first, _ in orders}) > 1


def test_seed_1042_starts_both_lists_with_the_same_colours() -> None:
    for agent_id in AGENT_IDS:
        assert colour_order(seed=1042, colour_count=4, agent_id=agent_id)[:2] == [
            "green",
            "yellow",
        ]


def test_seed_42_lists_the_orders_the_readme_quotes() -> None:
    assert colour_order(seed=42, colour_count=4, agent_id=PLAYER_A) == [
        "green",
        "yellow",
        "red",
        "blue",
    ]
    assert colour_order(seed=42, colour_count=4, agent_id=PLAYER_B) == [
        "blue",
        "green",
        "red",
        "yellow",
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"postmortem_enabled": True},
        {"compaction": {"enabled": True, "token_threshold": 96000}},
        {"shape_count": 0, "fill_count": 2},
    ],
)
def test_impossible_knobs_are_refused(overrides: dict[str, object]) -> None:
    config: dict[str, object] = {
        "round_count": 3,
        "max_round_duration_seconds": 60,
        "model_overrides": {},
        "grid_size": 2,
        "colour_count": 4,
        "moves_per_round": 12,
        "partner_colours_visible": False,
        "move_reasoning": True,
        "seed": 42,
        **overrides,
    }
    with pytest.raises(ValidationError):
        SignalGameScenario.create_from_config(config=config)


def test_the_base_of_the_impossible_knobs_is_possible() -> None:
    """So each refusal above comes from its override, not from the shared base."""
    config: dict[str, object] = {
        "round_count": 3,
        "max_round_duration_seconds": 60,
        "model_overrides": {},
        "grid_size": 3,
        "colour_count": 3,
        "shape_count": 3,
        "moves_per_round": 12,
        "partner_colours_visible": False,
        "move_reasoning": True,
        "seed": 42,
    }
    assert isinstance(SignalGameScenario.create_from_config(config=config), SignalGameScenario)


def test_seed_42_without_shapes_draws_the_boards_it_drew_before_shapes_existed() -> None:
    """The recorded colour-only runs replay and fork on these boards."""
    boards = generate_boards(
        seed=42, round_count=3, grid_size=2, colour_count=4, shape_count=0, fill_count=0
    )
    assert [round_boards.grids for round_boards in boards] == [
        {
            PLAYER_A: [["red", "red"], ["green", "blue"]],
            PLAYER_B: [["blue", "blue"], ["red", "red"]],
        },
        {
            PLAYER_A: [["yellow", "red"], ["red", "red"]],
            PLAYER_B: [["blue", "blue"], ["red", "blue"]],
        },
        {
            PLAYER_A: [["yellow", "blue"], ["yellow", "green"]],
            PLAYER_B: [["red", "blue"], ["yellow", "green"]],
        },
    ]
    assert [round_boards.starts for round_boards in boards] == [
        {PLAYER_A: Square(row=2, col=2), PLAYER_B: Square(row=2, col=2)},
        {PLAYER_A: Square(row=1, col=1), PLAYER_B: Square(row=2, col=1)},
        {PLAYER_A: Square(row=2, col=1), PLAYER_B: Square(row=1, col=1)},
    ]


def test_with_shapes_every_square_holds_a_coloured_shape_and_every_round_shares_one() -> None:
    every_item = set(items(colour_count=3, shape_count=3, fill_count=0))
    assert every_item == {f"{colour} {shape}" for colour in PALETTE[:3] for shape in SHAPES[:3]}
    boards = generate_boards(
        seed=42, round_count=200, grid_size=3, colour_count=3, shape_count=3, fill_count=0
    )
    for round_boards in boards:
        first, second = (
            {item for row in round_boards.grids[agent_id] for item in row} for agent_id in AGENT_IDS
        )
        assert first & second
        assert first | second <= every_item


def test_each_player_lists_the_shapes_in_its_own_order() -> None:
    orders = [
        tuple(shape_order(seed=seed, shape_count=4, agent_id=agent_id) for agent_id in AGENT_IDS)
        for seed in range(50)
    ]
    for pair in orders:
        for order in pair:
            assert sorted(order) == sorted(SHAPES[:4])
    assert any(first != second for first, second in orders)
    assert shape_order(seed=42, shape_count=0, agent_id=PLAYER_A) == []


def test_a_config_recorded_before_shapes_plays_the_same_game() -> None:
    recorded: dict[str, object] = {
        "colour_count": 4,
        "grid_size": 2,
        "max_round_duration_seconds": 600,
        "model_overrides": {},
        "move_reasoning": True,
        "moves_per_round": 200,
        "partner_colours_visible": False,
        "round_count": 10,
        "seed": 42,
    }
    knobs = SignalGameKnobs.model_validate(recorded)
    assert knobs.shape_count == 0
    assert knobs.fill_count == 0
    assert knobs.max_moves_per_call == 10


def test_with_fills_every_square_holds_a_filled_coloured_shape_and_every_round_shares_one() -> None:
    every_item = set(items(colour_count=3, shape_count=3, fill_count=3))
    assert len(every_item) == 27
    assert "striped red circle" in every_item
    boards = generate_boards(
        seed=42, round_count=100, grid_size=5, colour_count=3, shape_count=3, fill_count=3
    )
    for round_boards in boards:
        first, second = (
            {item for row in round_boards.grids[agent_id] for item in row} for agent_id in AGENT_IDS
        )
        assert first & second
        assert first | second <= every_item


def test_shapes_without_fills_draw_the_boards_they_drew_before_fills_existed() -> None:
    """Seed 42's first coloured-shapes round, as recorded by the runs made before fills."""
    [first_round] = generate_boards(
        seed=42, round_count=1, grid_size=3, colour_count=3, shape_count=3, fill_count=0
    )
    assert first_round.grids[PLAYER_A][1] == ["blue circle", "blue circle", "red star"]


def test_each_player_lists_the_fills_in_its_own_order() -> None:
    orders = [
        tuple(fill_order(seed=seed, fill_count=3, agent_id=agent_id) for agent_id in AGENT_IDS)
        for seed in range(50)
    ]
    for pair in orders:
        for order in pair:
            assert sorted(order) == sorted(FILLS)
    assert any(first != second for first, second in orders)


@pytest.mark.parametrize(
    ("item", "parts"),
    [
        ("red", ItemParts(colour="red", shape=None, fill=None)),
        ("red circle", ItemParts(colour="red", shape="circle", fill=None)),
        ("striped red circle", ItemParts(colour="red", shape="circle", fill="striped")),
    ],
)
def test_an_item_splits_into_its_parts(item: str, parts: ItemParts) -> None:
    assert item_parts(item=item) == parts
