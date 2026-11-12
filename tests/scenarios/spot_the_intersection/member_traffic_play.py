"""Scripted spot_the_intersection rounds for the metrics that split a team's count by member.

``play_relay_chain`` has Team A relay 10, 6 and 8 characters along A1 → A2 → A3
→ A4 over direct messages, then lock; A1 then messages A2 again, which costs
nothing. ``play_two_link_posts`` has A1 and A2 post 4 and 2 characters on Team
A's link in a broadcast run.
"""

from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.scenario_contract.measurement import Measurement
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.testing.scripted_agent import EventGate, GatedTurn, SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.spot_the_intersection.conftest import (
    TEAM_A,
    TEAM_B,
    answer_of,
    one_round_scenario,
    one_to_one_scenario,
    play,
    say_on,
    say_to,
    submit,
)


class PlayedRound(NamedTuple):
    """A played round and the scenario it was played on."""

    scenario: SimulationScenario
    result: SimulationResult


async def measure(metric: Metric, played: PlayedRound, tmp_path: Path) -> list[Measurement]:
    """``metric`` over the played round's log."""
    return await metric.compute(
        events=played.result.events,
        agent_configs=played.scenario.get_agents(default_model="m", default_provider="anthropic"),
        scenario=played.scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


def _team_a_locked(event: dict[str, object]) -> bool:
    """Whether ``event`` is the submission that completes Team A."""
    return (
        event["event_type"] == "intersection_submission_recorded"
        and event["team_id"] == "team_a"
        and event["members_submitted"] == len(TEAM_A)
    )


async def play_relay_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlayedRound:
    """Team A relays along a chain, locks, and A1 messages A2 once more after the lock."""
    scenario = one_to_one_scenario(overrides={})
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[GatedTurn]] = {
        TEAM_A[0]: [
            say_to(to=TEAM_A[1], text="x" * 10),
            submit(obj=answer),
            EventGate(matches=_team_a_locked, description="team A locks"),
            say_to(to=TEAM_A[1], text="after the lock"),
            SayTurn(text="done"),
        ],
        TEAM_A[1]: [say_to(to=TEAM_A[2], text="y" * 6), submit(obj=answer)],
        TEAM_A[2]: [say_to(to=TEAM_A[3], text="z" * 8), submit(obj=answer)],
        TEAM_A[3]: [submit(obj=answer)],
    }
    for agent_id in TEAM_B:
        scripts[agent_id] = [SayTurn(text="idle")]
    result = await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    sent = [message.text for message in result.messages_on(channel_id="dm:viewer_a_1+viewer_a_2")]
    assert sent == ["x" * 10, "after the lock"]
    return PlayedRound(scenario=scenario, result=result)


async def play_two_link_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlayedRound:
    """In a broadcast run, A1 and A2 post 4 and 2 characters on Team A's link."""
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        TEAM_A[0]: [
            say_on(scenario=scenario, channel_id="link_a", text="abcd"),
            submit(obj=answer),
        ],
        TEAM_A[1]: [
            say_on(scenario=scenario, channel_id="link_a", text="ef"),
            submit(obj=answer),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    return PlayedRound(scenario=scenario, result=result)
