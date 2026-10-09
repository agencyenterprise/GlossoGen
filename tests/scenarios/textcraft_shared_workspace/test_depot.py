"""Depot transitions: scarcity, observation cursors, uncraft and timed crafts."""

from collections import Counter

import pytest

from glossogen.scenarios.textcraft_shared_workspace.state import UNCRAFT_PREFIX, DepotState
from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask, generate_task

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")

SEATS = ["crafter_1", "crafter_2"]


def chain_task() -> WorkspaceTask:
    """Two independent two-step columns."""
    return generate_task(
        seed=42,
        width=2,
        span=2,
        quantity_scale=2,
        resource_slack_fraction=0.0,
        max_fan_in=2,
        cross_edge_density=0.0,
        raw_material_count=1,
        max_raw_inputs=1,
    )


def depot(task: WorkspaceTask, uncraft_enabled: bool) -> DepotState:
    return DepotState(task=task, seats=SEATS, uncraft_enabled=uncraft_enabled)


def test_missing_inputs_consume_nothing() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=False)
    second_layer = next(command for _, command in task.witness[2:])
    before = dict(state.depot)
    result = state.step(agent_id="crafter_1", command=second_layer)
    assert not result.accepted
    assert result.observation == "Craft failed: insufficient inputs."
    assert dict(state.depot) == before
    assert state.version == 0
    assert state.failed_crafts == 1


def test_there_is_no_fetch_or_transfer_command() -> None:
    state = depot(task=chain_task(), uncraft_enabled=False)
    for invented in ("get 100 r1", "deposit 1 r1", "withdraw 1 r1", "craft 0 fake using 0 fake"):
        result = state.step(agent_id="crafter_1", command=invented)
        assert not result.accepted
        assert result.observation.startswith("Invalid command.")


def test_the_witness_solves_and_targets_must_coexist() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=False)
    for _, command in task.witness:
        assert state.step(agent_id="crafter_1", command=command).accepted
    assert state.solved


def test_snapshots_show_absolute_zeroes_and_cursors_are_per_observer() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=False)
    _, command = task.witness[0]
    state.step(agent_id="crafter_1", command=command)
    first = state.observe(agent_id="crafter_1")
    second = state.observe(agent_id="crafter_1")
    peer = state.observe(agent_id="crafter_2")
    assert "v1:" in first and "v1:" in peer
    assert "none" in second
    assert "crafter_" not in peer
    for _, command in task.witness[1:]:
        state.step(agent_id="crafter_2", command=command)
    raw = next(iter(task.initial_depot))
    assert f"{raw}=0" in state.observe(agent_id="crafter_1")


def test_uncraft_removes_the_full_output_and_returns_every_input() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=True)
    _, command = task.witness[0]
    recipe = state.recipes[command]
    state.step(agent_id="crafter_1", command=command)
    result = state.step(agent_id="crafter_2", command=UNCRAFT_PREFIX + command)
    assert result.accepted
    assert +state.depot == Counter(task.initial_depot)
    assert result.delta == {**recipe.inputs, recipe.output: -recipe.count}
    assert state.version == 2


def test_uncraft_goes_back_one_step_to_the_intermediate() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=True)
    column, first = task.witness[0]
    second = next(command for owner, command in task.witness[1:] if owner == column)
    state.step(agent_id="crafter_1", command=first)
    before = +state.depot
    state.step(agent_id="crafter_1", command=second)
    assert state.step(agent_id="crafter_1", command=UNCRAFT_PREFIX + second).accepted
    assert +state.depot == before


def test_uncraft_fails_without_an_earlier_craft_or_once_its_output_is_consumed() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=True)
    column, first = task.witness[0]
    result = state.step(agent_id="crafter_1", command=UNCRAFT_PREFIX + first)
    assert not result.accepted
    assert result.observation == "Uncraft failed: not enough crafted output."
    second = next(command for owner, command in task.witness[1:] if owner == column)
    state.step(agent_id="crafter_1", command=first)
    state.step(agent_id="crafter_1", command=second)
    assert not state.step(agent_id="crafter_1", command=UNCRAFT_PREFIX + first).accepted


def test_disabled_uncraft_is_an_invalid_command() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=False)
    _, command = task.witness[0]
    state.step(agent_id="crafter_1", command=command)
    result = state.step(agent_id="crafter_1", command=UNCRAFT_PREFIX + command)
    assert not result.accepted
    assert result.observation.startswith("Invalid command.")


def test_undoing_and_redoing_every_craft_still_solves() -> None:
    for seed in range(10):
        task = generate_task(
            seed=seed,
            width=3,
            span=3,
            quantity_scale=2,
            resource_slack_fraction=0.0,
            max_fan_in=2,
            cross_edge_density=0.5,
            raw_material_count=None,
            max_raw_inputs=2,
        )
        state = DepotState(task=task, seats=list(task.cards), uncraft_enabled=True)
        for column, command in task.witness:
            assert state.step(agent_id=column, command=command).accepted
            assert state.step(agent_id=column, command=UNCRAFT_PREFIX + command).accepted
            assert state.step(agent_id=column, command=command).accepted
        assert state.solved


def test_a_started_craft_takes_its_inputs_and_lands_its_output_later() -> None:
    task = chain_task()
    state = depot(task=task, uncraft_enabled=True)
    _, command = task.witness[0]
    recipe = state.recipes[command]
    started = state.start(agent_id="crafter_1", command=command)
    assert started.accepted and started.pending is not None
    assert state.depot[recipe.output] == 0
    assert "Being crafted now" in state.observe(agent_id="crafter_2")
    # Its output is not in the depot yet, so it cannot be undone.
    assert not state.step(agent_id="crafter_2", command=UNCRAFT_PREFIX + command).accepted
    landed = state.finish(pending=started.pending)
    assert landed.delta == {recipe.output: recipe.count}
    assert state.depot[recipe.output] == recipe.count
