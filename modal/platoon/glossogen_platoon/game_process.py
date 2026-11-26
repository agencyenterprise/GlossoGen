"""Running one signal_game game with ``glossogen run``, and scoring it, as subprocesses in
GlossoGen's environment.

GlossoGen and platoon need different versions of huggingface-hub, so they live in two environments:
the repository's, and this project's. The harness runs in this project's, and starts the game and
the scorer with ``uv run --no-sync`` in the repository's.

Each seat plays a model at an OpenAI-compatible URL, or a model of another provider.
``SELF_HOSTED_BASE_URLS`` maps each self-hosted seat's model name to its URL. GlossoGen sends
``SELF_HOSTED_API_KEY`` to every self-hosted URL. A platoon agent's URL carries the agent's key in
its path and ignores that header, so the environment's own key is passed on for a self-hosted seat
outside platoon.
"""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from glossogen_platoon.game_scores import GameScores

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SCENARIO = "signal_game"
SELF_HOSTED = "self-hosted"
PLACEHOLDER_API_KEY = "platoon-agents-carry-their-key-in-the-url"
RUN_ID_PATTERN = re.compile(r"new_run_id=(\S+)")


class SeatModel(NamedTuple):
    """The model that plays one seat: its name, its GlossoGen provider, and its URL when it is
    self-hosted."""

    model: str
    provider: str
    base_url: str | None


class GameSettings(NamedTuple):
    """Where a game's files go, and how it is configured."""

    game_config: Path
    runs_dir: Path
    max_agent_turns: int


def game_config(*, base: dict[str, Any], seed: int, player_b: SeatModel) -> dict[str, Any]:
    """The game config for ``seed``, with player_b on its own model.

    Refuses a config that records token ids: platoon records every call's tokens itself, and its
    gateway does not return them to GlossoGen.
    """
    if base["record_token_ids"]:
        raise ValueError("the game config must set record_token_ids to false under platoon")
    config = dict(base)
    config["seed"] = seed
    config["model_overrides"] = {
        "player_b": {"model": player_b.model, "provider": player_b.provider}
    }
    return config


def self_hosted_urls(*, seats: dict[str, SeatModel]) -> dict[str, str]:
    """``SELF_HOSTED_BASE_URLS``: the URL of each self-hosted seat's model, by model name."""
    urls: dict[str, str] = {}
    for seat, model in seats.items():
        if model.provider != SELF_HOSTED:
            continue
        if model.base_url is None:
            raise ValueError(f"{seat} is self-hosted and has no base_url")
        if urls.get(model.model, model.base_url) != model.base_url:
            raise ValueError(f"two self-hosted seats name the model {model.model} at two URLs")
        urls[model.model] = model.base_url
    return urls


def game_environment(*, seats: dict[str, SeatModel], external_self_hosted: bool) -> dict[str, str]:
    """The environment of ``glossogen run``: this process's, without its virtualenv, with the seats'
    URLs."""
    environment = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    environment["SELF_HOSTED_BASE_URLS"] = json.dumps(self_hosted_urls(seats=seats))
    if not external_self_hosted:
        environment["SELF_HOSTED_API_KEY"] = PLACEHOLDER_API_KEY
    elif "SELF_HOSTED_API_KEY" not in environment:
        raise ValueError("a self-hosted seat outside platoon needs SELF_HOSTED_API_KEY")
    return environment


def run_command(*, settings: GameSettings, config_path: Path, player_a: SeatModel) -> list[str]:
    """The ``glossogen run`` command of one game."""
    return [
        "uv", "run", "--no-sync", "python", "-m", "glossogen", "run", SCENARIO,
        "--model", player_a.model, "--provider", player_a.provider,
        "--runs-dir", str(settings.runs_dir), "--max-agent-turns", str(settings.max_agent_turns),
        "--config", str(config_path),
    ]  # fmt: skip


async def play_game(
    *,
    settings: GameSettings,
    seed: int,
    seats: dict[str, SeatModel],
    external_self_hosted: bool,
) -> str:
    """Play one game on ``seed`` and return its run id; raise when ``glossogen run`` fails."""
    game_dir = settings.runs_dir / "platoon_games" / uuid.uuid4().hex
    game_dir.mkdir(parents=True)
    base = json.loads(settings.game_config.read_text())
    config_path = game_dir / "config.json"
    config = game_config(base=base, seed=seed, player_b=seats["player_b"])
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    log_path = game_dir / "glossogen_run.log"
    with log_path.open("w") as log_file:
        process = await asyncio.create_subprocess_exec(
            *run_command(settings=settings, config_path=config_path, player_a=seats["player_a"]),
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            env=game_environment(seats=seats, external_self_hosted=external_self_hosted),
        )
        returncode = await process.wait()
    log_text = log_path.read_text(errors="replace")
    match = RUN_ID_PATTERN.search(log_text)
    if returncode != 0 or match is None:
        raise RuntimeError(
            f"glossogen run exited {returncode}; log {log_path}:\n{log_text[-2000:]}"
        )
    return match.group(1)


async def score_game(*, run_dir: Path, labels: list[str]) -> GameScores:
    """Write the game's labels and read its scores, with ``glossogen_side.score_game``."""
    environment = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    process = await asyncio.create_subprocess_exec(
        "uv", "run", "--no-sync", "--project", str(REPO_ROOT),
        "python", "-m", "glossogen_side.score_game", "--run-dir", str(run_dir), "--labels", *labels,
        cwd=PROJECT_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )  # fmt: skip
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"the scorer exited {process.returncode}: {stderr.decode()[-2000:]}")
    return GameScores.model_validate_json(stdout)
