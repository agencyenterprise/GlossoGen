"""The layered task generator and manifest replay."""

from collections import Counter
from pathlib import Path

import pytest

from glossogen.scenarios.textcraft_shared_workspace.tasks import (
    WorkspaceTask,
    generate_task,
    load_task_manifest,
)
from glossogen.testing.scenario_runtime import build_scenario

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")


def layered(seed: int, width: int, span: int, density: float, slack: float) -> WorkspaceTask:
    """A task with the shipped preset's raw-material settings."""
    return generate_task(
        seed=seed,
        width=width,
        span=span,
        quantity_scale=2,
        resource_slack_fraction=slack,
        max_fan_in=2,
        cross_edge_density=density,
        raw_material_count=None,
        max_raw_inputs=2,
    )


@pytest.mark.parametrize("width", [1, 2, 5])
@pytest.mark.parametrize("span", [1, 3])
@pytest.mark.parametrize("density", [0.0, 0.3, 1.0])
def test_work_span_and_width_are_exact_whatever_the_coupling(
    width: int, span: int, density: float
) -> None:
    task = layered(seed=7, width=width, span=span, density=density, slack=0.0)
    assert len(task.cards) == width
    assert all(len(card.recipes) == span for card in task.cards.values())
    assert len(task.witness) == width * span


def test_zero_density_gives_independent_chains_and_density_adds_cross_edges() -> None:
    def cross_edges(task: WorkspaceTask) -> int:
        owner = {
            recipe.output: column for column, card in task.cards.items() for recipe in card.recipes
        }
        return sum(
            1
            for column, card in task.cards.items()
            for recipe in card.recipes
            for item in recipe.inputs
            if item in owner and owner[item] != column
        )

    assert cross_edges(task=layered(seed=3, width=4, span=3, density=0.0, slack=0.0)) == 0
    assert cross_edges(task=layered(seed=3, width=4, span=3, density=1.0, slack=0.0)) > 0


def test_the_witness_spends_every_raw_item_exactly_without_slack() -> None:
    task = layered(seed=11, width=3, span=2, density=0.3, slack=0.0)
    depot = Counter(task.initial_depot)
    for column, command in task.witness:
        recipe = next(r for r in task.cards[column].recipes if r.command == command)
        depot.subtract(recipe.inputs)
        depot[recipe.output] += recipe.count
    assert all(depot[item] == 0 for item in task.initial_depot)
    assert all(depot[card.target] == 1 for card in task.cards.values())


def test_slack_adds_a_rounded_up_share_of_each_raw_need() -> None:
    exact = layered(seed=5, width=3, span=2, density=0.3, slack=0.0)
    slack = layered(seed=5, width=3, span=2, density=0.3, slack=0.2)
    assert {
        item: count - exact.initial_depot[item] for item, count in slack.initial_depot.items()
    } == {item: -(-count // 5) for item, count in exact.initial_depot.items()}


def test_generation_is_deterministic_and_the_task_id_is_content_addressed() -> None:
    first = layered(seed=42, width=4, span=2, density=0.3, slack=0.2)
    again = layered(seed=42, width=4, span=2, density=0.3, slack=0.2)
    other = layered(seed=43, width=4, span=2, density=0.3, slack=0.2)
    assert first == again
    assert first.task_id == again.task_id
    assert first.task_id != other.task_id


def test_a_tampered_witness_fails_certification() -> None:
    task = layered(seed=1, width=2, span=2, density=0.0, slack=0.0)
    broken = task.model_copy(update={"witness": list(reversed(task.witness))})
    with pytest.raises(ValueError, match="infeasible witness"):
        broken.certify()


def test_a_manifest_replays_offline_tasks(tmp_path: Path) -> None:
    task = layered(seed=123, width=4, span=2, density=0.3, slack=0.2)
    manifest = tmp_path / "tasks.json"
    manifest.write_text("[" + task.model_dump_json() + "]")
    assert load_task_manifest(path=str(manifest)) == [task]
    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name="knobs_default",
        overrides={"task_manifest": str(manifest), "round_count": 1},
    )
    briefing = scenario.get_injection(round_number=1, agent_id="crafter_1")
    assert briefing is not None and briefing.count("craft ") == 8


def test_a_manifest_must_match_the_grid_width(tmp_path: Path) -> None:
    task = layered(seed=123, width=2, span=2, density=0.3, slack=0.2)
    manifest = tmp_path / "tasks.json"
    manifest.write_text("[" + task.model_dump_json() + "]")
    with pytest.raises(ValueError, match="crafter_count columns"):
        build_scenario(
            scenario_name="textcraft_shared_workspace",
            preset_name="knobs_default",
            overrides={"task_manifest": str(manifest), "round_count": 1},
        )
