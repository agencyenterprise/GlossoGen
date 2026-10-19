"""Which parked member is released, and when, decided against a stand-in runtime.

The rule reads who is parked and on what, which a scripted run decides by
scheduling. Stating those states directly makes each case exact.
"""

from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.models.event import InjectionDelivered
from glossogen.models.mcp_responses import SendMessageResult
from glossogen.models.unread_channel_messages import UnreadChannelMessages
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import ParkedWait
from glossogen.scenarios.leaderboard_leak.ids import AGENT_IDS
from glossogen.scenarios.leaderboard_leak.scenario import LeaderboardLeakScenario
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import ONE_ROUND, build

MESSAGE = ParkedWait(wait_for=WaitFor.MESSAGE, deadline_s=None)
NEXT_ROUND = ParkedWait(wait_for=WaitFor.NEXT_ROUND, deadline_s=None)


class StandInRuntime:
    """Reports the parked waits a test states, and records every release."""

    def __init__(self, parked: dict[str, ParkedWait], log_path: Path) -> None:
        self.parked = parked
        self.released: list[tuple[str, str]] = []
        self._logger = EventLogger(log_path=log_path, event_bus=EventBus(max_queue_size=10))

    @property
    def event_logger(self) -> EventLogger:
        return self._logger

    @property
    def current_round(self) -> int:
        return 1

    async def publish_message(
        self, agent_id: str, channel_id: str, text: str, force: bool
    ) -> SendMessageResult:
        raise AssertionError(f"{agent_id} posted {text!r} to {channel_id} (force={force})")

    async def direct_channel_for(self, agent_id: str, recipient_agent_ids: list[str]) -> str:
        raise AssertionError(f"{agent_id} asked for a direct channel to {recipient_agent_ids}")

    def drain_unread_channel_messages(self, agent_id: str) -> list[UnreadChannelMessages]:
        _ = agent_id
        return []

    def parked_waits(self) -> dict[str, ParkedWait]:
        return dict(self.parked)

    def running_agent_ids(self) -> frozenset[str]:
        return frozenset(AGENT_IDS)

    def release_wait(self, agent_id: str, detail: str) -> bool:
        self.released.append((agent_id, detail))
        self.parked.pop(agent_id, None)
        return True


class RoundOne(NamedTuple):
    scenario: LeaderboardLeakScenario
    runtime: StandInRuntime


def briefed_round_one(preset_name: str, parked: dict[str, ParkedWait], tmp_path: Path) -> RoundOne:
    """A scenario in round 1 whose agents have all read the briefing."""
    scenario = build(preset_name=preset_name, overrides=ONE_ROUND)
    scenario.restore_state_from_events(
        events=[
            InjectionDelivered(round_number=1, agent_id=agent_id, text="briefing")
            for agent_id in AGENT_IDS
        ]
    )
    scenario.get_world().start_round(sheets=scenario.round_sheets(round_number=1))
    runtime = StandInRuntime(parked=parked, log_path=tmp_path / "log.jsonl")
    scenario.bind_runtime(runtime=runtime)
    return RoundOne(scenario=scenario, runtime=runtime)


def test_the_member_that_parks_last_is_the_one_released(tmp_path: Path) -> None:
    scenario, runtime = briefed_round_one(
        preset_name="knobs_default",
        parked={"amber_1": MESSAGE, "amber_2": MESSAGE},
        tmp_path=tmp_path,
    )

    scenario.on_agent_parked(agent_id="amber_2")

    assert runtime.released == [
        (
            "amber_2",
            "amber_1 is also waiting for a message, so nothing will arrive until one of you acts.",
        )
    ]


def test_a_member_whose_teammate_finished_is_released(tmp_path: Path) -> None:
    scenario, runtime = briefed_round_one(
        preset_name="knobs_default",
        parked={"amber_1": NEXT_ROUND, "amber_2": MESSAGE},
        tmp_path=tmp_path,
    )

    scenario.on_agent_parked(agent_id="amber_1")

    assert runtime.released == [("amber_2", "amber_1 has finished this round.")]


def test_a_member_waiting_while_its_teammate_acts_stays_parked(tmp_path: Path) -> None:
    scenario, runtime = briefed_round_one(
        preset_name="knobs_default", parked={"amber_2": MESSAGE}, tmp_path=tmp_path
    )

    scenario.on_agent_parked(agent_id="amber_2")

    assert runtime.released == []


@pytest.mark.parametrize(
    ("cobalt_parked", "released"),
    [
        ({}, False),
        ({"cobalt_1": MESSAGE}, False),
        ({"cobalt_1": MESSAGE, "cobalt_2": NEXT_ROUND}, True),
    ],
)
def test_under_chat_a_team_waiting_together_is_released_only_when_nobody_can_post(
    cobalt_parked: dict[str, ParkedWait], released: bool, tmp_path: Path
) -> None:
    """The lobby lets the other team wake a waiting member, so it must be parked too."""
    scenario, runtime = briefed_round_one(
        preset_name="knobs_chat_control",
        parked={"amber_1": MESSAGE, "amber_2": MESSAGE, **cobalt_parked},
        tmp_path=tmp_path,
    )

    scenario.on_agent_parked(agent_id="amber_2")

    assert bool(runtime.released) is released


def test_a_member_is_released_at_most_three_times_a_round(tmp_path: Path) -> None:
    scenario, runtime = briefed_round_one(preset_name="knobs_default", parked={}, tmp_path=tmp_path)

    for _ in range(5):
        runtime.parked.update({"amber_1": MESSAGE, "amber_2": MESSAGE})
        scenario.on_agent_parked(agent_id="amber_2")

    assert [agent_id for agent_id, _ in runtime.released] == [
        "amber_2",
        "amber_2",
        "amber_2",
        "amber_1",
        "amber_1",
    ]
