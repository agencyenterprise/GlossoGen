"""The loop's records: one line per training step in ``steps.jsonl``, one per test in
``eval.jsonl``, both in ``<records dir>/<run>/``."""

import json
from pathlib import Path
from typing import NamedTuple

from game_sets import PlayedGames
from grpo_records import StepMetrics
from partner import Partner, trained_seats
from pydantic import BaseModel
from step_batch import (
    Batch,
    FinishedGame,
    counts_by_seed,
    first_item_by_seat,
    first_item_count,
    player_rounds,
    rounds_won,
)


class StepRecord(NamedTuple):
    """What one training step played and what the trainer measured.

    ``adapter`` is the adapter that played the step's games. ``partner`` is the run's frozen
    partner, and ``trained_seats`` the seats whose answers trained. ``first_item_by_seat`` splits
    ``first_item`` by seat. ``play_seconds`` is how long the step's games took to play, and
    ``train_seconds`` how long the trainer took on them.
    """

    step: int
    adapter: int
    reward: str
    partner: Partner | None
    trained_seats: list[str]
    games: int
    finished: int
    rounds: int
    won: int
    first_item: int
    first_item_by_seat: dict[str, int]
    player_rounds: int
    won_by_seed: dict[str, list[int]]
    moves_per_player_round: float
    player_rounds_without_move: int
    answers: int
    answer_tokens: int
    sequence_tokens: int
    chain_breaks: int
    play_seconds: float
    train_seconds: float
    trainer: StepMetrics
    run_ids: list[str]


class EvalRecord(NamedTuple):
    """What one adapter scored on the evaluated seeds.

    ``won_by_seed`` and ``first_item_by_seed`` hold each finished game's rounds won and
    first-item finishes, in game order, grouped by seed. ``partner`` is the frozen partner that
    the adapter played with, and ``first_item_by_seat`` splits ``first_item`` by seat.
    """

    step: int
    partner: Partner | None
    won_by_seed: dict[str, list[int]]
    first_item_by_seed: dict[str, list[int]]
    won: int
    rounds: int
    first_item: int
    first_item_by_seat: dict[str, int]
    player_rounds: int


class StepOutcome(NamedTuple):
    """What a training step produced: its games, their batch, and the trainer's metrics."""

    played: PlayedGames
    finished: list[FinishedGame]
    built: Batch
    metrics: StepMetrics
    train_seconds: float


def step_record(
    *, step: int, adapter: int, reward: str, partner: Partner | None, outcome: StepOutcome
) -> StepRecord:
    """The record of a training step from what it produced."""
    finished = outcome.finished
    rounds = player_rounds(finished=finished)
    seats = tuple(sorted({seat for game in finished for seat in game.outcome.players}))
    return StepRecord(
        step=step,
        adapter=adapter,
        reward=reward,
        partner=partner,
        trained_seats=list(trained_seats(players=seats, partner=partner)),
        games=len(outcome.played.games),
        finished=len(finished),
        rounds=sum(len(game.outcome.rounds) for game in finished),
        won=sum(rounds_won(game.outcome) for game in finished),
        first_item=sum(first_item_count(game.outcome) for game in finished),
        first_item_by_seat=first_item_by_seat(finished=finished),
        player_rounds=rounds,
        won_by_seed=counts_by_seed(finished=finished, count=rounds_won),
        moves_per_player_round=sum(game.outcome.moves for game in finished) / max(1, rounds),
        player_rounds_without_move=sum(
            game.outcome.player_rounds_without_move for game in finished
        ),
        answers=outcome.built.answers,
        answer_tokens=outcome.built.answer_tokens,
        sequence_tokens=outcome.built.sequence_tokens,
        chain_breaks=outcome.built.chain_breaks,
        play_seconds=outcome.played.seconds,
        train_seconds=outcome.train_seconds,
        trainer=outcome.metrics,
        run_ids=sorted(game.run_id for game in outcome.played.games),
    )


def eval_record(*, step: int, partner: Partner | None, finished: list[FinishedGame]) -> EvalRecord:
    """The record of a test of adapter ``step`` from its finished games."""
    return EvalRecord(
        step=step,
        partner=partner,
        won_by_seed=counts_by_seed(finished=finished, count=rounds_won),
        first_item_by_seed=counts_by_seed(finished=finished, count=first_item_count),
        won=sum(rounds_won(game.outcome) for game in finished),
        rounds=sum(len(game.outcome.rounds) for game in finished),
        first_item=sum(first_item_count(game.outcome) for game in finished),
        first_item_by_seat=first_item_by_seat(finished=finished),
        player_rounds=player_rounds(finished=finished),
    )


def next_step(*, steps_path: Path) -> int:
    """The step after the last one that ``steps.jsonl`` records, or 0 when it records none.

    Raises when the recorded steps are not 0, 1, 2 and so on, each once.
    """
    if not steps_path.exists():
        return 0
    steps = [json.loads(line)["step"] for line in steps_path.read_text().splitlines()]
    if steps != list(range(len(steps))):
        raise ValueError(f"{steps_path} records the steps {steps}, not 0 to {len(steps) - 1}")
    return len(steps)


def jsonable(value: object) -> object:
    """``value`` with each NamedTuple in it as a JSON object, and each pydantic model dumped."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple) and hasattr(value, "_asdict"):
        return {key: jsonable(item) for key, item in value._asdict().items()}
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    return value


def append_record(*, path: Path, record: tuple[object, ...]) -> None:
    """Append one record, a NamedTuple, to ``path`` as one JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as log:
        log.write(json.dumps(jsonable(record)) + "\n")


def print_step(*, record: StepRecord) -> None:
    """Print one line that summarizes a training step."""
    print(
        f"step {record.step}: {record.finished}/{record.games} games finished, "
        f"won {record.won}/{record.rounds} rounds, "
        f"first item {record.first_item}/{record.player_rounds} player-rounds, "
        f"{record.answers} answers ({record.answer_tokens} tokens), "
        f"kl {record.trainer.kl:.5f}, grad norm {record.trainer.grad_norm:.4f}, "
        f"play {record.play_seconds:.0f}s, train {record.train_seconds:.0f}s",
        flush=True,
    )


def print_eval(*, record: EvalRecord, finished: int, games: int) -> None:
    """Print one line that summarizes a test of an adapter."""
    print(
        f"eval step {record.step}: {finished}/{games} games finished, "
        f"won {record.won}/{record.rounds} rounds, "
        f"first item {record.first_item}/{record.player_rounds} player-rounds",
        flush=True,
    )
