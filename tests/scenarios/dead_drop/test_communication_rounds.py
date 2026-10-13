"""The communication views: what each agent put where the other could read it."""

import pytest

from glossogen.scenarios.dead_drop.events import DeadDropFsRead
from glossogen.scenarios.dead_drop.ids import LINK_CHANNEL_ID
from tests.scenarios.dead_drop.dead_drop_wiring import wire

pytestmark = pytest.mark.xdist_group("dead_drop")


async def test_shared_writes_copies_and_moves_are_messages_and_private_ones_are_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ana", command="echo first > /tmp/a; echo second >> /tmp/a")
    await wired.run(agent_id="ben", command="cp ~/cases/round_01.txt /tmp/ben.txt")
    await wired.run(agent_id="ben", command="mv /tmp/ben.txt /tmp/b.txt; echo mine > ~/notes")

    [view] = wired.scenario.build_communication_rounds(events=wired.logger.events)

    await wired.run(agent_id="ben", command="cat /tmp/b.txt")
    case_file = wired.of_type(event_type=DeadDropFsRead)[-1].content
    assert [(line.sender_agent_id, line.channel_id, line.text) for line in view.messages] == [
        ("ana", "/tmp/a", "first\n"),
        ("ana", "/tmp/a", "second\n"),
        ("ben", "/tmp/ben.txt", case_file),
        ("ben", "/tmp/b.txt", case_file),
    ]
    assert LINK_CHANNEL_ID not in {line.channel_id for line in view.messages}
    for agent_id in ("ana", "ben"):
        assert f"{agent_id} holds: " in view.ground_truth_block
