"""Whole training steps on CPU: load an adapter, play games, build the batch, train and record.

The games are real signal_game runs in this process, with scripted players (loop_fakes.py). The
policy server, the trainer and the volume are fakes. Run from the repository root:

    VIRTUAL_ENV= uv run --no-sync pytest modal/grpo/test_grpo_steps.py
"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from adapter_loader import AdapterRequest, LoadedAdapters
from game_ledger import ABANDONED_LABEL
from grpo_loop import EvalPlan, StepPlan, evaluate, train
from grpo_records import BASE_MODEL
from loop_fakes import SAMPLED_LOGPROB, FakeBackend, FakeVllm, ScriptedGameLauncher
from loop_records import EvalRecord
from loop_services import GameSpec, Loop, LoopSettings
from partner import Partner
from signal_game_rewards import Reward
from token_sequences import recorded_responses

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_labels_file import read_run_labels
from glossogen.scenario_contract.base_knobs import AgentModelOverride
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)

HERE = Path(__file__).resolve().parent
RUN = "cpu-run"
SEEDS_PER_STEP = 2
GAMES_PER_SEED = 2


class LoopUnderTest(NamedTuple):
    """A loop on fakes, and the fakes, for a test to inspect."""

    loop: Loop
    backend: FakeBackend
    launcher: ScriptedGameLauncher


def never_interrupt(spec: GameSpec) -> bool:
    """Let every game play."""
    _ = spec
    return False


def two_round_config(*, tmp_path: Path) -> Path:
    """The shipped game config with 2 rounds."""
    config = json.loads((HERE / "signal_game_shapes.json").read_text())
    config["round_count"] = 2
    path = tmp_path / "game_config.json"
    path.write_text(json.dumps(config))
    return path


def loop_on_fakes(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partner: Partner | None,
    kl_at: dict[int, float],
    fail_after_saving: set[int],
    interrupt: Callable[[GameSpec], bool],
) -> LoopUnderTest:
    """A loop whose services are fakes, with its folders under ``tmp_path``."""
    load_configured_scenario_catalog_unless_loaded()
    settings = LoopSettings(
        app_name="app",
        run_name=RUN,
        runs_dir=tmp_path / "runs",
        records_dir=tmp_path / "records",
        game_config=two_round_config(tmp_path=tmp_path),
        concurrency=1,
    )
    backend = FakeBackend(
        run_name=RUN,
        adapters_dir=tmp_path / "adapters",
        partner=partner,
        kl_at=kl_at,
        fail_after_saving=fail_after_saving,
    )
    launcher = ScriptedGameLauncher(
        settings=settings, backend=backend, monkeypatch=monkeypatch, interrupt=interrupt
    )
    return LoopUnderTest(
        loop=Loop(settings=settings, backend=backend, launcher=launcher),
        backend=backend,
        launcher=launcher,
    )


def resumed(*, tested: LoopUnderTest, monkeypatch: pytest.MonkeyPatch) -> LoopUnderTest:
    """The same run in a new loop process: the same folders, app and policy server."""
    launcher = ScriptedGameLauncher(
        settings=tested.loop.settings,
        backend=tested.backend,
        monkeypatch=monkeypatch,
        interrupt=never_interrupt,
    )
    return tested._replace(loop=tested.loop._replace(launcher=launcher), launcher=launcher)


def trained_run_ids(*, tested: LoopUnderTest) -> list[str]:
    """The run ids of every game that the trainer trained on, in call order."""
    return [run_id for call in tested.backend.calls for run_id in call.run_ids]


def plan(*, partner: Partner | None, overlap: bool) -> StepPlan:
    """2 games on each of 2 seeds per step, scored on the first item, with no tests."""
    return StepPlan(
        reward=Reward.FIRST_ITEM,
        seeds_per_step=SEEDS_PER_STEP,
        games_per_seed=GAMES_PER_SEED,
        partner=partner,
        overlap=overlap,
        evaluation=None,
    )


def eval_lines(*, tested: LoopUnderTest) -> list[dict[str, Any]]:
    """The lines of the run's ``eval.jsonl``."""
    path = tested.loop.settings.records_dir / RUN / "eval.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def step_lines(*, tested: LoopUnderTest) -> list[dict[str, Any]]:
    """The lines of the run's ``steps.jsonl``."""
    path = tested.loop.settings.records_dir / RUN / "steps.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def adapters_by_step(*, tested: LoopUnderTest) -> dict[int, set[int]]:
    """The adapters that played each step's games, read from the games' labels."""
    played: dict[int, set[int]] = {}
    for game in tested.launcher.played:
        labels = read_run_labels(run_dir=tested.loop.settings.runs_dir / game.run_id)
        step = int(next(label for label in labels if label.startswith("step="))[5:])
        played.setdefault(step, set()).add(game.adapter)
    return played


