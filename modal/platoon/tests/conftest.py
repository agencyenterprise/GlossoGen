"""Fixtures shared by the tests: a group of signal_game episodes on one seed, played once per
session."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from platoon.testing import EpisodeRun, ScriptedPolicy

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from episodes import play_episode  # noqa: E402
from scripted_player import signal_game_player  # noqa: E402

GROUP_SEED = 1000
GROUP_GAMES = 3


@pytest.fixture(scope="session")
def first_item_group(tmp_path_factory: pytest.TempPathFactory) -> list[EpisodeRun]:
    """Three episodes on one seed, trained on ``first_item``, each seat played by the scripted
    player."""
    runs_dir = tmp_path_factory.mktemp("group_runs")

    async def play_all() -> list[EpisodeRun]:
        return list(
            await asyncio.gather(
                *(
                    play_episode(
                        seed=GROUP_SEED,
                        runs_dir=runs_dir,
                        policy=ScriptedPolicy(script=signal_game_player),
                        external_seats={},
                        reward="first_item",
                    )
                    for _ in range(GROUP_GAMES)
                )
            )
        )

    return asyncio.run(play_all())
