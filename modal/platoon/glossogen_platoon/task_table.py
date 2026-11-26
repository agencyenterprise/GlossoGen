"""Write the task table of signal_game: one row per seed, in the ``train`` or the ``eval`` split.

Platoon's ``table`` service reads it. A training step draws ``train.batch_size`` training seeds and
plays ``workflow_config.group_size`` games on each; an evaluation plays the ``eval`` seeds. Run from
this project's folder:

    VIRTUAL_ENV= uv run --no-sync python -m glossogen_platoon.task_table \\
      --train-seeds $(seq 1000 1119) --eval-seeds $(seq 45 56) --out configs/signal_game_tasks.jsonl
"""

import argparse
import json
from pathlib import Path

GOAL = "Play one signal_game game."


def task_row(*, seed: int, split: str) -> str:
    """One row of the table, as a JSON line."""
    return json.dumps({"id": f"seed-{seed}", "goal": GOAL, "seed": seed, "split": split})


def table_lines(*, train_seeds: list[int], eval_seeds: list[int]) -> list[str]:
    """Every row of the table, training seeds first; refuse a seed in both splits."""
    shared = sorted(set(train_seeds) & set(eval_seeds))
    if shared:
        raise ValueError(f"seeds in both splits: {shared}")
    return [task_row(seed=seed, split="train") for seed in train_seeds] + [
        task_row(seed=seed, split="eval") for seed in eval_seeds
    ]


def main() -> None:
    """Write the table that the command line describes."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--train-seeds", required=True, type=int, nargs="+")
    parser.add_argument("--eval-seeds", required=True, type=int, nargs="+")
    parser.add_argument("--out", required=True, type=Path)
    arguments = parser.parse_args()
    lines = table_lines(train_seeds=arguments.train_seeds, eval_seeds=arguments.eval_seeds)
    arguments.out.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