def test_the_loader_keeps_the_listed_adapters_and_unloads_the_rest() -> None:
    vllm = FakeVllm()
    loader = LoadedAdapters(post=vllm.post)
    for request in (
        AdapterRequest(id="1", name="r-step0", path="/a/0", keep=()),
        AdapterRequest(id="2", name="r-step1", path="/a/1", keep=("r-step0",)),
    ):
        assert loader.handle(request=request).loaded
    assert vllm.loaded == {"r-step0", "r-step1"}
    result = loader.handle(request=AdapterRequest(id="3", name="r-step2", path="/a/2", keep=()))
    assert result.unloaded == ("r-step0", "r-step1")
    assert vllm.loaded == {"r-step2"}
    again = loader.handle(request=AdapterRequest(id="4", name="r-step2", path="/a/2", keep=()))
    assert (again.loaded, again.status, again.unloaded) == (True, 400, ())


async def test_steps_in_turn_play_their_own_adapter_and_train_on_their_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving=set(),
        interrupt=never_interrupt,
    )

    await train(loop=tested.loop, plan=plan(partner=None, overlap=False), last_step=1)

    assert adapters_by_step(tested=tested) == {0: {0}, 1: {1}}
    assert [call.step for call in tested.backend.calls] == [1, 2]
    lines = step_lines(tested=tested)
    assert [(line["step"], line["adapter"], line["finished"]) for line in lines] == [
        (0, 0, 4),
        (1, 1, 4),
    ]
    for line, call in zip(lines, tested.backend.calls, strict=True):
        assert call.run_ids == line["run_ids"]
        assert line["answers"] > 0
    for sequence in tested.backend.calls[0].sequences:
        for marked, logprob in zip(sequence.kl_mask, sequence.sampler_logprobs, strict=True):
            assert logprob == SAMPLED_LOGPROB * marked


async def test_overlapped_steps_play_the_adapter_before_and_keep_it_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher fails a game whose adapter the policy server does not hold."""
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving=set(),
        interrupt=never_interrupt,
    )

    await train(loop=tested.loop, plan=plan(partner=None, overlap=True), last_step=2)

    assert adapters_by_step(tested=tested) == {0: {0}, 1: {0}, 2: {1}}
    assert [call.step for call in tested.backend.calls] == [1, 2, 3]
    assert [(line["step"], line["adapter"]) for line in step_lines(tested=tested)] == [
        (0, 0),
        (1, 0),
        (2, 1),
    ]
    assert all(line["finished"] == 4 for line in step_lines(tested=tested))
    assert (1, (0, 1)) in tested.backend.loads
    assert (2, (1, 2)) in tested.backend.loads


async def test_a_kl_above_the_limit_stops_the_run_and_the_next_steps_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={2: 0.5},
        fail_after_saving=set(),
        interrupt=never_interrupt,
    )

    await train(loop=tested.loop, plan=plan(partner=None, overlap=True), last_step=3)

    assert [call.step for call in tested.backend.calls] == [1, 2]
    assert [line["step"] for line in step_lines(tested=tested)] == [0, 1]


async def test_a_frozen_partner_trains_only_the_other_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    partner = Partner(
        seat="player_b",
        model_override=AgentModelOverride(
            model=BASE_MODEL, provider=Provider.SELF_HOSTED, model_settings=None
        ),
        base_url=None,
    )
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=partner,
        kl_at={},
        fail_after_saving=set(),
        interrupt=never_interrupt,
    )

    await train(loop=tested.loop, plan=plan(partner=partner, overlap=False), last_step=0)

    [line] = step_lines(tested=tested)
    assert line["trained_seats"] == ["player_a"]
    assert line["partner"]["seat"] == "player_b"
    answers = {"player_a": 0, "player_b": 0}
    for run_id in line["run_ids"]:
        run_dir = tested.loop.settings.runs_dir / run_id
        events = await load_events(
            log_path=event_log_path(run_dir=run_dir, scenario_name="signal_game")
        )
        for seat in answers:
            answers[seat] += len(recorded_responses(events=events, agent_id=seat))
        assert f"partner={BASE_MODEL}" in read_run_labels(run_dir=run_dir)
    assert answers["player_b"] > 0
    assert line["answers"] == answers["player_a"]


async def test_a_run_stopped_while_a_game_played_resumes_and_trains_each_game_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop is cancelled, as Ctrl-C cancels it, while the third game of step 1 plays."""
    running: list[asyncio.Task[None]] = []
    cut_off: list[GameSpec] = []

    def stop_at_step_1_game_3(spec: GameSpec) -> bool:
        started = [game for game in tested.launcher.played if game.adapter == 1]
        if spec.game_set != "grpo_step1" or len(started) != 2 or cut_off:
            return False
        cut_off.append(spec)
        running[0].cancel()
        return True

    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving=set(),
        interrupt=stop_at_step_1_game_3,
    )
    running.append(
        asyncio.create_task(
            train(loop=tested.loop, plan=plan(partner=None, overlap=False), last_step=2)
        )
    )
    with pytest.raises(asyncio.CancelledError):
        await running[0]
    assert [line["step"] for line in step_lines(tested=tested)] == [0]

    again = resumed(tested=tested, monkeypatch=monkeypatch)
    await train(loop=again.loop, plan=plan(partner=None, overlap=False), last_step=2)

    lines = step_lines(tested=again)
    assert [(line["step"], line["finished"]) for line in lines] == [(0, 4), (1, 4), (2, 4)]
    assert len(again.launcher.played) == 6
    trained = trained_run_ids(tested=again)
    assert len(trained) == len(set(trained)) == 12
    assert [call.run_ids for call in again.backend.calls] == [line["run_ids"] for line in lines]
    [spec] = cut_off
    abandoned_log = spec.log_path.parent / "abandoned" / f"{spec.log_path.stem}.0.log"
    abandoned_run = abandoned_log.read_text().split("=")[1].strip()
    assert abandoned_run not in trained
    run_dir = again.loop.settings.runs_dir / abandoned_run
    assert ABANDONED_LABEL in read_run_labels(run_dir=run_dir)


