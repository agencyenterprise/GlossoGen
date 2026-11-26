"""GRPO on signal_game: the loop that plays, scores and trains, run on your machine.

Each training step k:

1. plays ``--games-per-seed`` signal_game games on each of ``--seeds-per-step`` new seeds, with
   ``record_token_ids`` on (game_sets.py). The policy plays every seat, or every seat but the
   one that the run's frozen partner plays (partner.py). Adapter k plays, served by the policy
   server in grpo_app.py under the model name ``<run>-step<k>``;
2. scores each player in each round with the reward from signal_game_rewards.py, and gives it
   an advantage against its seat's mean in that round over the seed's finished games
   (step_batch.py);
3. builds training sequences from the token ids that the policy's seats logged in each finished
   game (token_sequences.py), and sends them to the trainer, which saves adapter k+1;
4. appends the step's record to ``<records dir>/<run>/steps.jsonl`` (loop_records.py).

With ``--overlap``, step k's games play with adapter k-1 while the trainer trains step k-1, so
each batch after step 0's was sampled by the adapter before the one that trains on it. Step 0
and step 1 both play adapter 0. The policy server keeps the adapter that the playing games use
loaded while it loads the next one (adapter_loader.py).

Training stops after a step whose KL per marked token is above MAX_KL, or in which fewer than
MIN_FINISHED_SHARE of the games that started finished. With ``--overlap``, the next step's games
are playing at that point, and the loop stops them.

``init --partner`` gives a run its frozen partner, which the trainer saves in the run's settings
on the volume. ``train`` reads it from there, and ``eval --partner`` tests an adapter against any
partner.

``train`` starts with the step after the last one that ``steps.jsonl`` records. With
``--eval-every N``, it tests each adapter whose step is a multiple of N once the trainer has saved
it, on held-out seeds, and appends the test to ``eval.jsonl`` as ``eval`` does. A test that
``eval.jsonl`` already holds plays nothing.

Run it from the repository root. docs/rl-training.md gives the commands.
"""

import argparse
import asyncio
import time
from pathlib import Path
from typing import NamedTuple

from game_sets import GameSet, PlayedGames, play_game_set
from loop_records import (
    StepOutcome,
    StepRecord,
    append_record,
    eval_record,
    eval_recorded,
    next_step,
    print_eval,
    print_step,
    step_record,
)
from loop_services import (
    GlossogenRunLauncher,
    Loop,
    LoopSettings,
    ModalBackend,
    run_folder,
)
from partner import Partner, load_partner
from signal_game_rewards import Reward
from step_batch import batch, finished_games, step_advantages

import modal
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)

TRAINING_LABEL = "grpo"
EVAL_LABEL = "grpo_eval"
FIRST_TRAINING_SEED = 1000
MAX_KL = 0.3
MIN_FINISHED_SHARE = 0.75


class EvalPlan(NamedTuple):
    """The held-out test that ``train`` runs on each adapter whose step is a multiple of
    ``every``."""

    every: int
    seeds: list[int]
    games_per_seed: int


class StepPlan(NamedTuple):
    """What each training step of a ``train`` call plays, how it scores, whether its games play
    while the trainer trains the step before, and the tests that ``train`` runs."""

    reward: Reward
    seeds_per_step: int
    games_per_seed: int
    partner: Partner | None
    overlap: bool
    evaluation: EvalPlan | None


class Overlapped(NamedTuple):
    """How an overlapped step ended: whether training stops, and the next step's games, None
    after the last step."""

    stopping: bool
    next_played: PlayedGames | None


def seeds_for(*, step: int, seeds_per_step: int) -> list[int]:
    """The training seeds of ``step``: new ones in every step."""
    first = FIRST_TRAINING_SEED + step * seeds_per_step
    return list(range(first, first + seeds_per_step))


def adapter_for(*, step: int, overlap: bool) -> int:
    """The adapter that plays step ``step``'s games: adapter ``step``, or with ``overlap`` the
    adapter before it."""
    if overlap and step > 0:
        return step - 1
    return step


