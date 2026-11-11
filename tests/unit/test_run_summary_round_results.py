"""A run summary tallies the rounds its scenario judged, per team, from the run's log."""

from pathlib import Path

import orjson

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    RoundResultRecorded,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.run_storage.run_discovery import build_summary
from glossogen.run_storage.run_summary_models import JudgedRound, RoundResultTally, RunSummary


def _result(round_number: int, success: bool, team_id: str | None) -> RoundResultRecorded:
    return RoundResultRecorded(
        round_number=round_number, success=success, team_id=team_id, reason="judged"
    )


def _judged(*verdicts: tuple[int, bool]) -> list[JudgedRound]:
    return [
        JudgedRound(round_number=round_number, succeeded=succeeded)
        for round_number, succeeded in verdicts
    ]


def _write_run(run_dir: Path, results: list[RoundResultRecorded], ended: bool) -> None:
    run_dir.mkdir(parents=True)
    events: list[SimulationEvent] = [
        SimulationStarted(
            round_number=0,
            run_id=run_dir.name,
            scenario_name="smoke",
            scenario_description="round results run",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={"round_count": 3},
        ),
        AgentRegistered(
            round_number=0,
            agent_id="first_agent",
            role_name="First Agent",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="",
            channel_ids=["link"],
            tool_names=["read_channel"],
            model_settings=AgentModelSettings(max_tokens=16384),
        ),
        *results,
    ]
    if ended:
        events.append(
            SimulationEnded(
                round_number=3,
                reason=RunStatus.SCENARIO_COMPLETE,
                total_messages=0,
                total_cost_usd=0.0,
            )
        )
    (run_dir / "smoke.jsonl").write_bytes(
        b"\n".join(event.model_dump_json().encode() for event in events) + b"\n"
    )


async def _summary(run_dir: Path) -> RunSummary:
    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    assert summary is not None
    return summary


async def test_a_single_team_run_tallies_its_judged_rounds(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        results=[
            _result(round_number=1, success=True, team_id=None),
            _result(round_number=2, success=False, team_id=None),
            _result(round_number=3, success=True, team_id=None),
        ],
        ended=True,
    )

    expected = [
        RoundResultTally(
            team_id=None,
            succeeded=2,
            judged=3,
            rounds=_judged((1, True), (2, False), (3, True)),
        )
    ]
    assert (await _summary(run_dir=run_dir)).round_results == expected
    # The second listing reads the cache the first one wrote.
    assert (await _summary(run_dir=run_dir)).round_results == expected


async def test_a_multi_team_run_tallies_each_team_by_id(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        results=[
            _result(round_number=1, success=True, team_id="team_b"),
            _result(round_number=1, success=False, team_id="team_a"),
            _result(round_number=2, success=True, team_id="team_b"),
        ],
        ended=False,
    )

    assert (await _summary(run_dir=run_dir)).round_results == [
        RoundResultTally(team_id="team_a", succeeded=0, judged=1, rounds=_judged((1, False))),
        RoundResultTally(
            team_id="team_b", succeeded=2, judged=2, rounds=_judged((1, True), (2, True))
        ),
    ]


async def test_a_round_judged_twice_counts_once_by_its_last_verdict(tmp_path: Path) -> None:
    # A run that crashed after judging round 2 resumes into round 2 and judges it again.
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        results=[
            _result(round_number=1, success=True, team_id=None),
            _result(round_number=2, success=False, team_id=None),
            _result(round_number=2, success=True, team_id=None),
            _result(round_number=3, success=False, team_id=None),
        ],
        ended=True,
    )

    assert (await _summary(run_dir=run_dir)).round_results == [
        RoundResultTally(
            team_id=None,
            succeeded=2,
            judged=3,
            rounds=_judged((1, True), (2, True), (3, False)),
        )
    ]


async def test_a_run_whose_scenario_judges_no_rounds_has_no_tally(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(run_dir=run_dir, results=[], ended=True)

    assert (await _summary(run_dir=run_dir)).round_results == []


async def test_a_cache_written_before_round_results_is_rescanned(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        results=[_result(round_number=1, success=True, team_id=None)],
        ended=True,
    )
    await _summary(run_dir=run_dir)
    cache_path = run_dir / "run_summary_cache.json"
    old_cache = orjson.loads(cache_path.read_bytes())
    del old_cache["round_results"]
    cache_path.write_bytes(orjson.dumps(old_cache))

    assert (await _summary(run_dir=run_dir)).round_results == [
        RoundResultTally(team_id=None, succeeded=1, judged=1, rounds=_judged((1, True)))
    ]
    assert "round_results" in orjson.loads(cache_path.read_bytes())


async def test_a_cache_written_before_judged_rounds_is_rescanned(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        results=[
            _result(round_number=1, success=False, team_id=None),
            _result(round_number=2, success=True, team_id=None),
        ],
        ended=True,
    )
    await _summary(run_dir=run_dir)
    cache_path = run_dir / "run_summary_cache.json"
    old_cache = orjson.loads(cache_path.read_bytes())
    for tally in old_cache["round_results"]:
        del tally["rounds"]
    cache_path.write_bytes(orjson.dumps(old_cache))

    assert (await _summary(run_dir=run_dir)).round_results == [
        RoundResultTally(team_id=None, succeeded=1, judged=2, rounds=_judged((1, False), (2, True)))
    ]
    rewritten = orjson.loads(cache_path.read_bytes())
    assert all("rounds" in tally for tally in rewritten["round_results"])
