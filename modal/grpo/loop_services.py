"""The services that the loop calls, and where a training run keeps its local files.

``Backend`` is the loop's view of the deployed app: the policy server's URL and its adapters,
the trainer, and the run's settings on the volume. ``GameLauncher`` plays one game. The loop
reaches them through a ``Loop``. ``ModalBackend`` and ``GlossogenRunLauncher`` reach the deployed
app and run ``glossogen run``; the loop's tests replace both with fakes.
"""

import asyncio
import contextlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from adapter_loader import ADAPTER_REQUEST_KEY, ADAPTER_RESULT_KEY, AdapterRequest, AdapterResult
from grpo_records import StepMetrics, TrainingSequence
from partner import Partner

import modal
from glossogen.run_storage.run_labels_file import RUN_LABELS_FILENAME

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SCENARIO = "signal_game"
MAX_AGENT_TURNS = 400
RUN_ID_WAIT_SECONDS = 300
ADAPTER_LOAD_WAIT_SECONDS = 1800
NEW_RUN_ID = re.compile(r"new_run_id=(\S+)")


class LoopSettings(NamedTuple):
    """Where a training run lives: its Modal app, its name, and its local folders."""

    app_name: str
    run_name: str
    runs_dir: Path
    records_dir: Path
    game_config: Path
    concurrency: int


class GameSpec(NamedTuple):
    """One game to play: its seed, its number within the seed, and the adapter that plays it.

    ``config`` is the seed's game config, ``labels`` the run's labels, ``log_path`` the file
    that takes the terminal output of ``glossogen run``, and ``urls`` the self-hosted models'
    ``SELF_HOSTED_BASE_URLS``.
    """

    seed: int
    game: int
    adapter: int
    config: Path
    labels: list[str]
    log_path: Path
    urls: dict[str, str]


class Game(NamedTuple):
    """One game that the loop launched: its seed, its number, the adapter that played it, its run
    id and the exit code of ``glossogen run``."""

    seed: int
    game: int
    adapter: int
    run_id: str
    returncode: int


class Backend(Protocol):
    """The deployed app, as the loop calls it."""

    async def serve_url(self) -> str:
        """The ``/v1`` URL of the policy server."""
        ...

    async def load_adapter(self, *, step: int, keep: list[int]) -> None:
        """Load adapter ``step`` on the policy server, and unload each adapter not in ``keep``."""
        ...

    async def train_step(
        self, *, step: int, sequences: list[TrainingSequence], run_ids: list[str]
    ) -> StepMetrics:
        """Train adapter ``step - 1`` on the sequences of the games ``run_ids``; save adapter
        ``step``."""
        ...

    async def run_partner(self) -> Partner | None:
        """The frozen partner that ``init`` saved in the run's settings."""
        ...


class GameLauncher(Protocol):
    """Plays one game."""

    async def play(self, *, spec: GameSpec) -> Game:
        """Play the game that ``spec`` describes and label its run."""
        ...


class Loop(NamedTuple):
    """A training run's settings and the services that its loop calls."""

    settings: LoopSettings
    backend: Backend
    launcher: GameLauncher


def run_folder(*, settings: LoopSettings) -> Path:
    """The local folder of the training run's configs, game logs and records."""
    return settings.records_dir / settings.run_name


def model_name(*, run_name: str, step: int) -> str:
    """The model name under which the policy server plays adapter ``step``."""
    return f"{run_name}-step{step}"


def adapter_path(*, run_name: str, step: int) -> str:
    """Where grpo_app.py saves adapter ``step`` on its volume, as the server sees it."""
    return f"/grpo/runs/{run_name}/adapters/step_{step}"


def adapter_request(*, run_name: str, step: int, keep: list[int]) -> AdapterRequest:
    """The request that loads adapter ``step`` and keeps the adapters ``keep``."""
    return AdapterRequest(
        id=str(uuid.uuid4()),
        name=model_name(run_name=run_name, step=step),
        path=adapter_path(run_name=run_name, step=step),
        keep=tuple(model_name(run_name=run_name, step=kept) for kept in keep),
    )


