"""Fakes of the loop's services, for tests that run whole training steps on CPU.

``FakeBackend`` stands in for the deployed app. Its policy server runs adapter_loader.py's
``LoadedAdapters`` against a fake vLLM that only tracks which adapters are loaded. Its trainer
saves each adapter's metrics and games in a folder, as grpo_app.py does on the volume, and
returns made-up metrics. ``ScriptedGameLauncher`` plays each game in this process: a real
signal_game run with GlossoGen's runtime, whose players follow random scripts instead of calling
a model. Each scripted answer carries token ids and logprobs, as a self-hosted model's answers do
under ``record_token_ids``. No model, no network and no Modal call is involved.
"""

import asyncio
import json
import random
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from adapter_loader import LoadedAdapters, VllmReply
from grpo_records import StepMetrics, TrainingSequence
from loop_services import (
    SCENARIO,
    Game,
    GameSpec,
    LoopSettings,
    adapter_request,
    model_name,
    write_labels,
)
from partner import Partner
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from trained_adapters import METRICS_FILE, record_trained_games, saved_step

from glossogen.llm.self_hosted_chat_model import (
    PROMPT_TOKEN_IDS_DETAIL,
    TOKEN_IDS_DETAIL,
    TOKEN_LOGPROBS_DETAIL,
)
from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.agent_config import AgentConfig
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.testing import simulation_harness
from glossogen.testing.scenario_runtime import assert_no_agent_crashed
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn, build_scripted_model
from glossogen.testing.simulation_harness import never_times_out, run_simulation

SAMPLED_LOGPROB = -0.5
"""The logprob that each scripted answer token is logged with."""
DIRECTIONS = ("up", "down", "left", "right")
URL = "http://policy.test/v1"


class FakeVllm:
    """The adapters that a fake vLLM server holds."""

    def __init__(self) -> None:
        self.loaded: set[str] = set()

    def post(self, *, path: str, body: dict[str, str]) -> VllmReply:
        """Load or unload one adapter, as vLLM's LoRA endpoints do."""
        name = body["lora_name"]
        if path.endswith("unload_lora_adapter"):
            self.loaded.discard(name)
            return VllmReply(status=200, body="unloaded")
        if name in self.loaded:
            return VllmReply(status=400, body=f"The lora adapter {name} has already been loaded")
        self.loaded.add(name)
        return VllmReply(status=200, body="loaded")


class TrainCall(NamedTuple):
    """One call of the fake trainer that trained, rather than returned saved metrics."""

    step: int
    run_ids: list[str]
    sequences: list[TrainingSequence]


class FakeBackend:
    """The deployed app: a policy server, a trainer and the run's partner, on CPU.

    ``kl_at`` gives the KL that the trainer reports for a step. ``fail_after_saving`` names a
    step whose call saves its adapter and then raises, as when the loop stops between the
    trainer's save and the step's record.
    """

    def __init__(
        self,
        *,
        run_name: str,
        adapters_dir: Path,
        partner: Partner | None,
        kl_at: dict[int, float],
        fail_after_saving: set[int],
    ) -> None:
        self.run_name = run_name
        self.vllm = FakeVllm()
        self.loader = LoadedAdapters(post=self.vllm.post)
        self.adapters_dir = adapters_dir
        self.partner = partner
        self.kl_at = kl_at
        self.fail_after_saving = fail_after_saving
        self.calls: list[TrainCall] = []
        self.loads: list[tuple[int, tuple[int, ...]]] = []
        self._save(step=0, run_ids=[], metrics=made_up_metrics(sequences=[], kl=0.0))

    async def serve_url(self) -> str:
        """The fake policy server's URL."""
        return URL

    async def load_adapter(self, *, step: int, keep: list[int]) -> None:
        """Handle the request as the policy server's loader thread does."""
        if not (self.adapters_dir / f"step_{step}").exists():
            raise RuntimeError(f"adapter {step} was never saved")
        result = self.loader.handle(
            request=adapter_request(run_name=self.run_name, step=step, keep=keep)
        )
        if not result.loaded:
            raise RuntimeError(f"loading adapter {step} failed: {result.body}")
        self.loads.append((step, tuple(keep)))

    async def train_step(
        self, *, step: int, sequences: list[TrainingSequence], run_ids: list[str]
    ) -> StepMetrics:
        """Return the saved metrics of a step trained on these games, or save made-up ones."""
        saved = saved_step(directory=self.adapters_dir / f"step_{step}", run_ids=run_ids)
        if saved is not None:
            return saved
        if not (self.adapters_dir / f"step_{step - 1}").exists():
            raise RuntimeError(f"adapter {step - 1} was never saved")
        metrics = made_up_metrics(sequences=sequences, kl=self.kl_at.get(step, 0.001))
        self._save(step=step, run_ids=run_ids, metrics=metrics)
        self.calls.append(TrainCall(step=step, run_ids=sorted(run_ids), sequences=sequences))
        if step in self.fail_after_saving:
            self.fail_after_saving.discard(step)
            raise RuntimeError(f"the loop stopped after the trainer saved adapter {step}")
        return metrics

    async def run_partner(self) -> Partner | None:
        """The run's partner."""
        return self.partner

    def _save(self, *, step: int, run_ids: list[str], metrics: StepMetrics) -> None:
        """Save an adapter's metrics and games, as grpo_app.py does."""
        directory = self.adapters_dir / f"step_{step}"
        directory.mkdir(parents=True)
        (directory / METRICS_FILE).write_text(json.dumps(metrics._asdict()) + "\n")
        record_trained_games(directory=directory, run_ids=run_ids)


