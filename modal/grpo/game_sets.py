"""Sets of games: a training step's games or a test's, their seed configs and their logs.

A game set is every game of one training step, or of one test of an adapter. Its games play
``loop.settings.concurrency`` at a time. Once a game gets a slot, it waits LAUNCH_GAP_SECONDS
times its index modulo the concurrency before it starts. A game that fails to start or to run
is printed and left out of the set's games.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, NamedTuple

from loop_services import (
    SCENARIO,
    Game,
    GameSpec,
    Loop,
    LoopSettings,
    model_name,
    run_folder,
)
from partner import Partner, partner_labels, self_hosted_urls

from glossogen.scenario_contract.loader import get_scenario_class

LAUNCH_GAP_SECONDS = 5


class GameSet(NamedTuple):
    """The games of one training step or one test.

    ``label`` is ``grpo`` or ``grpo_eval``, and ``step`` the training step or the tested adapter.
    ``adapter`` plays the policy's seats. ``labels`` are the labels before the run, step, seed
    and game ones.
    """

    label: str
    step: int
    adapter: int
    seeds: list[int]
    games_per_seed: int
    labels: list[str]
    partner: Partner | None


class PlayedGames(NamedTuple):
    """The games of a set that started, and how long the set took to play."""

    games: list[Game]
    seconds: float


def partner_suffix(*, partner: Partner | None) -> str:
    """The part of a config or log file name that names the partner, empty without one."""
    if partner is None:
        return ""
    return f"_vs_{partner.label()}"


def check_partner_seat(*, partner: Partner, config: dict[str, Any]) -> None:
    """Refuse a partner whose seat is not one of the scenario's agents."""
    roles = get_scenario_class(name=SCENARIO).get_agent_roles(knobs=config)
    seats = sorted(role.agent_id for role in roles)
    if partner.seat not in seats:
        raise ValueError(f"the partner's seat {partner.seat} is not one of {seats}")


def seed_config_text(*, game_config: Path, seed: int, partner: Partner | None) -> str:
    """The game config for ``seed``: the base config with its seed, and the partner's override."""
    config = json.loads(game_config.read_text())
    if config.get("record_token_ids") is not True:
        raise ValueError(f"{game_config} must set record_token_ids to true")
    if config.get("model_overrides"):
        raise ValueError(f"{game_config} must leave model_overrides empty; --partner names one")
    config["seed"] = seed
    if partner is not None:
        check_partner_seat(partner=partner, config=config)
        override = partner.model_override.model_dump(mode="json", exclude_none=True)
        config["model_overrides"] = {partner.seat: override}
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def seed_config(*, settings: LoopSettings, seed: int, partner: Partner | None) -> Path:
    """The game config for ``seed`` and ``partner``, written once.

    A run keeps its game config: when the file exists and the base config now gives another,
    this raises.
    """
    name = f"seed_{seed}{partner_suffix(partner=partner)}.json"
    path = run_folder(settings=settings) / "configs" / name
    text = seed_config_text(game_config=settings.game_config, seed=seed, partner=partner)
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"{path} differs from the config that {settings.game_config} gives")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def game_log_path(*, settings: LoopSettings, game_set: GameSet, seed: int, game: int) -> Path:
    """The file that takes the terminal output of one game's ``glossogen run``."""
    suffix = partner_suffix(partner=game_set.partner)
    name = f"{game_set.label}_step{game_set.step}{suffix}_seed{seed}_game{game}.log"
    return run_folder(settings=settings) / "game_logs" / name


def game_specs(*, settings: LoopSettings, game_set: GameSet, url: str) -> list[GameSpec]:
    """Every game of the set, game 1 of each seed first."""
    urls = self_hosted_urls(
        policy_model=model_name(run_name=settings.run_name, step=game_set.adapter),
        url=url,
        partner=game_set.partner,
    )
    specs: list[GameSpec] = []
    for game in range(1, game_set.games_per_seed + 1):
        for seed in game_set.seeds:
            labels = [
                *game_set.labels,
                *partner_labels(partner=game_set.partner),
                f"run={settings.run_name}",
                f"step={game_set.step}",
                f"adapter={game_set.adapter}",
                f"seed={seed}",
                f"game={game}",
            ]
            specs.append(
                GameSpec(
                    seed=seed,
                    game=game,
                    adapter=game_set.adapter,
                    config=seed_config(settings=settings, seed=seed, partner=game_set.partner),
                    labels=labels,
                    log_path=game_log_path(
                        settings=settings, game_set=game_set, seed=seed, game=game
                    ),
                    urls=urls,
                )
            )
    return specs


async def play_spec(*, loop: Loop, spec: GameSpec) -> Game:
    """Play one game; refuse a game whose log the loop already holds."""
    if spec.log_path.exists():
        raise RuntimeError(f"{spec.log_path} exists; not playing that game again")
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)
    return await loop.launcher.play(spec=spec)


async def play_game_set(*, loop: Loop, game_set: GameSet) -> PlayedGames:
    """Play every game of the set, ``loop.settings.concurrency`` at a time."""
    began = time.monotonic()
    concurrency = loop.settings.concurrency
    specs = game_specs(
        settings=loop.settings, game_set=game_set, url=await loop.backend.serve_url()
    )
    slots = asyncio.Semaphore(concurrency)

    async def guarded(index: int, spec: GameSpec) -> Game:
        async with slots:
            await asyncio.sleep(LAUNCH_GAP_SECONDS * (index % concurrency))
            return await play_spec(loop=loop, spec=spec)

    results = await asyncio.gather(
        *(guarded(index, spec) for index, spec in enumerate(specs)),
        return_exceptions=True,
    )
    games: list[Game] = []
    for result in results:
        if isinstance(result, Game):
            games.append(result)
        else:
            print(f"a game failed to start or to run: {result!r}", flush=True)
    return PlayedGames(games=games, seconds=time.monotonic() - began)
