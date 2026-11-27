"""``platoon train`` end to end on CPU: the shipped configs, real GlossoGen games with scripted
players, and the Tinker-API service with CPU backends over HTTP.

Each run trains two steps of one seed's group of two games, with games that run ahead of training,
the per-round credit with its KL penalty to the frozen base model, and an evaluation on a held-out
seed at step 0 and at the end. The configs name Qwen3.8-27B with its own chat template. The runs use
copies of the configs that keep the model's name, give it the toy tokenizer, and render with
``qwen3_instruct``, which the toy tokenizer serves.
"""

import json
import logging
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import torch
import yaml
from episodes import PROJECT_ROOT, task_row
from glossogen_platoon.eval_report import run_report
from platoon import cli
from platoon.testing import toy_tokenizer
from platoon.testing.trainers import _restored_signals
from scripted_player import signal_game_player
from service_thread import API_KEY, RunningService, running_service
from tinker_cookbook.tokenizer_utils import register_tokenizer, unregister_tokenizer

MODEL = "Qwen/Qwen3.8-27B"
CONFIGS = PROJECT_ROOT / "configs"
TRAIN_SEEDS = (1000, 1001)
EVAL_SEED = 45
STEPS = 2
STATS_LOGGER = "platoon.utils.stats_logger"


@pytest.fixture(autouse=True)
def toy_tokenizer_for_the_model() -> Iterator[None]:
    """tinker-cookbook loads the model's tokenizer by name: the toy one, so nothing is
    downloaded."""
    register_tokenizer(MODEL, toy_tokenizer)
    yield
    unregister_tokenizer(MODEL)


def task_table(*, path: Path) -> Path:
    """A task table of two training seeds and one held-out seed."""
    rows = [{**task_row(seed=seed), "split": "train"} for seed in TRAIN_SEEDS]
    rows.append({**task_row(seed=EVAL_SEED), "split": "eval"})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def toy_renderer(*, section: Any) -> Any:
    """``section`` with every ``chat_template`` renderer replaced by ``qwen3_instruct``, without its
    options."""
    if isinstance(section, list):
        return [toy_renderer(section=item) for item in section]
    if not isinstance(section, dict):
        return section
    replaced = {key: toy_renderer(section=value) for key, value in section.items()}
    if replaced.get("renderer_name") == "chat_template":
        replaced["renderer_name"] = "qwen3_instruct"
        del replaced["renderer_kwargs"]
    return replaced


def toy_configs(*, tmp_path: Path) -> Path:
    """Copies of the shipped configs that render with ``qwen3_instruct``, beside the game config."""
    folder = tmp_path / "configs"
    folder.mkdir()
    for config in CONFIGS.glob("*.yaml"):
        loaded = yaml.safe_load(config.read_text())
        (folder / config.name).write_text(yaml.safe_dump(toy_renderer(section=loaded)))
    shutil.copy(CONFIGS / "signal_game_shapes.json", folder / "signal_game_shapes.json")
    task_table(path=folder / "signal_game_tasks.jsonl")
    return folder


def overrides(*, tmp_path: Path) -> list[str]:
    """The settings of a short CPU run, laid over a config."""
    return [
        f"log_path={tmp_path / 'platoon'}",
        f"environments.0.harness_options.runs_dir={tmp_path / 'games'}",
        "train.batch_size=1",
        f"train.max_training_steps={STEPS}",
        "train.max_concurrent_rollouts=2",
        "train.workflow_config.group_size=2",
        "eval.every=2",
        "eval.max_concurrent_rollouts=1",
        "eval.workflow_config.group_size=1",
        "watchdog.enabled=false",
    ]


