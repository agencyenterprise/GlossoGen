"""Count each evaluation's first-item finishes and won rounds, from a platoon run's folder.

``platoon train`` writes each evaluation's rollouts under ``rollouts/eval/<step>/events/``. The root
trajectory of each rollout records its game's scores (``misc["glossogen"]``, a ``PlayedGame``), and
this report sums them over the games of each evaluation. Run from this project's folder:

    VIRTUAL_ENV= uv run --no-sync python -m glossogen_platoon.eval_report \\
      --run ../../runs/platoon/signal-game/first-item
"""

import argparse
import json
from pathlib import Path
from typing import NamedTuple

from glossogen_platoon.game_scores import PlayedGame

FINISHED_EVENT = "trajectory_finished"
FIRST_ITEM = "first_item"
WIN = "win"


class EvalCounts(NamedTuple):
    """One evaluation's totals over its finished games."""

    step: int
    games: int
    first_item: int
    player_rounds: int
    won: int
    rounds: int


def played_games(*, events_file: Path) -> list[PlayedGame]:
    """The games whose scores a rollout's event file records, once each."""
    games: dict[str, PlayedGame] = {}
    for line in events_file.read_text().splitlines():
        event = json.loads(line)
        if event["type"] == FINISHED_EVENT and "glossogen" in event["misc"]:
            game = PlayedGame.model_validate(event["misc"]["glossogen"])
            games[game.run_id] = game
    return list(games.values())


def seat_total(*, game: PlayedGame, reward: str) -> int:
    """The game's scores under ``reward``, summed over its seats and rounds."""
    return sum(sum(seat.scores[reward].values()) for seat in game.scores.seats.values())


def eval_counts(*, step: int, games: list[PlayedGame]) -> EvalCounts:
    """The totals of one evaluation; a won round counts once, not once per seat."""
    finished = [game for game in games if game.scores.finished]
    return EvalCounts(
        step=step,
        games=len(finished),
        first_item=sum(seat_total(game=game, reward=FIRST_ITEM) for game in finished),
        player_rounds=sum(len(game.scores.seats) * len(game.scores.rounds) for game in finished),
        won=sum(seat_total(game=game, reward=WIN) // len(game.scores.seats) for game in finished),
        rounds=sum(len(game.scores.rounds) for game in finished),
    )


def run_report(*, run: Path) -> list[EvalCounts]:
    """The totals of each evaluation of the run, by step."""
    steps = sorted(int(folder.name) for folder in (run / "rollouts" / "eval").iterdir())
    report: list[EvalCounts] = []
    for step in steps:
        events = sorted((run / "rollouts" / "eval" / str(step) / "events").glob("*.jsonl"))
        games = [game for events_file in events for game in played_games(events_file=events_file)]
        report.append(eval_counts(step=step, games=games))
    return report


def main() -> None:
    """Print one line per evaluation."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True, type=Path)
    arguments = parser.parse_args()
    for counts in run_report(run=arguments.run):
        print(
            f"eval step {counts.step}: {counts.games} games finished, "
            f"won {counts.won}/{counts.rounds} rounds, "
            f"first item {counts.first_item}/{counts.player_rounds} player-rounds",
            flush=True,
        )


if __name__ == "__main__":
    main()
