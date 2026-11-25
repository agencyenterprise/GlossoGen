"""GRPO on signal_game: the loop that plays, scores and trains, run on your machine.

Each training step k:

1. asks the policy server in grpo_app.py to load adapter k under the model name
   ``<run>-step<k>``;
2. plays ``--games-per-seed`` signal_game games on each of ``--seeds-per-step`` new seeds, with
   both players on that model and ``record_token_ids`` on;
3. scores each player in each round with the reward from signal_game_rewards.py. A player's
   advantage in a round is its score minus the mean score of the same seat (player_a or player_b)
   in the same round, over the seed's finished games;
4. builds training sequences from the token ids that each finished game logged
   (token_sequences.py), and sends them to the trainer, which saves adapter k+1;
5. appends the step's record to ``<records dir>/<run>/steps.jsonl``.

A game that ends without ``simulation_ended`` is left out of the batch. When a seed has fewer
than 2 finished games, every answer token of its finished game gets advantage 0. Training stops
after a step whose KL per marked token is above MAX_KL, or in which fewer than MIN_FINISHED_SHARE
of the games that started finished.

Run it from the repository root. docs/rl-training.md gives the commands.
"""

import argparse
import asyncio
import json
import os
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from grpo_records import StepMetrics, TrainingSequence
from signal_game_rewards import GameOutcome, PlayerRound, Reward, game_outcome, player_score
from token_sequences import game_sequences

import modal
from glossogen.models.event import SimulationEvent
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_labels_file import RUN_LABELS_FILENAME
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SCENARIO = "signal_game"
TRAINING_LABEL = "grpo"
EVAL_LABEL = "grpo_eval"
FIRST_TRAINING_SEED = 1000
MAX_AGENT_TURNS = 400
LAUNCH_GAP_SECONDS = 5
RUN_ID_WAIT_SECONDS = 300
ADAPTER_LOAD_WAIT_SECONDS = 1800
MAX_KL = 0.3
MIN_FINISHED_SHARE = 0.75


class LoopSettings(NamedTuple):
    """Where a training run lives: its Modal app, its name, and its local folders."""

    app_name: str
    run_name: str
    runs_dir: Path
    records_dir: Path
    game_config: Path
    concurrency: int


class Game(NamedTuple):
    """One game that the loop launched, by its seed, its number within the seed and its run id."""

    seed: int
    game: int
    run_id: str
    returncode: int


class FinishedGame(NamedTuple):
    """A game that ended with ``simulation_ended``, with its events and its outcome."""

    game: Game
    events: list[SimulationEvent]
    outcome: GameOutcome


class PlayerRoundAdvantage(NamedTuple):
    """One player's advantage in one round of one game."""

    run_id: str
    player_round: PlayerRound
    advantage: float


class Batch(NamedTuple):
    """The training sequences of a step, and counts that describe them."""

    sequences: list[TrainingSequence]
    answers: int
    answer_tokens: int
    sequence_tokens: int
    chain_breaks: int


class StepRecord(NamedTuple):
    """What one training step played and what the trainer measured."""

    step: int
    reward: str
    games: int
    finished: int
    rounds: int
    won: int
    first_item: int
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
    first-item finishes, in game order, grouped by seed.
    """

    step: int
    won_by_seed: dict[str, list[int]]
    first_item_by_seed: dict[str, list[int]]
    won: int
    rounds: int
    first_item: int
    player_rounds: int


def run_folder(*, settings: LoopSettings) -> Path:
    """The local folder of the training run's configs, game logs and records."""
    return settings.records_dir / settings.run_name


def model_name(*, run_name: str, step: int) -> str:
    """The model name under which the policy server plays adapter ``step``."""
    return f"{run_name}-step{step}"


def adapter_path(*, run_name: str, step: int) -> str:
    """Where grpo_app.py saves adapter ``step`` on its volume, as the server sees it."""
    return f"/grpo/runs/{run_name}/adapters/step_{step}"


def seeds_for(*, step: int, seeds_per_step: int) -> list[int]:
    """The training seeds of ``step``: new ones in every step."""
    first = FIRST_TRAINING_SEED + step * seeds_per_step
    return list(range(first, first + seeds_per_step))


