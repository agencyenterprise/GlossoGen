"""The grid geometry and the boards drawn from the seed."""

import pytest
from pydantic import ValidationError

from glossogen.scenarios.signal_game.board import (
    START_SQUARE,
    Square,
    generate_boards,
    path_length,
    step,
)
from glossogen.scenarios.signal_game.ids import AGENT_IDS, PALETTE, Direction
from glossogen.scenarios.signal_game.scenario import SignalGameScenario


def test_a_move_off_the_grid_goes_nowhere() -> None:
    assert step(square=START_SQUARE, direction=Direction.UP, grid_size=2) is None
    assert step(square=START_SQUARE, direction=Direction.LEFT, grid_size=2) is None
    assert step(square=START_SQUARE, direction=Direction.RIGHT, grid_size=2) == Square(row=1, col=2)


def test_the_shortest_path_is_the_manhattan_distance() -> None:
    assert path_length(start=START_SQUARE, end=Square(row=2, col=2)) == 2
    assert path_length(start=START_SQUARE, end=START_SQUARE) == 0


def test_every_round_shares_a_colour_and_uses_only_the_palette() -> None:
    boards = generate_boards(seed=42, round_count=200, grid_size=2, colour_count=3)
    for round_boards in boards:
        first, second = (
            {colour for row in round_boards.grids[agent_id] for colour in row}
            for agent_id in AGENT_IDS
        )
        assert first & second
        assert first | second <= set(PALETTE[:3])


def test_the_same_seed_draws_the_same_boards() -> None:
    first = generate_boards(seed=7, round_count=5, grid_size=3, colour_count=4)
    second = generate_boards(seed=7, round_count=5, grid_size=3, colour_count=4)
    assert first == second


@pytest.mark.parametrize(
    "overrides",
    [
        {"postmortem_enabled": True},
        {"compaction": {"enabled": True, "token_threshold": 96000}},
        {"grid_size": 2, "colour_count": 5},
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
        "seed": 42,
        **overrides,
    }
    with pytest.raises(ValidationError):
        SignalGameScenario.create_from_config(config=config)
