"""One-to-one messaging: where a message goes, who may be addressed, and what it costs.

Played rounds check that a message naming one teammate lands on a direct channel
only the two of them share, is charged to the sender's team and scored with the
team's link, and that the discussion phase stays a broadcast while direct
messages close for it. Who a viewer may address is checked on the scenario
directly.
"""

from pathlib import Path

import pytest

from glossogen.models.event import ChannelCreated, ToolResultReceived
from glossogen.scenario_contract.scored_channels import scored_channel_ids
from glossogen.scenarios.spot_the_intersection.messaging import (
    DIRECT_MESSAGES_CLOSED_IN_DISCUSSION,
    LINK_IS_NOTICES_ONLY,
)
from glossogen.testing.scenario_runtime import build_scenario
from glossogen.testing.scripted_agent import EventGate, GatedTurn, SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    TEAM_B,
    answer_of,
    one_round_scenario,
    one_to_one_scenario,
    play,
    say_to,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)

DIRECT_A1_A2 = "dm:viewer_a_1+viewer_a_2"


async def test_a_message_lands_on_a_direct_channel_only_the_two_viewers_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_to_one_scenario(overrides={})
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {agent: [submit(obj=answer)] for agent in TEAM_A}
    scripts[TEAM_A[0]] = [say_to(to=TEAM_A[1], text="C4 red sq?"), submit(obj=answer)]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    (created,) = result.of_type(event_type=ChannelCreated)
    assert created.channel_id == DIRECT_A1_A2
    assert created.member_agent_ids == [TEAM_A[0], TEAM_A[1]]
    assert [message.text for message in result.messages_on(channel_id=DIRECT_A1_A2)] == [
        "C4 red sq?"
    ]
    assert result.messages_on(channel_id="link_a") == []
    outcome = world_of(scenario=result.scenario).outcome_for(team_id="team_a", round_number=1)
    assert outcome is not None
    assert outcome.correct
    assert outcome.characters_used == len("C4 red sq?")
    team_a_link = next(
        primary for primary in scenario.get_primary_channels() if primary.channel_id == "link_a"
    )
    assert scored_channel_ids(
        primary=team_a_link, scenario=scenario, events=result.events
    ) == frozenset({"link_a", DIRECT_A1_A2})
    (round_view,) = scenario.build_communication_rounds(events=result.events)
    assert [message.channel_id for message in round_view.messages] == [DIRECT_A1_A2]


def test_a_viewer_may_address_one_teammate_on_its_own_team() -> None:
    scenario = one_to_one_scenario(overrides={})

    assert scenario.validate_direct_channel(
        agent_id=TEAM_A[0], recipient_agent_ids=[TEAM_A[1]]
    ) is (None)
    assert (
        scenario.validate_direct_channel(agent_id=TEAM_A[0], recipient_agent_ids=[TEAM_B[0]])
        == f"'{TEAM_B[0]}' is not on your team."
    )
    assert (
        scenario.validate_direct_channel(
            agent_id=TEAM_A[0], recipient_agent_ids=[TEAM_A[1], TEAM_A[2]]
        )
        == "Address exactly one teammate per message."
    )
    assert (
        scenario.validate_outgoing_message(agent_id=TEAM_A[0], channel_id="link_a")
        == LINK_IS_NOTICES_ONLY
    )


def test_a_broadcast_run_opens_no_direct_channel() -> None:
    scenario = one_round_scenario()

    assert scenario.validate_direct_channel(
        agent_id=TEAM_A[0], recipient_agent_ids=[TEAM_A[1]]
    ) == ("This run has no direct channels: post on your team's link.")
    assert scenario.validate_outgoing_message(agent_id=TEAM_A[0], channel_id="link_a") is None


def test_one_to_one_messaging_needs_three_viewers() -> None:
    with pytest.raises(ValueError, match="needs team_size >= 3"):
        build_scenario(
            scenario_name=SCENARIO,
            preset_name="knobs_one_to_one",
            overrides={"team_size": 2, "decoy_count_values": [0], "decoy_count_weights": [1]},
        )


async def test_the_discussion_phase_is_a_broadcast_and_direct_messages_close_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every viewer submits, so the round ends early; viewer_a_1 then talks in the discussion."""
    scenario = one_to_one_scenario(overrides={"postmortem_enabled": True})
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[GatedTurn]] = {
        agent: [submit(obj=answer)] for agent in (*TEAM_A, *TEAM_B)
    }
    scripts[TEAM_A[0]] = [
        submit(obj=answer),
        EventGate(
            matches=lambda event: event["event_type"] == "postmortem_started",
            description="the discussion phase opens",
        ),
        say_to(to="postmortem_a", text="relay in seat order"),
        say_to(to=TEAM_A[1], text="psst"),
        SayTurn(text="done"),
    ]

    result = await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert [message.text for message in result.messages_on(channel_id="postmortem_a")] == [
        "relay in seat order"
    ]
    assert result.messages_on(channel_id=DIRECT_A1_A2) == []
    refused = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == TEAM_A[0]
        and event.tool_name == "send_message"
        and DIRECT_MESSAGES_CLOSED_IN_DISCUSSION in str(event.result)
    ]
    assert len(refused) == 1