async def serve_url(*, app_name: str) -> str:
    """The ``/v1`` URL of the policy server of the deployed app."""
    url = await modal.Function.from_name(app_name, "serve").get_web_url.aio()
    if url is None:
        raise RuntimeError(f"{app_name}'s serve function has no web URL; is the app deployed?")
    return f"{url}/v1"


async def load_adapter(*, settings: LoopSettings, step: int) -> None:
    """Ask the policy server to load adapter ``step``, and wait until it reports the outcome."""
    control = modal.Dict.from_name(f"{settings.app_name}-adapters", create_if_missing=True)
    request_id = str(uuid.uuid4())
    name = model_name(run_name=settings.run_name, step=step)
    path = adapter_path(run_name=settings.run_name, step=step)
    await control.put.aio("request", {"id": request_id, "name": name, "path": path})
    deadline = time.monotonic() + ADAPTER_LOAD_WAIT_SECONDS
    while time.monotonic() < deadline:
        result = await control.get.aio("result")
        if result is not None and result["id"] == request_id:
            already_loaded = result["status"] == 400 and "has already been loaded" in result["body"]
            if result["status"] != 200 and not already_loaded:
                raise RuntimeError(f"loading {name} failed: {result['status']} {result['body']}")
            print(f"loaded {name}", flush=True)
            return
        await asyncio.sleep(5)
    raise RuntimeError(f"the policy server did not load {name} within {ADAPTER_LOAD_WAIT_SECONDS}s")


def seed_config(*, settings: LoopSettings, seed: int) -> Path:
    """The game config for ``seed``: the base config with its seed replaced, written once."""
    path = run_folder(settings=settings) / "configs" / f"seed_{seed}.json"
    if path.exists():
        return path
    config = json.loads(settings.game_config.read_text())
    if config.get("record_token_ids") is not True:
        raise ValueError(f"{settings.game_config} must set record_token_ids to true")
    config["seed"] = seed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return path


def game_environment(*, model: str, url: str) -> dict[str, str]:
    """This process's environment for a game, with ``model`` served at ``url``."""
    environment = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    environment["SELF_HOSTED_BASE_URLS"] = json.dumps({model: url})
    return environment


async def wait_for_run_id(*, log_path: Path, process: asyncio.subprocess.Process) -> str:
    """The run id that ``glossogen run`` prints once it has created the run directory."""
    for _ in range(RUN_ID_WAIT_SECONDS):
        match = re.search(r"new_run_id=(\S+)", log_path.read_text(errors="replace"))
        if match:
            return match.group(1)
        if process.returncode is not None:
            raise RuntimeError(f"{log_path.name}: exited {process.returncode} before a run id")
        await asyncio.sleep(1)
    raise RuntimeError(f"{log_path.name}: no run id after {RUN_ID_WAIT_SECONDS}s")


async def play_game(
    *, settings: LoopSettings, step: int, seed: int, game: int, url: str, labels: list[str]
) -> Game:
    """Play one game with adapter ``step`` and label its run."""
    name = f"step{step}_seed{seed}_game{game}"
    log_path = run_folder(settings=settings) / "game_logs" / f"{labels[0]}_{name}.log"
    if log_path.exists():
        raise RuntimeError(f"{log_path} exists; not playing that game again")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    model = model_name(run_name=settings.run_name, step=step)
    command = [
        "uv", "run", "--no-sync", "python", "-m", "glossogen", "run", SCENARIO,
        "--model", model, "--provider", "self-hosted",
        "--runs-dir", str(settings.runs_dir), "--max-agent-turns", str(MAX_AGENT_TURNS),
        "--config", str(seed_config(settings=settings, seed=seed)),
    ]  # fmt: skip
    with log_path.open("w") as log_file:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            env=game_environment(model=model, url=url),
        )
        run_id = await wait_for_run_id(log_path=log_path, process=process)
        game_labels = [
            *labels,
            f"run={settings.run_name}",
            f"step={step}",
            f"seed={seed}",
            f"game={game}",
        ]
        labels_path = settings.runs_dir / run_id / RUN_LABELS_FILENAME
        labels_path.write_text(json.dumps(game_labels) + "\n")
        returncode = await process.wait()
    return Game(seed=seed, game=game, run_id=run_id, returncode=returncode)


