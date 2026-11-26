"""The games of a training run that ended, one JSON line each in ``games.jsonl``.

The ledger is ``<records dir>/<run>/games.jsonl``. The loop enters a game once its ``glossogen
run`` has exited, whether or not the game finished.
When the loop plays a set of games again after a stop, it reuses each game that the ledger
holds. A game that has a log and no ledger entry was cut off by the stop: the loop moves its log
to ``game_logs/abandoned/``, adds the label ``abandoned`` to its run, and plays it again.
"""

import json
from pathlib import Path
from typing import NamedTuple

from loop_services import Game, LoopSettings, logged_run_id, run_folder, write_labels

from glossogen.run_storage.run_labels_file import read_run_labels

ABANDONED_LABEL = "abandoned"


class GameKey(NamedTuple):
    """A game's place in a run: its game set, its seed and its number within the seed."""

    game_set: str
    seed: int
    game: int


def ledger_path(*, settings: LoopSettings) -> Path:
    """The run's ledger of ended games."""
    return run_folder(settings=settings) / "games.jsonl"


def read_ledger(*, settings: LoopSettings) -> dict[GameKey, Game]:
    """Each ended game of the run, by its key."""
    path = ledger_path(settings=settings)
    if not path.exists():
        return {}
    ended: dict[GameKey, Game] = {}
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        key = GameKey(game_set=entry["game_set"], seed=entry["seed"], game=entry["game"])
        ended[key] = Game(
            seed=entry["seed"],
            game=entry["game"],
            adapter=entry["adapter"],
            run_id=entry["run_id"],
            returncode=entry["returncode"],
        )
    return ended


def record_game(*, settings: LoopSettings, game_set: str, game: Game) -> None:
    """Enter one ended game in the ledger."""
    path = ledger_path(settings=settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as ledger:
        ledger.write(json.dumps({"game_set": game_set, **game._asdict()}) + "\n")


def abandon(*, settings: LoopSettings, log_path: Path) -> None:
    """Move a cut-off game's log aside, and label its run ``abandoned`` when it has one."""
    run_id = logged_run_id(log_path=log_path)
    folder = log_path.parent / "abandoned"
    folder.mkdir(parents=True, exist_ok=True)
    attempt = len(list(folder.glob(f"{log_path.stem}.*")))
    log_path.rename(folder / f"{log_path.stem}.{attempt}.log")
    if run_id is None or not (settings.runs_dir / run_id).exists():
        print(f"abandoned {log_path.name}, which has no run", flush=True)
        return
    run_dir = settings.runs_dir / run_id
    write_labels(run_dir=run_dir, labels=[*read_run_labels(run_dir=run_dir), ABANDONED_LABEL])
    print(f"abandoned {run_id}, cut off by a stop", flush=True)