def made_up_metrics(*, sequences: list[TrainingSequence], kl: float) -> StepMetrics:
    """Metrics with the batch's token counts and ``kl``."""
    marked = sum(sum(sequence.kl_mask[1:]) for sequence in sequences)
    return StepMetrics(
        policy_loss=0.0,
        kl=kl,
        marked_tokens=marked,
        advantaged_tokens=0,
        tokens=sum(len(sequence.input_ids) for sequence in sequences),
        grad_norm=0.0,
        clamped_tokens=0,
        ratio_mean=1.0,
        ratio_max=1.0,
        ratio_capped_share=0.0,
        seconds=0.0,
        peak_memory_gb=0.0,
    )


def part_token(*, kind: str, text: str) -> list[int]:
    """Two token ids for one message part: one for its kind, one for its text."""
    return [zlib.crc32(kind.encode()) % 1000, 1000 + zlib.crc32(text.encode()) % 50_000]


def response_ids(*, response: ModelResponse) -> list[int]:
    """The token ids of an answer, as each later prompt that holds it repeats them."""
    ids: list[int] = []
    for part in response.parts:
        if isinstance(part, ToolCallPart):
            ids += part_token(kind=part.tool_name, text=part.args_as_json_str())
        elif isinstance(part, TextPart):
            ids += part_token(kind="text", text=part.content)
    return ids


def prompt_ids(*, messages: list[ModelMessage]) -> list[int]:
    """The token ids of a prompt: each message's parts in order."""
    ids: list[int] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            ids += response_ids(response=message)
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                ids += part_token(kind=part.part_kind, text=str(getattr(part, "content", "")))
    return ids