async def play_games(
    *,
    settings: LoopSettings,
    step: int,
    seeds: list[int],
    games_per_seed: int,
    labels: list[str],
) -> list[Game]:
    """Play every game of a step, ``settings.concurrency`` at a time.

    Once a game gets a slot, it waits LAUNCH_GAP_SECONDS times its index modulo
    ``settings.concurrency`` before it starts.
    """
    url = await serve_url(app_name=settings.app_name)
    slots = asyncio.Semaphore(settings.concurrency)
    specs = [(seed, game) for game in range(1, games_per_seed + 1) for seed in seeds]

    async def guarded(index: int, seed: int, game: int) -> Game:
        async with slots:
            await asyncio.sleep(LAUNCH_GAP_SECONDS * (index % settings.concurrency))
            return await play_game(
                settings=settings, step=step, seed=seed, game=game, url=url, labels=labels
            )

    results = await asyncio.gather(
        *(guarded(index, seed, game) for index, (seed, game) in enumerate(specs)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            print(f"a game failed to start or to run: {result!r}", flush=True)
    return [result for result in results if isinstance(result, Game)]


async def finished_games(*, settings: LoopSettings, games: list[Game]) -> list[FinishedGame]:
    """The games whose event log holds ``simulation_ended``, read with their outcomes."""
    finished: list[FinishedGame] = []
    for game in games:
        log_path = event_log_path(run_dir=settings.runs_dir / game.run_id, scenario_name=SCENARIO)
        events = await load_events(log_path=log_path)
        outcome = game_outcome(events=events)
        if outcome.finished:
            finished.append(FinishedGame(game=game, events=events, outcome=outcome))
    return finished


def seed_advantages(*, group: list[FinishedGame], reward: Reward) -> list[PlayerRoundAdvantage]:
    """Each player's score in each round, minus the seat's mean score in that round in the group."""
    if len(group) < 2:
        return []
    advantages: list[PlayerRoundAdvantage] = []
    player_rounds = {
        PlayerRound(player=player, round_number=round_number)
        for finished in group
        for player in finished.outcome.players
        for round_number in finished.outcome.rounds
    }
    for player_round in sorted(player_rounds):
        scores = [
            player_score(outcome=finished.outcome, player_round=player_round, reward=reward)
            for finished in group
        ]
        mean = sum(scores) / len(scores)
        for finished, score in zip(group, scores, strict=True):
            advantages.append(
                PlayerRoundAdvantage(
                    run_id=finished.game.run_id,
                    player_round=player_round,
                    advantage=score - mean,
                )
            )
    return advantages


def step_advantages(*, finished: list[FinishedGame], reward: Reward) -> list[PlayerRoundAdvantage]:
    """The advantages of every finished game, each against the mean of its seed's finished games."""
    by_seed: dict[int, list[FinishedGame]] = defaultdict(list)
    for game in finished:
        by_seed[game.game.seed].append(game)
    return [
        advantage
        for group in by_seed.values()
        for advantage in seed_advantages(group=group, reward=reward)
    ]


def batch(*, finished: list[FinishedGame], advantages: list[PlayerRoundAdvantage]) -> Batch:
    """Every finished game's training sequences, one player at a time."""
    sequences: list[TrainingSequence] = []
    answers = answer_tokens = sequence_tokens = chain_breaks = 0
    for game in finished:
        for player in game.outcome.players:
            by_round = {
                advantage.player_round.round_number: advantage.advantage
                for advantage in advantages
                if advantage.run_id == game.game.run_id and advantage.player_round.player == player
            }
            built = game_sequences(events=game.events, agent_id=player, advantages=by_round)
            sequences.extend(built.sequences)
            answers += built.answers
            answer_tokens += built.answer_tokens
            sequence_tokens += built.sequence_tokens
            chain_breaks += built.chain_breaks
    return Batch(
        sequences=sequences,
        answers=answers,
        answer_tokens=answer_tokens,
        sequence_tokens=sequence_tokens,
        chain_breaks=chain_breaks,
    )


def trainer(*, app_name: str, run_name: str) -> Any:
    """The deployed trainer of training run ``run_name``."""
    return modal.Cls.from_name(app_name, "Trainer")(run_name=run_name)


def counts_by_seed(
    *, finished: list[FinishedGame], count: Callable[[GameOutcome], int]
) -> dict[str, list[int]]:
    """``count`` of each finished game's outcome, in game order, grouped by seed."""
    grouped: dict[str, list[int]] = defaultdict(list)
    for game in sorted(finished, key=lambda game: (game.game.seed, game.game.game)):
        grouped[str(game.game.seed)].append(count(game.outcome))
    return dict(grouped)


def rounds_won(outcome: GameOutcome) -> int:
    """The number of rounds that the game's players won."""
    return len(outcome.won_rounds)


def first_item_count(outcome: GameOutcome) -> int:
    """The number of the game's player-rounds that ended on the player's first item."""
    return len(outcome.first_item_finishes)


async def run_step(
    *,
    settings: LoopSettings,
    step: int,
    reward: Reward,
    seeds_per_step: int,
    games_per_seed: int,
) -> StepRecord:
    """Play, score and train one step. Adapter ``step`` plays, and adapter ``step + 1`` is saved."""
    began = time.monotonic()
    await load_adapter(settings=settings, step=step)
    games = await play_games(
        settings=settings,
        step=step,
        seeds=seeds_for(step=step, seeds_per_step=seeds_per_step),
        games_per_seed=games_per_seed,
        labels=[TRAINING_LABEL, f"reward={reward.value}"],
    )
    finished = await finished_games(settings=settings, games=games)
    built = batch(finished=finished, advantages=step_advantages(finished=finished, reward=reward))
    played = time.monotonic()
    metrics = await trainer(
        app_name=settings.app_name, run_name=settings.run_name
    ).train_step.remote.aio(step=step + 1, sequences=built.sequences)
    rounds = sum(len(game.outcome.rounds) for game in finished)
    player_rounds = sum(len(game.outcome.rounds) * len(game.outcome.players) for game in finished)
    return StepRecord(
        step=step,
        reward=reward.value,
        games=len(games),
        finished=len(finished),
        rounds=rounds,
        won=sum(rounds_won(game.outcome) for game in finished),
        first_item=sum(first_item_count(game.outcome) for game in finished),
        player_rounds=player_rounds,
        won_by_seed=counts_by_seed(finished=finished, count=rounds_won),
        moves_per_player_round=sum(game.outcome.moves for game in finished) / max(1, player_rounds),
        player_rounds_without_move=sum(
            game.outcome.player_rounds_without_move for game in finished
        ),
        answers=built.answers,
        answer_tokens=built.answer_tokens,
        sequence_tokens=built.sequence_tokens,
        chain_breaks=built.chain_breaks,
        play_seconds=played - began,
        train_seconds=time.monotonic() - played,
        trainer=metrics,
        run_ids=sorted(game.run_id for game in games),
    )


def append_record(*, path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as log:
        log.write(json.dumps(record) + "\n")


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


async def train(
    *,
    settings: LoopSettings,
    first_step: int,
    last_step: int,
    reward: Reward,
    seeds_per_step: int,
    games_per_seed: int,
) -> None:
    """Run training steps ``first_step`` to ``last_step``.

    Stop after a step whose KL is above MAX_KL, or in which fewer than MIN_FINISHED_SHARE of the
    games that started finished.
    """
    load_configured_scenario_catalog_unless_loaded()
    for step in range(first_step, last_step + 1):
        record = await run_step(
            settings=settings,
            step=step,
            reward=reward,
            seeds_per_step=seeds_per_step,
            games_per_seed=games_per_seed,
        )
        append_record(
            path=run_folder(settings=settings) / "steps.jsonl",
            record={**record._asdict(), "trainer": record.trainer._asdict()},
        )
        print_step(record=record)
        if record.trainer.kl > MAX_KL:
            print(f"stopping: KL {record.trainer.kl:.4f} is above {MAX_KL}", flush=True)
            return
        if record.finished < MIN_FINISHED_SHARE * record.games:
            print(f"stopping: {record.finished} of {record.games} games finished", flush=True)
            return


async def evaluate(
    *, settings: LoopSettings, step: int, games_per_seed: int, seeds: list[int]
) -> None:
    """Play adapter ``step`` on the given seeds without training, and record what it scored."""
    load_configured_scenario_catalog_unless_loaded()
    await load_adapter(settings=settings, step=step)
    games = await play_games(
        settings=settings,
        step=step,
        seeds=seeds,
        games_per_seed=games_per_seed,
        labels=[EVAL_LABEL],
    )
    finished = await finished_games(settings=settings, games=games)
    rounds = sum(len(game.outcome.rounds) for game in finished)
    record = EvalRecord(
        step=step,
        won_by_seed=counts_by_seed(finished=finished, count=rounds_won),
        first_item_by_seed=counts_by_seed(finished=finished, count=first_item_count),
        won=sum(rounds_won(game.outcome) for game in finished),
        rounds=rounds,
        first_item=sum(first_item_count(game.outcome) for game in finished),
        player_rounds=sum(
            len(game.outcome.rounds) * len(game.outcome.players) for game in finished
        ),
    )
    append_record(path=run_folder(settings=settings) / "eval.jsonl", record=record._asdict())
    print(
        f"eval step {step}: {len(finished)}/{len(games)} games finished, "
        f"won {record.won}/{record.rounds} rounds, "
        f"first item {record.first_item}/{record.player_rounds} player-rounds",
        flush=True,
    )


def initialize(*, app_name: str, run_name: str) -> None:
    """Create the training run on the trainer: adapter step 0 and the run's settings."""
    adapter = trainer(app_name=app_name, run_name=run_name).initialize.remote()
    print(f"step 0 adapter: {adapter}", flush=True)


def parser() -> argparse.ArgumentParser:
    """The command line: init, train and eval."""
    root = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("init", "train", "eval"):
        command = commands.add_parser(name)
        command.add_argument("--app", required=True, help="GRPO_APP_NAME of the deployed app")
        command.add_argument("--run", required=True, help="name of the training run")
    for name in ("train", "eval"):
        command = commands.choices[name]
        command.add_argument("--runs-dir", required=True, type=Path, help="GlossoGen runs dir")
        command.add_argument("--records-dir", required=True, type=Path, help="the loop's records")
        command.add_argument("--game-config", required=True, type=Path, help="signal_game config")
        command.add_argument("--concurrency", required=True, type=int, help="games at a time")
    train_command = commands.choices["train"]
    train_command.add_argument("--first-step", required=True, type=int)
    train_command.add_argument("--last-step", required=True, type=int)
    train_command.add_argument(
        "--reward", required=True, choices=[reward.value for reward in Reward]
    )
    train_command.add_argument("--seeds-per-step", required=True, type=int)
    train_command.add_argument("--games-per-seed", required=True, type=int)
    eval_command = commands.choices["eval"]
    eval_command.add_argument("--step", required=True, type=int)
    eval_command.add_argument("--games-per-seed", required=True, type=int)
    eval_command.add_argument("--seeds", required=True, type=int, nargs="+")
    return root


def main() -> None:
    """Run the command that the command line names."""
    arguments = parser().parse_args()
    if arguments.command == "init":
        initialize(app_name=arguments.app, run_name=arguments.run)
        return
    settings = LoopSettings(
        app_name=arguments.app,
        run_name=arguments.run,
        runs_dir=arguments.runs_dir.resolve(),
        records_dir=arguments.records_dir.resolve(),
        game_config=arguments.game_config.resolve(),
        concurrency=arguments.concurrency,
    )
    if arguments.command == "train":
        asyncio.run(
            train(
                settings=settings,
                first_step=arguments.first_step,
                last_step=arguments.last_step,
                reward=Reward(arguments.reward),
                seeds_per_step=arguments.seeds_per_step,
                games_per_seed=arguments.games_per_seed,
            )
        )
    else:
        asyncio.run(
            evaluate(
                settings=settings,
                step=arguments.step,
                games_per_seed=arguments.games_per_seed,
                seeds=arguments.seeds,
            )
        )


if __name__ == "__main__":
    main()