def train(*, config: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunningService:
    """``platoon train`` with a copy of ``config`` against a CPU service; return the service."""
    configs = toy_configs(tmp_path=tmp_path)
    with running_service(
        base_model=MODEL, script=signal_game_player, root=tmp_path / "service"
    ) as served:
        monkeypatch.setenv("TINKER_API_KEY", API_KEY)
        monkeypatch.setenv("TINKER_BASE_URL", served.url)
        monkeypatch.setenv("TINKER_TELEMETRY", "0")
        with _restored_signals():
            cli.main(["train", str(configs / config), *overrides(tmp_path=tmp_path)])
        return served


def run_folder(*, tmp_path: Path, trial: str) -> Path:
    """Where platoon wrote the run."""
    return tmp_path / "platoon" / "signal-game" / trial


def checkpoint_rows(*, run: Path) -> list[dict[str, object]]:
    """The rows of the run's ``checkpoints.jsonl``."""
    return [json.loads(line) for line in (run / "checkpoints.jsonl").read_text().splitlines()]


def trained_adapters(*, served: RunningService) -> list[str]:
    """The adapters whose logits moved from zero."""
    return [name for name, logits in served.model.logits.items() if bool(torch.any(logits != 0))]


def logged_values(*, caplog: pytest.LogCaptureFixture, key: str) -> list[float]:
    """Every value that platoon's step log gave the metric ``key``, in order."""
    pattern = re.compile(rf"^\s*{re.escape(key)}: (\S+)$")
    values: list[float] = []
    for record in caplog.records:
        if record.name != STATS_LOGGER:
            continue
        match = pattern.match(record.getMessage())
        if match:
            values.append(float(match.group(1)))
    return values


def base_model_games(*, served: RunningService) -> int:
    """How many samples played a game turn on the base model, as against scoring a prompt with
    it."""
    return sum(1 for call in served.sampler.calls if call.adapter is None and not call.scoring)


def test_the_shared_policy_trains_ahead_of_its_games_with_round_credit_and_a_kl_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=STATS_LOGGER)
    served = train(config="signal_game.yaml", tmp_path=tmp_path, monkeypatch=monkeypatch)
    run = run_folder(tmp_path=tmp_path, trial="first-item")
    rows = checkpoint_rows(run=run)
    assert rows[-1]["name"] == "final" and rows[-1]["batch"] == STEPS
    resolved = yaml.safe_load((run / "config.resolved.yaml").read_text())["train"]
    assert (resolved["max_staleness"], resolved["permit_release"]) == (3, "rollout")
    assert (resolved["loss_fn"], resolved["loss_fn_config"]["clip_high_threshold"]) == (
        "cispo",
        5.0,
    )
    assert resolved["optimizer"]["grad_clip_norm"] == 1.0
    assert logged_values(caplog=caplog, key="batch/stale_groups") == [0.0] * STEPS
    assert len(logged_values(caplog=caplog, key="credit/glossogen/kl_k3")) == STEPS
    assert len(logged_values(caplog=caplog, key="optim/grad_norm")) == STEPS
    assert len(served.service.trainer.adapters) == 1
    assert len(trained_adapters(served=served)) == 1
    assert base_model_games(served=served) == 0
    assert any(call.scoring for call in served.sampler.calls)
    evaluations = (run / "evaluations.jsonl").read_text().splitlines()
    assert [json.loads(line)["step"] for line in evaluations] == [0, STEPS]
    report = run_report(run=run)
    assert [(counts.step, counts.games, counts.player_rounds) for counts in report] == [
        (0, 1, 20),
        (STEPS, 1, 20),
    ]
    for counts in report:
        assert set(counts.first_item_by_seat) == {"player_a", "player_b"}
        assert sum(counts.first_item_by_seat.values()) == counts.first_item


def test_a_frozen_partner_plays_the_base_model_and_trains_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    served = train(config="frozen_partner.yaml", tmp_path=tmp_path, monkeypatch=monkeypatch)
    rows = checkpoint_rows(run=run_folder(tmp_path=tmp_path, trial="first-item-frozen-partner"))
    assert rows[-1]["name"] == "final"
    assert len(served.service.trainer.adapters) == 1
    assert base_model_games(served=served) > 0


def test_each_seat_trains_its_own_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    served = train(config="seat_policies.yaml", tmp_path=tmp_path, monkeypatch=monkeypatch)
    rows = checkpoint_rows(run=run_folder(tmp_path=tmp_path, trial="first-item-seat-policies"))
    assert rows[-1]["name"] == "final"
    assert len(served.service.trainer.adapters) == 2
    assert len(trained_adapters(served=served)) == 2
    assert base_model_games(served=served) == 0
