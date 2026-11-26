"""The random-square and start-square baselines of the first_item reward, for a set of seeds.

The boards of each seed come from the game config. Each baseline counts the player-rounds that end
on the alphabetically first item of the player's own grid:

- random square: the expected count when each player ends on a random square of its grid;
- start square: the count when each player stays on its start square and never moves.

Both counts depend on the seeds' boards, so compare a count of first-item finishes with the
baselines of the same seeds. Run it in GlossoGen's environment, from this project's folder:

    cd modal/platoon && VIRTUAL_ENV= uv run --no-sync --project ../.. \\
      python -m glossogen_side.first_item_baselines \\
      --game-config configs/signal_game_shapes.json --games-per-seed 6 --seeds $(seq 45 56)
"""

import argparse
import json
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.scenarios.signal_game.board import generate_boards


class Baselines(NamedTuple):
    """The two baselines of a set of games, out of their player-rounds."""

    random_square: float
    start_square: int
    player_rounds: int


def seed_baselines(*, config: dict[str, Any], seed: int) -> Baselines:
    """The baselines of one game on ``seed``."""
    random_square = 0.0
    start_square = 0
    player_rounds = 0
    boards = generate_boards(
        seed=seed,
        round_count=config["round_count"],
        grid_size=config["grid_size"],
        colour_count=config["colour_count"],
        shape_count=config["shape_count"],
        fill_count=config["fill_count"],
        word_count=config["word_count"],
    )
    for board in boards:
        for player, grid in board.grids.items():
            items = [item for row in grid for item in row]
            first = min(items)
            random_square += items.count(first) / len(items)
            start = board.starts[player]
            start_square += int(grid[start.row - 1][start.col - 1] == first)
            player_rounds += 1
    return Baselines(
        random_square=random_square, start_square=start_square, player_rounds=player_rounds
    )


def games_baselines(*, config: dict[str, Any], seeds: list[int], games_per_seed: int) -> Baselines:
    """The baselines of ``games_per_seed`` games on each of ``seeds``."""
    per_seed = [seed_baselines(config=config, seed=seed) for seed in seeds]
    return Baselines(
        random_square=games_per_seed * sum(baselines.random_square for baselines in per_seed),
        start_square=games_per_seed * sum(baselines.start_square for baselines in per_seed),
        player_rounds=games_per_seed * sum(baselines.player_rounds for baselines in per_seed),
    )


def main() -> None:
    """Print the baselines of ``--games-per-seed`` games on each of ``--seeds``."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game-config", required=True, type=Path)
    parser.add_argument("--games-per-seed", required=True, type=int)
    parser.add_argument("--seeds", required=True, type=int, nargs="+")
    arguments = parser.parse_args()
    config = json.loads(arguments.game_config.read_text())
    baselines = games_baselines(
        config=config, seeds=arguments.seeds, games_per_seed=arguments.games_per_seed
    )
    print(
        f"seeds {' '.join(map(str, arguments.seeds))}: "
        f"random square {baselines.random_square:.0f}/{baselines.player_rounds}, "
        f"start square {baselines.start_square}/{baselines.player_rounds}",
        flush=True,
    )


if __name__ == "__main__":
    main()
