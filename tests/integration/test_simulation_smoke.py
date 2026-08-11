"""Smoke tests that run a real simulation against a fake LLM.

Only the model is faked. The MCP server, tool dispatch, runtime, game clock and
event logger all run for real, so these catch breakage that no component test
sees.
"""

from pathlib import Path

import pytest

from tests.fakes.scripted_agent_model import SayTurn, ToolTurn
from tests.testbed.simulation_harness import run_simulation
from tests.testbed.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


def build_scenario(*, round_count: int, round_seconds: float) -> SmokeScenario:
    """Build the smoke scenario with a short round so tests stay fast."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=round_count,
            max_round_duration_seconds=round_seconds,
            model_overrides={},
            round_time_budget_seconds=600,
        )
    )


def exercise_every_base_tool(*, message: str) -> list[ToolTurn | SayTurn]:
    """Return turns calling every base tool plus the scenario's custom one.

    The send forces on purpose. Both agents act at once and ``send_message``
    applies optimistic concurrency, so whichever sends second is told the channel
    moved under it and its message is dropped. That behaviour is correct but
    depends on interleaving, and this test is about the plumbing, not the race.
    """
    return [
        ToolTurn(tool_name="list_channels", args={}),
        ToolTurn(tool_name="get_channel_members", args={"channel_id": LINK_CHANNEL_ID}),
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": message, "force": True},
        ),
        ToolTurn(tool_name="read_channel", args={"channel_id": LINK_CHANNEL_ID, "last_n": 10}),
        ToolTurn(tool_name=RECORD_TOOL_NAME, args={"finding": f"finding from {message}"}),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="done"),
    ]


async def test_a_full_round_writes_everything_to_the_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One round, two agents, every base tool and the custom tool.

    Asserts against the JSONL rather than in-memory state. The log is what the
    viewer, the metrics and the fork/resume flows all read, so anything that
    happened without being logged did not happen as far as they know.
    """
    scenario = build_scenario(round_count=1, round_seconds=45)

    result = await run_simulation(
        scenario=scenario,
        scripts={
            FIRST_AGENT_ID: exercise_every_base_tool(message="AB12 from first"),
            SECOND_AGENT_ID: exercise_every_base_tool(message="CD34 from second"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    # The run identifies itself, including the scenario's own description.
    started = result.of_type(event_type="simulation_started")
    assert len(started) == 1
    assert started[0]["scenario_description"] == scenario.scenario_description()

    # Both agents were registered, with the roles the scenario declared.
    registered = {e["agent_id"] for e in result.of_type(event_type="agent_registered")}
    assert registered == {FIRST_AGENT_ID, SECOND_AGENT_ID}

    # The round opened and each agent received its injection.
    injections = result.of_type(event_type="injection_delivered")
    assert {e["agent_id"] for e in injections} == {FIRST_AGENT_ID, SECOND_AGENT_ID}
    assert all("Round 1" in str(e["text"]) for e in injections)

    # Every base tool and the custom tool actually dispatched.
    for tool in (
        "list_channels",
        "get_channel_members",
        "send_message",
        "read_channel",
        "read_notifications",
        RECORD_TOOL_NAME,
    ):
        assert result.tool_calls(tool_name=tool), f"{tool} was never invoked"

    # No tool call failed. Failures come back as text, so without this the test
    # would pass with every call rejected.
    assert result.failed_tool_calls() == []
    assert result.conflicted_sends() == []

    # Both agents' messages reached the channel, with their text intact.
    texts = {str(m["text"]) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)}
    assert "AB12 from first" in texts
    assert "CD34 from second" in texts

    # The custom tool wrote through to the scenario's own world, attributed to
    # the agent that called it. Tool context reaches scenario code.
    callers = {agent_id for _, agent_id, _ in scenario.get_world().findings}
    assert callers == {FIRST_AGENT_ID, SECOND_AGENT_ID}

    # The round ended, was judged, and the run terminated cleanly.
    assert result.of_type(event_type="round_ended")
    verdicts = result.of_type(event_type="round_result_recorded")
    assert len(verdicts) == 1
    assert verdicts[0]["success"] is True
    ended = result.of_type(event_type="simulation_ended")
    assert len(ended) == 1
    assert ended[0]["reason"] != "error"


async def test_all_agents_going_idle_advances_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When every agent parks on read_notifications, the clock advances early.

    The round has a long wall-clock limit, so an advance can only have come from
    idle detection. That is what lets a run finish in seconds instead of sitting
    out every round.
    """
    scenario = build_scenario(round_count=2, round_seconds=120)

    # Nothing but an immediate park: no messages, no work, just idle.
    idle_only = [
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]

    result = await run_simulation(
        scenario=scenario,
        scripts={FIRST_AGENT_ID: list(idle_only), SECOND_AGENT_ID: list(idle_only)},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    advances = result.of_type(event_type="round_advanced")
    # The first advance opens round 1; the ones after it are real transitions.
    triggers = [str(e["trigger"]) for e in advances]
    assert triggers[0] == "simulation_start"
    assert triggers[1:], "the clock never advanced past the opening round"
    assert all(
        t == "all_agents_idle" for t in triggers[1:]
    ), f"expected idle-driven advances, got {triggers}"

    assert result.of_type(event_type="simulation_ended")