def with_token_ids(*, model: FunctionModel) -> FunctionModel:
    """``model``, with token ids and logprobs on each answer, as vLLM returns them."""
    answer = model.function
    if answer is None:
        raise ValueError("the scripted model has no plain function")

    def answer_with_ids(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        response = answer(messages, info)
        if not isinstance(response, ModelResponse):
            raise TypeError("the scripted model answered asynchronously")
        token_ids = response_ids(response=response)
        response.provider_details = {
            PROMPT_TOKEN_IDS_DETAIL: prompt_ids(messages=messages),
            TOKEN_IDS_DETAIL: token_ids,
            TOKEN_LOGPROBS_DETAIL: [SAMPLED_LOGPROB] * len(token_ids),
        }
        return response

    return FunctionModel(answer_with_ids, stream_function=model.stream_function)


def scripted_models_with_token_ids(
    *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
) -> FunctionModel:
    """``build_scripted_model``, with token ids on each answer."""
    return with_token_ids(model=build_scripted_model(turns=turns, when_exhausted=when_exhausted))


def player_script(*, seed: int, game: int, player: str, rounds: int) -> list[ScriptedTurn]:
    """A player that reads, then in each round makes 0 to 2 random moves and ends the round."""
    choices = random.Random(f"{seed}-{game}-{player}")
    turns: list[ScriptedTurn] = [ToolTurn(tool_name="read_notifications", args={})]
    for _ in range(rounds):
        directions = [choices.choice(DIRECTIONS) for _ in range(choices.randint(0, 2))]
        if directions:
            turns.append(
                ToolTurn(tool_name="move", args={"directions": directions, "reasoning": "Try."})
            )
        turns.append(ToolTurn(tool_name="end_round", args={"reasoning": "Done."}))
        turns.append(ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"}))
    return turns


def self_hosted_scenario(
    *, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationScenario:
    """The scenario of a seed config, whose agents run under ``self-hosted``.

    The test harness builds each agent under ``anthropic``. Under ``self-hosted`` the runner
    sends each request whole and records the token ids that the answer carries.
    """
    config: dict[str, Any] = json.loads(config_path.read_text())
    scenario_cls = get_scenario_class(name=SCENARIO)
    prepared = scenario_cls.prepare_config(config=dict(config))
    scenario = scenario_cls.create_from_config(config=dict(prepared))
    agents = scenario.get_agents

    def self_hosted_agents(default_model: str, default_provider: str) -> list[AgentConfig]:
        _ = default_provider
        return agents(default_model=default_model, default_provider=Provider.SELF_HOSTED)

    monkeypatch.setattr(scenario, "get_agents", self_hosted_agents)
    return scenario


class ScriptedGameLauncher:
    """Plays each game in this process with scripted players, and checks that the policy server
    holds the game's adapter from its start to its end.

    ``interrupt`` sees each game once the game has its run id and labels. When it returns True,
    it has cancelled the task that runs the loop, as ``asyncio.run`` does on Ctrl-C, and the
    game waits for that cancellation without playing.
    """

    def __init__(
        self,
        *,
        settings: LoopSettings,
        backend: FakeBackend,
        monkeypatch: pytest.MonkeyPatch,
        interrupt: Callable[[GameSpec], bool],
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._monkeypatch = monkeypatch
        self._interrupt = interrupt
        self.played: list[Game] = []
        monkeypatch.setattr(
            simulation_harness, "build_scripted_model", scripted_models_with_token_ids
        )

    async def play(self, *, spec: GameSpec) -> Game:
        """Play one scripted game and file its event log where ``glossogen run`` would."""
        model = model_name(run_name=self._settings.run_name, step=spec.adapter)
        self._check_loaded(model=model)
        run_id = f"{SCENARIO}/{len(list(self._settings.runs_dir.glob(f'{SCENARIO}/*'))) + 1}"
        spec.log_path.write_text(f"new_run_id={run_id}\n")
        run_dir = self._settings.runs_dir / run_id
        run_dir.mkdir(parents=True)
        write_labels(run_dir=run_dir, labels=spec.labels)
        if self._interrupt(spec):
            await asyncio.Event().wait()
        scenario = self_hosted_scenario(config_path=spec.config, monkeypatch=self._monkeypatch)
        rounds = scenario.get_knobs().round_count
        scripts = {
            seat: player_script(seed=spec.seed, game=spec.game, player=seat, rounds=rounds)
            for seat in ("player_a", "player_b")
        }
        result = await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=run_dir,
            monkeypatch=self._monkeypatch,
            phase_timed_out=never_times_out,
        )
        assert_no_agent_crashed(result=result)
        result.log_path.rename(event_log_path(run_dir=run_dir, scenario_name=SCENARIO))
        self._check_loaded(model=model)
        game = Game(
            seed=spec.seed, game=spec.game, adapter=spec.adapter, run_id=run_id, returncode=0
        )
        self.played.append(game)
        return game

    def _check_loaded(self, *, model: str) -> None:
        """Fail the game when the policy server does not hold its adapter."""
        if model not in self._backend.vllm.loaded:
            raise AssertionError(
                f"{model} is not loaded; loaded: {sorted(self._backend.vllm.loaded)}"
            )
