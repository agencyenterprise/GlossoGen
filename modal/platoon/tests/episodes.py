"""Playing signal_game episodes on CPU with scripted players, and crediting them as platoon's
trainer does.

Each episode plays a real GlossoGen game: the harness runs ``glossogen run`` in the repository's
environment, so the repository needs ``make install`` first. The helpers that build a credit group
use platoon 0.6.0's own conversion and crediting functions, which are not part of its public API;
this project pins that version.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import glossogen_platoon.signal_game  # noqa: F401  (registers the harness, the program and the estimator)
from glossogen_platoon.harness import HARNESS_NAME
from glossogen_platoon.program import PROGRAM_NAME
from platoon.task import Task
from platoon.testing import EpisodeRun, ScriptedPolicy, run_episode
from platoon.train.config_defs import WorkflowConfig
from platoon.train.credit.api import CreditGroup, PolicyView
from platoon.train.policy.spec import MAIN
from platoon.train.workflow.crediting import member_rollout
from platoon.utils.stats_tracker import DeferredStats
from platoon.utils.tinker_data_processing import get_train_data_for_trajectory_collection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "configs" / "signal_game_shapes.json"
GOAL = "Play one signal_game game."
MAX_STEPS = 400
TIMEOUT_SECONDS = 1800


def task_row(*, seed: int) -> dict[str, Any]:
    """The task table's row of ``seed``."""
    return {"id": f"seed-{seed}", "goal": GOAL, "seed": seed}


def harness_options(*, runs_dir: Path, external_seats: Mapping[str, Any]) -> dict[str, Any]:
    """The harness options of a test episode, with absolute paths."""
    return {
        "game_config": str(GAME_CONFIG),
        "runs_dir": str(runs_dir),
        "labels": ["platoon_test"],
        "external_seats": dict(external_seats),
        "max_agent_turns": MAX_STEPS,
    }


async def play_episode(
    *,
    seed: int,
    runs_dir: Path,
    policy: ScriptedPolicy,
    external_seats: Mapping[str, Any],
    reward: str,
) -> EpisodeRun:
    """One signal_game game as one platoon episode, with ``policy`` playing every seat that platoon
    serves."""
    row = task_row(seed=seed)
    return await run_episode(
        task=Task(id=row["id"], goal=GOAL, misc={"seed": seed}),
        service="table",
        service_kwargs={"rows": [row]},
        harness=HARNESS_NAME,
        policy=policy,
        harness_options=harness_options(runs_dir=runs_dir, external_seats=external_seats),
        program=PROGRAM_NAME,
        max_steps=MAX_STEPS,
        rollout={"extra": {"glossogen_reward": reward}, "timeout": TIMEOUT_SECONDS},
    )


def credit_group(
    *, runs: list[EpisodeRun], task_id: str, policies: Mapping[str, PolicyView]
) -> CreditGroup:
    """The episodes as one training group of ``main``, each member's rows tagged with its agents."""
    results = [
        get_train_data_for_trajectory_collection(
            trajectory_collection=run.collection.to_dict(),
            interactions=run.interactions,
            task_id=task_id,
            checkpoint_version=0,
            tag_datums=True,
        )
        for run in runs
    ]
    return CreditGroup(
        task_id=task_id,
        label=None,
        entry="signal-game",
        settings=WorkflowConfig(),
        members=[
            member_rollout(index=index, result=result, policy=MAIN, tagged=True)
            for index, result in enumerate(results)
        ],
        policies={MAIN: PolicyView(id=MAIN), **policies},
        versions={MAIN: 0},
        stats=DeferredStats(),
    )


def seat_trajectories(*, run: EpisodeRun) -> dict[str, Any]:
    """Each seat's trajectory of an episode, by the role its agent was minted with."""
    return {
        trajectory.misc["agent"]["role"]: trajectory
        for trajectory in run.collection.trajectories.values()
        if "spans" in trajectory.misc
    }