def step_games(*, step: int, plan: StepPlan) -> GameSet:
    """The games of training step ``step``."""
    return GameSet(
        label=TRAINING_LABEL,
        step=step,
        adapter=adapter_for(step=step, overlap=plan.overlap),
        seeds=seeds_for(step=step, seeds_per_step=plan.seeds_per_step),
        games_per_seed=plan.games_per_seed,
        labels=[TRAINING_LABEL, f"reward={plan.reward.value}"],
        partner=plan.partner,
    )


async def play_step(*, loop: Loop, step: int, plan: StepPlan) -> PlayedGames:
    """Play the games of training step ``step``."""
    return await play_game_set(loop=loop, game_set=step_games(step=step, plan=plan))


async def train_on(*, loop: Loop, step: int, plan: StepPlan, played: PlayedGames) -> StepRecord:
    """Score step ``step``'s games, train on them, and record the step; adapter ``step + 1`` is
    saved."""
    finished = await finished_games(settings=loop.settings, games=played.games)
    built = batch(
        finished=finished,
        advantages=step_advantages(finished=finished, reward=plan.reward),
        partner=plan.partner,
    )
    began = time.monotonic()
    metrics = await loop.backend.train_step(
        step=step + 1,
        sequences=built.sequences,
        run_ids=sorted(game.game.run_id for game in finished),
    )
    record = step_record(
        step=step,
        adapter=adapter_for(step=step, overlap=plan.overlap),
        reward=plan.reward.value,
        partner=plan.partner,
        outcome=StepOutcome(
            played=played,
            finished=finished,
            built=built,
            metrics=metrics,
            train_seconds=time.monotonic() - began,
        ),
    )
    append_record(path=run_folder(settings=loop.settings) / "steps.jsonl", record=record)
    print_step(record=record)
    return record


def stop_reason(*, record: StepRecord) -> str | None:
    """Why training stops after this step, or None when it goes on."""
    if record.trainer.kl > MAX_KL:
        return f"KL {record.trainer.kl:.4f} is above {MAX_KL}"
    if record.finished < MIN_FINISHED_SHARE * record.games:
        return f"{record.finished} of {record.games} games finished"
    return None


def stops_training(*, record: StepRecord) -> bool:
    """Whether training stops after this step; prints the reason when it does."""
    reason = stop_reason(record=record)
    if reason is None:
        return False
    print(f"stopping: {reason}", flush=True)
    return True


async def evaluate_if_due(*, loop: Loop, plan: StepPlan, adapter: int) -> None:
    """Test ``adapter`` when ``train`` tests it: a step after 0 that is a multiple of
    ``--eval-every``."""
    evaluation = plan.evaluation
    if evaluation is None or adapter == 0 or adapter % evaluation.every != 0:
        return
    await evaluate(
        loop=loop,
        step=adapter,
        games_per_seed=evaluation.games_per_seed,
        seeds=evaluation.seeds,
        partner=plan.partner,
    )


async def train_in_turn(*, loop: Loop, plan: StepPlan, first_step: int, last_step: int) -> None:
    """Train steps ``first_step`` to ``last_step``, each playing its games, then training."""
    for step in range(first_step, last_step + 1):
        await loop.backend.load_adapter(step=step, keep=[step])
        played = await play_step(loop=loop, step=step, plan=plan)
        record = await train_on(loop=loop, step=step, plan=plan, played=played)
        if stops_training(record=record):
            return
        await evaluate_if_due(loop=loop, plan=plan, adapter=step + 1)


async def overlapped_step(
    *, loop: Loop, plan: StepPlan, step: int, played: PlayedGames, last_step: int
) -> Overlapped:
    """Train step ``step`` while step ``step + 1``'s games play with adapter ``step``.

    Once the trainer has saved adapter ``step + 1``, the policy server loads it and keeps
    adapter ``step`` for the games that are playing. When training stops, the playing games are
    stopped.
    """
    await loop.backend.load_adapter(step=step, keep=[step])
    playing: asyncio.Task[PlayedGames] | None = None
    async with asyncio.TaskGroup() as group:
        if step < last_step:
            playing = group.create_task(play_step(loop=loop, step=step + 1, plan=plan))
        record = await train_on(loop=loop, step=step, plan=plan, played=played)
        stopping = stops_training(record=record)
        if playing is not None and stopping:
            playing.cancel()
        if playing is not None and not stopping:
            await loop.backend.load_adapter(step=step + 1, keep=[step, step + 1])
    if playing is None or stopping:
        return Overlapped(stopping=stopping, next_played=None)
    return Overlapped(stopping=False, next_played=playing.result())