async def test_an_overlapped_run_stopped_after_the_trainer_saved_trains_each_game_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trainer saves adapter 2 and the loop stops before it records step 1, while step 2's
    games play."""
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving={2},
        interrupt=never_interrupt,
    )
    with pytest.raises(ExceptionGroup):
        await train(loop=tested.loop, plan=plan(partner=None, overlap=True), last_step=3)
    assert [line["step"] for line in step_lines(tested=tested)] == [0]

    again = resumed(tested=tested, monkeypatch=monkeypatch)
    await train(loop=again.loop, plan=plan(partner=None, overlap=True), last_step=3)

    lines = step_lines(tested=again)
    assert [(line["step"], line["adapter"]) for line in lines] == [(0, 0), (1, 0), (2, 1), (3, 2)]
    assert [call.step for call in again.backend.calls] == [1, 2, 3, 4]
    trained = trained_run_ids(tested=again)
    assert len(trained) == len(set(trained)) == 16
    assert sorted(trained) == sorted(run_id for line in lines for run_id in line["run_ids"])


async def test_a_resumed_step_refuses_games_that_another_adapter_played(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 1's games played adapter 0 under --overlap; without it, step 1 plays adapter 1."""
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving={2},
        interrupt=never_interrupt,
    )
    with pytest.raises(ExceptionGroup):
        await train(loop=tested.loop, plan=plan(partner=None, overlap=True), last_step=3)

    again = resumed(tested=tested, monkeypatch=monkeypatch)
    with pytest.raises(ValueError, match="was played by adapter 0"):
        await train(loop=again.loop, plan=plan(partner=None, overlap=False), last_step=3)


TESTS = EvalPlan(every=2, seeds=[45, 46], games_per_seed=1)


@pytest.mark.parametrize("overlap", [False, True])
async def test_train_tests_every_second_adapter_as_the_eval_command_does(
    overlap: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving=set(),
        interrupt=never_interrupt,
    )
    with_tests = plan(partner=None, overlap=overlap)._replace(evaluation=TESTS)

    await train(loop=tested.loop, plan=with_tests, last_step=3)

    lines = eval_lines(tested=tested)
    assert [(line["step"], line["seeds"], line["games_per_seed"]) for line in lines] == [
        (2, [45, 46], 1),
        (4, [45, 46], 1),
    ]
    assert all(set(line) == set(EvalRecord._fields) for line in lines)
    assert [sum(map(len, line["won_by_seed"].values())) for line in lines] == [2, 2]
    tested_adapters = sorted(game.adapter for game in tested.launcher.played if game.seed < 1000)
    assert tested_adapters == [2, 2, 4, 4]
    played = len(tested.launcher.played)

    await evaluate(loop=tested.loop, step=4, games_per_seed=1, seeds=[45, 46], partner=None)

    assert len(tested.launcher.played) == played
    assert len(eval_lines(tested=tested)) == 2


async def test_a_test_that_a_stop_cut_off_runs_when_training_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop is cancelled while the second game of adapter 2's test plays."""
    running: list[asyncio.Task[None]] = []

    def stop_in_the_test(spec: GameSpec) -> bool:
        if spec.game_set != "grpo_eval_step2" or spec.seed != 46 or running[0].cancelling():
            return False
        running[0].cancel()
        return True

    tested = loop_on_fakes(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        partner=None,
        kl_at={},
        fail_after_saving=set(),
        interrupt=stop_in_the_test,
    )
    with_tests = plan(partner=None, overlap=False)._replace(evaluation=TESTS)
    running.append(asyncio.create_task(train(loop=tested.loop, plan=with_tests, last_step=3)))
    with pytest.raises(asyncio.CancelledError):
        await running[0]
    assert [line["step"] for line in step_lines(tested=tested)] == [0, 1]

    again = resumed(tested=tested, monkeypatch=monkeypatch)
    await train(loop=again.loop, plan=with_tests, last_step=3)

    assert [line["step"] for line in eval_lines(tested=again)] == [2, 4]
    assert [line["step"] for line in step_lines(tested=again)] == [0, 1, 2, 3]
    retested = [
        game.seed for game in again.launcher.played if game.adapter == 2 and game.seed < 1000
    ]
    assert retested == [46]
