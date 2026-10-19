"""Each round's view joins team messages and comments with both sheets."""

from pathlib import Path

import pytest

from glossogen.scenarios.leaderboard_leak.ids import AGENT_IDS, TEAM_AMBER, TEAM_COBALT
from glossogen.testing.simulation_harness import never_times_out
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import (
    GUESS,
    ONE_ROUND,
    build,
    correct_round,
    play,
)

pytestmark = pytest.mark.xdist_group("leaderboard_leak")


async def test_a_round_view_lists_every_comment_and_where_each_task_4_id_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    result = await play(
        scenario=scenario,
        scripts={
            agent_id: correct_round(
                scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
            )
            for agent_id in AGENT_IDS
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    [view] = scenario.build_communication_rounds(events=list(result.events))

    comments = [line for line in view.messages if line.channel_id.startswith("comment:")]
    assert len(comments) == 16
    assert {line.channel_id for line in comments} == {f"comment:task{task}" for task in range(1, 5)}
    sheets = scenario.round_sheets(round_number=1)
    for team_id in (TEAM_AMBER, TEAM_COBALT):
        bonus_id = sheets.team(team_id=team_id).task_ids[3]
        assert f"asks for {bonus_id} = {sheets.expected_answer(team_id=team_id, task=4)}" in (
            view.ground_truth_block
        )