class ModalBackend:
    """The deployed app of ``app_name``, for the training run ``run_name``."""

    def __init__(self, *, app_name: str, run_name: str) -> None:
        self._app_name = app_name
        self._run_name = run_name
        self._requests = asyncio.Lock()

    async def serve_url(self) -> str:
        """The ``/v1`` URL of the policy server of the deployed app."""
        url = await modal.Function.from_name(self._app_name, "serve").get_web_url.aio()
        if url is None:
            raise RuntimeError(f"{self._app_name}'s serve function has no web URL; is it deployed?")
        return f"{url}/v1"

    async def load_adapter(self, *, step: int, keep: list[int]) -> None:
        """Write the request into the control Dict, and wait until the loader reports it."""
        control = modal.Dict.from_name(f"{self._app_name}-adapters", create_if_missing=True)
        request = adapter_request(run_name=self._run_name, step=step, keep=keep)
        async with self._requests:
            await control.put.aio(ADAPTER_REQUEST_KEY, request)
            result = await self._wait_for_result(control=control, request=request)
        if not result.loaded:
            raise RuntimeError(f"loading {request.name} failed: {result.status} {result.body}")
        print(f"loaded {request.name}", flush=True)

    async def _wait_for_result(self, *, control: Any, request: AdapterRequest) -> AdapterResult:
        """The loader's result for ``request``, once the loader writes it."""
        deadline = time.monotonic() + ADAPTER_LOAD_WAIT_SECONDS
        while time.monotonic() < deadline:
            result = await control.get.aio(ADAPTER_RESULT_KEY)
            if isinstance(result, AdapterResult) and result.id == request.id:
                return result
            await asyncio.sleep(5)
        raise RuntimeError(f"the policy server did not load {request.name} in time")

    async def train_step(
        self, *, step: int, sequences: list[TrainingSequence], run_ids: list[str]
    ) -> StepMetrics:
        """One step of the deployed trainer."""
        trainer = modal.Cls.from_name(self._app_name, "Trainer")(run_name=self._run_name)
        return await trainer.train_step.remote.aio(step=step, sequences=sequences, run_ids=run_ids)

    async def run_partner(self) -> Partner | None:
        """The partner in the run's ``settings.json`` on the app's volume."""
        volume = modal.Volume.from_name(self._app_name)
        path = f"runs/{self._run_name}/settings.json"
        data = b""
        async for chunk in volume.read_file.aio(path):
            data += chunk
        run_settings = json.loads(data)
        if "partner" not in run_settings:
            raise ValueError(f"{path} on {self._app_name} names no partner, not even null")
        if run_settings["partner"] is None:
            return None
        return Partner.model_validate(run_settings["partner"])


def game_environment(*, urls: dict[str, str]) -> dict[str, str]:
    """This process's environment for a game, with each self-hosted model served at its URL."""
    environment = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    environment["SELF_HOSTED_BASE_URLS"] = json.dumps(urls)
    return environment


def logged_run_id(*, log_path: Path) -> str | None:
    """The run id that ``glossogen run`` printed into its log, or None before it has."""
    match = NEW_RUN_ID.search(log_path.read_text(errors="replace"))
    if match is None:
        return None
    return match.group(1)


async def wait_for_run_id(*, log_path: Path, process: asyncio.subprocess.Process) -> str:
    """The run id that ``glossogen run`` prints once it has created the run directory."""
    for _ in range(RUN_ID_WAIT_SECONDS):
        run_id = logged_run_id(log_path=log_path)
        if run_id is not None:
            return run_id
        if process.returncode is not None:
            raise RuntimeError(f"{log_path.name}: exited {process.returncode} before a run id")
        await asyncio.sleep(1)
    raise RuntimeError(f"{log_path.name}: no run id after {RUN_ID_WAIT_SECONDS}s")


def write_labels(*, run_dir: Path, labels: list[str]) -> None:
    """Write a new run's labels."""
    (run_dir / RUN_LABELS_FILENAME).write_text(json.dumps(labels) + "\n")


class GlossogenRunLauncher:
    """Plays a game with ``glossogen run`` in a subprocess, as the policy's model name."""

    def __init__(self, *, settings: LoopSettings) -> None:
        self._settings = settings

    async def play(self, *, spec: GameSpec) -> Game:
        """Run the game, label its run once it has a run id, and wait for it to end.

        A cancelled game stops its ``glossogen run``.
        """
        model = model_name(run_name=self._settings.run_name, step=spec.adapter)
        command = [
            "uv", "run", "--no-sync", "python", "-m", "glossogen", "run", SCENARIO,
            "--model", model, "--provider", "self-hosted",
            "--runs-dir", str(self._settings.runs_dir),
            "--max-agent-turns", str(MAX_AGENT_TURNS), "--config", str(spec.config),
        ]  # fmt: skip
        with spec.log_path.open("w") as log_file:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=REPO_ROOT,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
                env=game_environment(urls=spec.urls),
            )
            try:
                run_id = await wait_for_run_id(log_path=spec.log_path, process=process)
                write_labels(run_dir=self._settings.runs_dir / run_id, labels=spec.labels)
                returncode = await process.wait()
            finally:
                await stop_if_running(process=process)
        return Game(
            seed=spec.seed,
            game=spec.game,
            adapter=spec.adapter,
            run_id=run_id,
            returncode=returncode,
        )


async def stop_if_running(*, process: asyncio.subprocess.Process) -> None:
    """Terminate a ``glossogen run`` that is still running, and wait for it to exit."""
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    await process.wait()
