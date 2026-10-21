"""The grid geometry and the boards drawn from the seed."""

import pytest
from pydantic import ValidationError

from glossogen.scenarios.signal_game.board import (
    Square,
    colour_order,
    generate_boards,
    path_length,
    step,
)
from glossogen.scenarios.signal_game.ids import (
    AGENT_IDS,
    PALETTE,
    PLAYER_A,
    PLAYER_B,
    Direction,
    Medium,
)
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
    boards = generate_boards(seed=42, round_count=200, grid_size=2, colour_count=3)
    for round_boards in boards:
        first, second = (
            {colour for row in round_boards.grids[agent_id] for colour in row}
            for agent_id in AGENT_IDS
        )
        assert first & second
        assert first | second <= set(PALETTE[:3])


def test_each_player_starts_on_its_own_random_square() -> None:
    boards = generate_boards(seed=42, round_count=200, grid_size=3, colour_count=4)
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
    first = generate_boards(seed=7, round_count=5, grid_size=3, colour_count=4)
    second = generate_boards(seed=7, round_count=5, grid_size=3, colour_count=4)
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


def valid_config() -> dict[str, object]:
    return {
        "round_count": 3,
        "max_round_duration_seconds": 60,
        "model_overrides": {},
        "grid_size": 2,
        "colour_count": 4,
        "moves_per_round": 12,
        "partner_colours_visible": False,
        "move_reasoning": True,
        "seed": 42,
        "medium": "grid",
        "judge_model": "claude-haiku-5-5",
        "judge_provider": "anthropic",
        "commands_per_round": 200,
        "command_output_char_limit": 4000,
        "max_sleep_seconds": 30,
    }


def test_the_config_the_refusals_start_from_is_accepted() -> None:
    SignalGameScenario.create_from_config(config=valid_config())


def test_a_config_without_the_medium_knobs_plays_the_grid_game() -> None:
    """The knobs the ``file_system`` medium added default to the ``grid`` game."""
    medium_knobs = {
        "medium",
        "judge_model",
        "judge_provider",
        "commands_per_round",
        "command_output_char_limit",
        "max_sleep_seconds",
    }
    recorded = {key: value for key, value in valid_config().items() if key not in medium_knobs}
    scenario = SignalGameScenario.create_from_config(config=recorded)
    assert scenario.get_knobs().medium is Medium.GRID
    assert SignalGameScenario.get_judge_models(knobs=recorded) == ()
    for agent in scenario.get_agents(default_model="test", default_provider="anthropic"):
        assert agent.tool_names == ["move", "end_round"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"postmortem_enabled": True},
        {"compaction": {"enabled": True, "token_threshold": 96000}},
        {"grid_size": 2, "colour_count": 5},
        {"medium": "radio"},
    ],
)
def test_impossible_knobs_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SignalGameScenario.create_from_config(config={**valid_config(), **overrides})
