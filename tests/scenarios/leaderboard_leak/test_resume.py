"""A fork keeps the rounds it inherited; a log that stopped mid-round is refused."""

from pathlib import Path

import pytest

from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakRoundResolved,
    LeaderboardLeakRoundStarted,
)
from glossogen.scenarios.leaderboard_leak.ids import AGENT_IDS
from glossogen.testing.simulation_harness import SimulationResult, never_times_out
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import (
    GUESS,
    ONE_ROUND,
    build,
    correct_round,
    play,
)

pytestmark = pytest.mark.xdist_group("leaderboard_leak")


async def one_played_round(
    seed: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "seed": seed})
    return await play(
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


async def test_a_fork_keeps_the_logged_round_and_reports_it_in_the_next_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await one_played_round(seed=99, tmp_path=tmp_path, monkeypatch=monkeypatch)
    [logged] = result.of_type(event_type=LeaderboardLeakRoundStarted)

    fork = build(preset_name="knobs_default", overrides={"round_count": 3})
    fork.restore_state_from_events(events=list(result.events))

    assert [list(team.task_ids) for team in fork.round_sheets(round_number=1).teams] == [
        list(team.task_ids) for team in logged.teams
    ]
    later = (
        fork.round_sheets(round_number=2).entry_ids()
        | fork.round_sheets(round_number=3).entry_ids()
    )
    assert not later & fork.round_sheets(round_number=1).entry_ids()
    briefing = fork.get_injection(round_number=2, agent_id="amber_1")
    assert "Round 1: Team Amber scored 3 of 6 points. Total: 3 points." in briefing


async def test_a_log_that_stopped_mid_round_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await one_played_round(seed=42, tmp_path=tmp_path, monkeypatch=monkeypatch)
    cut = next(
        index
        for index, event in enumerate(result.events)
        if isinstance(event, LeaderboardLeakRoundResolved)
    )

    fork = build(preset_name="knobs_default", overrides={"round_count": 3})
    with pytest.raises(ValueError, match="cannot resume in the middle of a round"):
        fork.restore_state_from_events(events=list(result.events[:cut]))
