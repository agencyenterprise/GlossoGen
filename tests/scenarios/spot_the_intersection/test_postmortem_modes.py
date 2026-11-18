"""Who may post in a discussion phase, to whom, and how many characters.

Played rounds check each rule through the ``send_message`` tool: a viewer who is
not the phase's author is refused, a viewer's partner is the first teammate it
messages, two sends made at once cannot both choose a partner, and a character
limit refuses the message that would go over it and reports what is left. The
author rotation, the pair channels and the knob rules are checked on the
scenario directly.
"""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.discussion_phase import DiscussionPhase
from glossogen.scenarios.spot_the_intersection.postmortem_modes import (
    not_the_author_refusal,
    over_limit_refusal,
    second_partner_refusal,
)
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import (
    EventGate,
    GatedTurn,
    ParallelToolTurn,
    SayTurn,
)
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    run_simulation,
)
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    answer_of,
    say_on,
    submit,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)

DISCUSSION_OPENS = EventGate(
    matches=lambda event: event["event_type"] == "postmortem_started",
    description="the discussion phase opens",
)


def message_from(agent_id: str) -> EventGate:
    """A gate that opens once ``agent_id`` has sent a message."""

    def matches(event: dict[str, object]) -> bool:
        if event["event_type"] != "message_sent":
            return False
        message = cast(dict[str, object], event["message"])
        return message["sender_agent_id"] == agent_id

    return EventGate(matches=matches, description=f"{agent_id} sends a message")


def discussion_scenario(overrides: dict[str, object]) -> SimulationScenario:
    """Team A alone against a simulated Team B, for one round and its discussion phase."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_simulated_opponent",
        overrides={"round_count": 1, "max_round_duration_seconds": ROUND_SECONDS, **overrides},
    )


async def play_discussion(
    scenario: SimulationScenario,
    discussion_turns: dict[str, list[GatedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Every viewer submits the answer; the ones named then play their turns in the discussion."""
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[GatedTurn]] = {agent: [submit(obj=answer)] for agent in TEAM_A}
    for agent, turns in discussion_turns.items():
        scripts[agent] = [submit(obj=answer), DISCUSSION_OPENS, *turns, SayTurn(text="done")]
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def send_results(result: SimulationResult, agent_id: str) -> list[dict[str, Any]]:
    """Every ``send_message`` result ``agent_id`` read, in order."""
    return [
        json.loads(event.result)
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == "send_message"
    ]


def texts_on(result: SimulationResult, channel_id: str) -> list[str]:
    """The texts sent on ``channel_id``, in order."""
    return [message.text for message in result.messages_on(channel_id=channel_id)]


