"""The scenario through the real runner, MCP tools and game clock, with scripted models."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.textcraft_shared_workspace.scenario import (
    TextcraftSharedWorkspaceScenario,
)
from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_round_loop_completed,
    build_scenario,
)
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")

SMALL: dict[str, Any] = {
    "crafter_count": 2,
    "steps_per_agent": 1,
    "pool_agent_count": 2,
    "dag_cross_edge_density": 0.0,
    "virtual_clock": False,
    "max_round_duration_seconds": 30,
}


def build(preset_name: str, overrides: dict[str, Any]) -> TextcraftSharedWorkspaceScenario:
    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name=preset_name,
        overrides={**SMALL, **overrides},
    )
    assert isinstance(scenario, TextcraftSharedWorkspaceScenario)
    return scenario


def witness(scenario: TextcraftSharedWorkspaceScenario) -> list[str]:
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    return [command for _, command in task.witness]


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def act(command: str) -> ToolTurn:
    return ToolTurn(tool_name="act", args={"command": command})


def finish() -> ToolTurn:
    return ToolTurn(tool_name="finish", args={})


async def run(
    scenario: TextcraftSharedWorkspaceScenario,
    scripts: dict[str, list[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    async with asyncio.timeout(60):
        result = await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
    assert_no_agent_crashed(result=result)
    return result


def resolved(result: SimulationResult) -> dict[str, Any]:
    return result.of_type(event_type="workspace_round_resolved")[0]


async def test_a_team_crafting_every_target_wins_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    first, second = witness(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [read(), act(command=first), finish()],
        "crafter_2": [read(), act(command=second), finish()],
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome["success"]
    assert outcome["trigger"] == "all_targets_satisfied"
    actions = result.of_type(event_type="workspace_action_executed")
    assert [action["version"] for action in actions] == [1, 2]
    assert all("Depot now" in action["observation"] for action in actions)


async def test_a_message_wakes_a_waiting_teammate_and_is_delivered_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    first, second = witness(scenario=scenario)
    note = "I take column one."
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [
            read(),
            ToolTurn(tool_name="send", args={"text": note}),
            act(command=first),
            finish(),
        ],
        "crafter_2": [
            read(),
            ToolTurn(tool_name="wait_for_message", args={}),
            act(command=second),
            ToolTurn(tool_name="observe", args={}),
            finish(),
        ],
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    outcome = resolved(result=result)
    assert outcome["success"]
    assert outcome["characters_used"] == len(note)
    waits = [e for e in result.of_type(event_type="wait_registered") if e["kind"] == "message"]
    assert [e["agent_id"] for e in waits] == ["crafter_2"]
    wake = next(
        e for e in result.of_type(event_type="agent_resumed") if e["wait_id"] == waits[0]["wait_id"]
    )
    assert "new_public_message" in wake["wake_reasons"]
    assert note in wake["wake_package"]["workspace"]
    deliveries = result.of_type(event_type="workspace_message_context_delivered")
    assert [(e["agent_id"], e["delivery_carrier"]) for e in deliveries] == [("crafter_2", "wake")]
    receipt = next(
        e["result"]
        for e in result.of_type(event_type="tool_result_received")
        if e["tool_name"] == "send"
    )
    assert '"status": "sent"' in receipt and "Depot now" in receipt


@pytest.mark.parametrize("round_count", [1, 2])
async def test_finish_is_a_round_claim_and_the_next_round_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, round_count: int
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"round_count": round_count})
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [read(), *[finish() for _ in range(round_count)]]
        for agent in ("crafter_1", "crafter_2")
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert_round_loop_completed(result=result, round_count=round_count)
    outcomes = result.of_type(event_type="workspace_round_resolved")
    assert len(outcomes) == round_count
    assert all(e["trigger"] == "all_agents_finished" and not e["success"] for e in outcomes)


async def test_a_turn_that_ends_in_text_counts_as_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [read(), SayTurn(text="I am done.")],
        "crafter_2": [read(), finish()],
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    implicit = [e for e in result.of_type(event_type="wait_registered") if e["implicit"]]
    assert [(e["agent_id"], e["kind"]) for e in implicit] == [("crafter_1", "finish")]
    assert resolved(result=result)["trigger"] == "all_agents_finished"


async def test_a_team_parked_without_deadlines_ends_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [read(), ToolTurn(tool_name="wait_for_message", args={})]
        for agent in ("crafter_1", "crafter_2")
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert resolved(result=result)["trigger"] == "all_agents_waiting"
    resumed = result.of_type(event_type="agent_resumed")
    assert all("deadline" not in e["wake_reasons"] for e in resumed)
    assert all(e["terminated"] for e in resumed)


async def test_a_wait_with_a_timeout_wakes_on_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"virtual_clock": True})
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [
            read(),
            ToolTurn(tool_name="wait_for_message", args={"timeout_s": 5}),
            finish(),
        ],
        "crafter_2": [read(), finish()],
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    wake = next(
        e for e in result.of_type(event_type="agent_resumed") if e["agent_id"] == "crafter_1"
    )
    assert wake["wake_reasons"] == ["deadline"]
    assert wake["waited_seconds"] == 5.0


async def test_silent_agents_are_offered_no_channel_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_no_comms", overrides={})
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [read(), ToolTurn(tool_name="send", args={"text": "hi"}), finish()]
        for agent in ("crafter_1", "crafter_2")
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert not result.messages_on(channel_id="workspace")
    assert resolved(result=result)["characters_used"] == 0


async def test_effects_follow_simulated_latency_not_arrival_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(
        preset_name="knobs_default",
        overrides={"virtual_clock": True, "virtual_output_tokens_per_second": 10.0},
    )
    first, second = witness(scenario=scenario)
    long_message = " ".join(f"word{index}" for index in range(300))
    # crafter_1 first writes a long message, so its craft lands late in virtual
    # time; crafter_2 crafts at once. The scripted model answers both instantly.
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [
            ToolTurn(tool_name="send", args={"text": long_message}),
            act(command=second),
            finish(),
        ],
        "crafter_2": [act(command=first), finish()],
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    releases = [
        e
        for e in result.of_type(event_type="virtual_request_released")
        if e["agent_id"] == "crafter_1"
    ]
    send, craft = releases[:2]
    assert send["started_at_s"] == 0.0 and send["completed_at_s"] > 20.0
    assert craft["started_at_s"] == send["completed_at_s"]
    actions = result.of_type(event_type="workspace_action_executed")
    assert [action["agent_id"] for action in actions] == ["crafter_2", "crafter_1"]
    times = [action["virtual_time_s"] for action in actions]
    assert times[0] < send["completed_at_s"] < times[1]
    outcome = resolved(result=result)
    assert outcome["success"]
    assert outcome["virtual_elapsed_seconds"] == times[1]


@pytest.mark.parametrize("split", [True, False])
async def test_timed_crafts_overlap_across_agents_and_queue_within_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, split: bool
) -> None:
    overrides: dict[str, Any] = {"virtual_clock": True, "craft_duration_s": 20.0}
    if not split:
        overrides.update(pool_agent_count=1, comms_enabled=False)
    scenario = build(preset_name="knobs_default", overrides=overrides)
    first, second = witness(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        "crafter_1": [act(command=first), act(command=second), finish()]
    }
    if split:
        scripts = {
            "crafter_1": [act(command=first), finish()],
            "crafter_2": [act(command=second), finish()],
        }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    starts = result.of_type(event_type="workspace_action_executed")
    landings = result.of_type(event_type="workspace_craft_completed")
    assert len(starts) == len(landings) == 2
    assert all(count < 0 for start in starts for count in start["delta"].values())
    assert all(count > 0 for landing in landings for count in landing["delta"].values())
    assert all(landing["virtual_time_s"] - landing["started_at_s"] == 20.0 for landing in landings)
    outcome = resolved(result=result)
    assert outcome["success"]
    makespan = outcome["virtual_elapsed_seconds"]
    assert makespan == max(landing["virtual_time_s"] for landing in landings)
    if split:
        assert 20.0 < makespan < 25.0
    else:
        assert makespan > 40.0


async def test_released_responses_are_charged_to_the_team_token_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"team_token_limit": 1})
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [read(), finish()] for agent in ("crafter_1", "crafter_2")
    }
    result = await run(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert resolved(result=result)["trigger"] == "team_tokens_exhausted"