async def train_overlapped(*, loop: Loop, plan: StepPlan, first_step: int, last_step: int) -> None:
    """Train steps ``first_step`` to ``last_step``, each step's games playing while the trainer
    trains the step before."""
    adapter = adapter_for(step=first_step, overlap=True)
    await loop.backend.load_adapter(step=adapter, keep=[adapter])
    played = await play_step(loop=loop, step=first_step, plan=plan)
    for step in range(first_step, last_step + 1):
        overlapped = await overlapped_step(
            loop=loop, plan=plan, step=step, played=played, last_step=last_step
        )
        if overlapped.stopping:
            return
        await evaluate_if_due(loop=loop, plan=plan, adapter=step + 1)
        if overlapped.next_played is None:
            return
        played = overlapped.next_played


async def train(*, loop: Loop, plan: StepPlan, last_step: int) -> None:
    """Run the training steps after the last one that ``steps.jsonl`` records, to ``last_step``.

    A step that stopped partway reuses the games that ended before the stop (game_sets.py). A
    test that a stop cut off runs before the first step.
    """
    first_step = next_step(steps_path=run_folder(settings=loop.settings) / "steps.jsonl")
    if first_step > last_step:
        print(f"steps.jsonl already records steps 0 to {first_step - 1}", flush=True)
        return
    await evaluate_if_due(loop=loop, plan=plan, adapter=first_step)
    print(f"training steps {first_step} to {last_step}", flush=True)
    if plan.overlap:
        await train_overlapped(loop=loop, plan=plan, first_step=first_step, last_step=last_step)
    else:
        await train_in_turn(loop=loop, plan=plan, first_step=first_step, last_step=last_step)


async def evaluate(
    *,
    loop: Loop,
    step: int,
    games_per_seed: int,
    seeds: list[int],
    partner: Partner | None,
) -> None:
    """Play adapter ``step`` on the given seeds without training, and record what it scored.

    A test that ``eval.jsonl`` already holds, with the same partner, seeds and games per seed,
    plays nothing.
    """
    eval_path = run_folder(settings=loop.settings) / "eval.jsonl"
    if eval_recorded(
        eval_path=eval_path,
        step=step,
        partner=partner,
        seeds=seeds,
        games_per_seed=games_per_seed,
    ):
        print(f"eval step {step}: eval.jsonl already holds this test", flush=True)
        return
    await loop.backend.load_adapter(step=step, keep=[step])
    game_set = GameSet(
        label=EVAL_LABEL,
        step=step,
        adapter=step,
        seeds=seeds,
        games_per_seed=games_per_seed,
        labels=[EVAL_LABEL],
        partner=partner,
    )
    played = await play_game_set(loop=loop, game_set=game_set)
    finished = await finished_games(settings=loop.settings, games=played.games)
    record = eval_record(
        step=step,
        partner=partner,
        seeds=seeds,
        games_per_seed=games_per_seed,
        finished=finished,
    )
    append_record(path=eval_path, record=record)
    print_eval(record=record, finished=len(finished), games=len(played.games))


def partner_json(*, partner: Partner | None) -> str:
    """The partner as JSON, ``null`` without one."""
    if partner is None:
        return "null"
    return partner.model_dump_json()


def initialize(*, app_name: str, run_name: str, partner: Partner | None) -> None:
    """Create the training run on the trainer: adapter step 0, and the run's settings with
    ``partner``."""
    trainer = modal.Cls.from_name(app_name, "Trainer")(run_name=run_name)
    adapter = trainer.initialize.remote(partner=partner_json(partner=partner))
    print(f"step 0 adapter: {adapter}", flush=True)


def optional_partner(*, path: Path | None) -> Partner | None:
    """The partner in the file at ``path``, or None when the command line names no file."""
    if path is None:
        return None
    return load_partner(path=path)