async def test_only_the_author_posts_in_a_single_author_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = discussion_scenario(overrides={"postmortem_mode": "single_author"})

    result = await play_discussion(
        scenario=scenario,
        discussion_turns={
            TEAM_A[0]: [say_on(scenario=scenario, channel_id="postmortem_a", text="rows first")],
            TEAM_A[1]: [say_on(scenario=scenario, channel_id="postmortem_a", text="no, columns")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert texts_on(result=result, channel_id="postmortem_a") == ["rows first"]
    (refused,) = send_results(result=result, agent_id=TEAM_A[1])
    assert refused["status"] == "rejected"
    assert refused["detail"] == not_the_author_refusal(author_role_name="Viewer 1 (Team A)")


def test_the_author_turns_over_with_each_round() -> None:
    scenario = discussion_scenario(overrides={"postmortem_mode": "rotating_author"})

    authors: list[list[str]] = []
    for round_number in range(1, 6):
        scenario.on_postmortem_started(round_number=round_number)
        authors.append(
            [
                agent
                for agent in TEAM_A
                if scenario.validate_outgoing_message(agent_id=agent, channel_id="postmortem_a")
                is None
            ]
        )

    assert authors == [[TEAM_A[0]], [TEAM_A[1]], [TEAM_A[2]], [TEAM_A[3]], [TEAM_A[0]]]
    assert scenario.validate_outgoing_message(
        agent_id=TEAM_A[1], channel_id="postmortem_a"
    ) == not_the_author_refusal(author_role_name="Viewer 1 (Team A)")


def test_a_chosen_partner_run_gives_each_pair_of_teammates_a_channel() -> None:
    scenario = discussion_scenario(overrides={"postmortem_mode": "chosen_partner"})

    pairs = [
        "postmortem_a_1_2",
        "postmortem_a_1_3",
        "postmortem_a_1_4",
        "postmortem_a_2_3",
        "postmortem_a_2_4",
        "postmortem_a_3_4",
    ]
    assert [channel.channel_id for channel in scenario.get_channels()] == ["link_a", *pairs]
    viewer_1 = scenario.get_agents(default_model="m", default_provider="anthropic")[0]
    assert viewer_1.channel_ids == ["link_a", *pairs[:3]]
    assert '"discussion with Viewer 2 (Team A)" (channel_id: postmortem_a_1_2)' in (
        viewer_1.system_prompt
    )
    assert "channel_id: postmortem_a)" not in viewer_1.system_prompt


async def test_a_partner_is_the_first_teammate_a_viewer_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Viewer 4 messages viewer 1 first; viewer 1 still picks viewer 2, and then cannot answer 4."""
    scenario = discussion_scenario(overrides={"postmortem_mode": "chosen_partner"})

    result = await play_discussion(
        scenario=scenario,
        discussion_turns={
            TEAM_A[3]: [say_on(scenario=scenario, channel_id="postmortem_a_1_4", text="hi 1")],
            TEAM_A[0]: [
                message_from(agent_id=TEAM_A[3]),
                say_on(scenario=scenario, channel_id="postmortem_a_1_2", text="rows first"),
                say_on(scenario=scenario, channel_id="postmortem_a_1_4", text="hi 4"),
            ],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert texts_on(result=result, channel_id="postmortem_a_1_4") == ["hi 1"]
    assert texts_on(result=result, channel_id="postmortem_a_1_2") == ["rows first"]
    sent, refused = send_results(result=result, agent_id=TEAM_A[0])
    assert sent["status"] == "sent"
    assert refused["status"] == "rejected"
    assert refused["detail"] == second_partner_refusal(partner_role_name="Viewer 2 (Team A)")


async def test_two_sends_at_once_choose_one_partner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = discussion_scenario(overrides={"postmortem_mode": "chosen_partner"})

    result = await play_discussion(
        scenario=scenario,
        discussion_turns={
            TEAM_A[0]: [
                ParallelToolTurn(
                    calls=(
                        say_on(scenario=scenario, channel_id="postmortem_a_1_2", text="to 2"),
                        say_on(scenario=scenario, channel_id="postmortem_a_1_3", text="to 3"),
                    )
                )
            ]
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    delivered = texts_on(result=result, channel_id="postmortem_a_1_2") + texts_on(
        result=result, channel_id="postmortem_a_1_3"
    )
    assert len(delivered) == 1
    statuses = sorted(
        outcome["status"] for outcome in send_results(result=result, agent_id=TEAM_A[0])
    )
    assert statuses == ["rejected", "sent"]


async def test_a_character_limit_refuses_the_message_that_would_go_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = discussion_scenario(overrides={"postmortem_character_limit": 100})

    result = await play_discussion(
        scenario=scenario,
        discussion_turns={
            TEAM_A[0]: [
                say_on(scenario=scenario, channel_id="postmortem_a", text="a" * 60),
                say_on(scenario=scenario, channel_id="postmortem_a", text="b" * 50),
                say_on(scenario=scenario, channel_id="postmortem_a", text="c" * 40),
            ]
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert texts_on(result=result, channel_id="postmortem_a") == ["a" * 60, "c" * 40]
    outcomes = send_results(result=result, agent_id=TEAM_A[0])
    assert [outcome["status"] for outcome in outcomes] == ["sent", "rejected", "sent"]
    assert [outcome["discussion_characters_left"] for outcome in outcomes] == [40, 40, 0]
    assert outcomes[1]["detail"] == over_limit_refusal(characters=50, characters_left=40, limit=100)


def test_a_send_that_posted_nothing_gives_back_its_partner_and_characters() -> None:
    phase = DiscussionPhase(
        round_number=1,
        character_limit=100,
        partner_channels={"postmortem_a_1_2": (TEAM_A[0], TEAM_A[1])},
        role_names={TEAM_A[1]: "Viewer 2 (Team A)"},
    )

    claim = phase.claim(agent_id=TEAM_A[0], channel_id="postmortem_a_1_2", characters=70)
    phase.release(claim=claim)

    assert phase.characters_left(agent_id=TEAM_A[0]) == 100
    assert (
        phase.refusal_for(agent_id=TEAM_A[0], channel_id="postmortem_a_1_3", characters=100) is None
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"postmortem_enabled": False, "postmortem_mode": "chosen_partner"},
            "with postmortem_enabled=False there is no discussion phase",
        ),
        (
            {"postmortem_enabled": False, "postmortem_character_limit": 100},
            "with postmortem_enabled=False there is no discussion phase",
        ),
        ({"postmortem_character_limit": 0}, "postmortem_character_limit must be > 0"),
        (
            {"postmortem_mode": "chosen_partner", "messaging": "one_to_one"},
            "needs messaging='broadcast'",
        ),
    ],
)
def test_postmortem_knobs_that_cannot_apply_are_rejected(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        discussion_scenario(overrides=overrides)
