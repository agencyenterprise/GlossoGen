"""The communication views: what each agent put where the other could read it."""

import pytest

from glossogen.scenarios.dead_drop.events import DeadDropFsRead
from glossogen.scenarios.dead_drop.ids import LINK_CHANNEL_ID
from tests.scenarios.dead_drop.dead_drop_wiring import wire

pytestmark = pytest.mark.xdist_group("dead_drop")


async def test_text_put_in_the_partners_reach_is_a_message_and_a_shuffle_inside_it_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copy or move between two places the partner can read shows it nothing new."""
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides={})
    await wired.run(agent_id="ana", command="echo first > /tmp/a; echo second >> /tmp/a")
    await wired.run(agent_id="ben", command="cp ~/cases/round_01.txt /tmp/ben.txt")
    await wired.run(agent_id="ben", command="mv /tmp/ben.txt /tmp/b.txt; cp /tmp/a /tmp/a_copy")
    await wired.run(agent_id="ben", command="echo mine > ~/notes; mv ~/notes /tmp/notes")

    [view] = wired.scenario.build_communication_rounds(events=wired.logger.events)

    await wired.run(agent_id="ben", command="cat /tmp/b.txt")
    case_file = wired.of_type(event_type=DeadDropFsRead)[-1].content
    assert [(line.sender_agent_id, line.channel_id, line.text) for line in view.messages] == [
        ("ana", "/tmp/a", "first\n"),
        ("ana", "/tmp/a", "second\n"),
        ("ben", "/tmp/ben.txt", case_file),
        ("ben", "/tmp/notes", "mine\n"),
    ]
    assert LINK_CHANNEL_ID not in {line.channel_id for line in view.messages}
    for agent_id in ("ana", "ben"):
        assert f"{agent_id} holds: " in view.ground_truth_block