def parser() -> argparse.ArgumentParser:
    """The command line: init, train and eval."""
    root = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("init", "train", "eval"):
        command = commands.add_parser(name)
        command.add_argument("--app", required=True, help="GRPO_APP_NAME of the deployed app")
        command.add_argument("--run", required=True, help="name of the training run")
    for name in ("init", "eval"):
        commands.choices[name].add_argument(
            "--partner", type=Path, help="a partner file: the frozen model of one seat"
        )
    for name in ("train", "eval"):
        command = commands.choices[name]
        command.add_argument("--runs-dir", required=True, type=Path, help="GlossoGen runs dir")
        command.add_argument("--records-dir", required=True, type=Path, help="the loop's records")
        command.add_argument("--game-config", required=True, type=Path, help="signal_game config")
        command.add_argument("--concurrency", required=True, type=int, help="games at a time")
    train_command = commands.choices["train"]
    train_command.add_argument("--last-step", required=True, type=int)
    train_command.add_argument(
        "--reward", required=True, choices=[reward.value for reward in Reward]
    )
    train_command.add_argument("--seeds-per-step", required=True, type=int)
    train_command.add_argument("--games-per-seed", required=True, type=int)
    train_command.add_argument(
        "--overlap",
        action="store_true",
        help="play each step's games while the trainer trains the step before",
    )
    train_command.add_argument(
        "--eval-every", type=int, help="test each adapter whose step is a multiple of this"
    )
    train_command.add_argument("--eval-seeds", type=int, nargs="+", help="the tests' seeds")
    train_command.add_argument("--eval-games-per-seed", type=int, help="the tests' games per seed")
    eval_command = commands.choices["eval"]
    eval_command.add_argument("--step", required=True, type=int)
    eval_command.add_argument("--games-per-seed", required=True, type=int)
    eval_command.add_argument("--seeds", required=True, type=int, nargs="+")
    return root


def modal_loop(*, settings: LoopSettings) -> Loop:
    """The loop of a training run on the deployed app."""
    return Loop(
        settings=settings,
        backend=ModalBackend(app_name=settings.app_name, run_name=settings.run_name),
        launcher=GlossogenRunLauncher(settings=settings),
    )


def eval_plan(*, arguments: argparse.Namespace) -> EvalPlan | None:
    """The tests that ``train`` runs: none, or the three ``--eval-*`` flags together."""
    flags = (arguments.eval_every, arguments.eval_seeds, arguments.eval_games_per_seed)
    if all(flag is None for flag in flags):
        return None
    if any(flag is None for flag in flags):
        raise SystemExit("--eval-every, --eval-seeds and --eval-games-per-seed go together")
    if arguments.eval_every < 1:
        raise SystemExit("--eval-every must be at least 1")
    return EvalPlan(
        every=arguments.eval_every,
        seeds=arguments.eval_seeds,
        games_per_seed=arguments.eval_games_per_seed,
    )


async def run_train(*, loop: Loop, arguments: argparse.Namespace) -> None:
    """The ``train`` command, with the partner that ``init`` saved."""
    evaluation = eval_plan(arguments=arguments)
    plan = StepPlan(
        reward=Reward(arguments.reward),
        seeds_per_step=arguments.seeds_per_step,
        games_per_seed=arguments.games_per_seed,
        partner=await loop.backend.run_partner(),
        overlap=arguments.overlap,
        evaluation=evaluation,
    )
    await train(loop=loop, plan=plan, last_step=arguments.last_step)


def main() -> None:
    """Run the command that the command line names."""
    arguments = parser().parse_args()
    if arguments.command == "init":
        initialize(
            app_name=arguments.app,
            run_name=arguments.run,
            partner=optional_partner(path=arguments.partner),
        )
        return
    load_configured_scenario_catalog_unless_loaded()
    loop = modal_loop(
        settings=LoopSettings(
            app_name=arguments.app,
            run_name=arguments.run,
            runs_dir=arguments.runs_dir.resolve(),
            records_dir=arguments.records_dir.resolve(),
            game_config=arguments.game_config.resolve(),
            concurrency=arguments.concurrency,
        )
    )
    if arguments.command == "train":
        asyncio.run(run_train(loop=loop, arguments=arguments))
        return
    asyncio.run(
        evaluate(
            loop=loop,
            step=arguments.step,
            games_per_seed=arguments.games_per_seed,
            seeds=arguments.seeds,
            partner=optional_partner(path=arguments.partner),
        )
    )


if __name__ == "__main__":
    main()
