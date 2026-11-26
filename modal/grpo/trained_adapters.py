"""What an adapter's folder on the volume records about the training step that saved it.

The trainer saves adapter k with the step's metrics in ``metrics.json``. Once the adapter, its
optimizer state and the metrics are saved, it writes the sorted run ids of the games that the
step trained on to ``games.json``. ``saved_step`` reads both back. A repeated call for a step
whose adapter exists returns the saved metrics when it brings the same games, so a loop that
stopped after the trainer saved a step does not train on those games twice. It raises when the
games differ.

This module imports nothing outside the standard library: it runs in the trainer's image, and
the loop's tests run it on CPU.
"""

import json
from pathlib import Path

from grpo_records import StepMetrics

METRICS_FILE = "metrics.json"
GAMES_FILE = "games.json"


class AdapterTrainedOnOtherGames(ValueError):
    """An adapter exists, and the games it trained on are not the games of this call."""


def record_trained_games(*, directory: Path, run_ids: list[str]) -> None:
    """Write the run ids of the games that trained the adapter in ``directory``."""
    (directory / GAMES_FILE).write_text(json.dumps(sorted(run_ids)) + "\n")


def saved_step(*, directory: Path, run_ids: list[str]) -> StepMetrics | None:
    """The metrics of the step that saved the adapter in ``directory`` from these games.

    None when no adapter is saved there. Raises when the adapter holds no record of its games,
    or when it trained on other games.
    """
    if not directory.exists():
        return None
    games_path = directory / GAMES_FILE
    if not games_path.exists():
        raise ValueError(f"{directory} holds no {GAMES_FILE}, so its games are unknown")
    trained_on = json.loads(games_path.read_text())
    if trained_on != sorted(run_ids):
        raise AdapterTrainedOnOtherGames(
            f"{directory} trained on {len(trained_on)} other games than the {len(run_ids)} given"
        )
    return StepMetrics(**json.loads((directory / METRICS_FILE).read_text()))
