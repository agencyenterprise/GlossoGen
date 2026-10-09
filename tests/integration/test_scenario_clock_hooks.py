"""The runner, wait registry and runtime tell the scenario what a clock needs to know.

A scenario that simulates time owns its clock through these hooks; the platform
schedules nothing itself except through ``schedule_wait_timeout``.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from glossogen.models.event import AgentResumed, WaitRegistered
from glossogen.runtime.wait_registry import DEFAULT_ANY_TIMEOUT_SECONDS
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

BRIEFING = ToolTurn(tool_name="read_notifications", args={})


class RecordingSmokeScenario(SmokeScenario):
    """Records each clock hook call, and fires an explicit wait timeout as soon as it is armed.

    The platform's default timeout on a plain poll never fires here, so idle
    agents stay parked and the round ends on idle.
    """

    def __init__(self, knobs: SmokeKnobs) -> None:
        super().__init__(knobs=knobs)
        self.calls: list[tuple[str, str]] = []
        self.timeouts: list[tuple[str, float]] = []

    def on_model_request_started(self, agent_id: str) -> None:
        self.calls.append(("request", agent_id))

    async def gate_model_response(
        self, agent_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        _ = input_tokens, output_tokens
        self.calls.append(("gate", agent_id))

    def schedule_wait_timeout(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        self.timeouts.append((agent_id, timeout_s))
        if timeout_s >= DEFAULT_ANY_TIMEOUT_SECONDS:
            return lambda: None
        handle = asyncio.get_running_loop().call_soon(fire)
        return handle.cancel

    def on_agent_parked(self, agent_id: str) -> None:
        self.calls.append(("parked", agent_id))

    def on_agent_resumed(self, agent_id: str) -> None:
        self.calls.append(("resumed", agent_id))

    def on_agent_retired(self, agent_id: str) -> None:
        self.calls.append(("retired", agent_id))

    def on_simulation_stopping(self) -> None:
        self.calls.append(("stopping", ""))


async def run_recording(
    scenario: RecordingSmokeScenario, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    return await run_simulation(
        scenario=scenario,
        scripts={
            FIRST_AGENT_ID: [
                BRIEFING,
                ToolTurn(
                    tool_name="read_notifications", args={"wait_for": "message", "timeout_s": 5.0}
                ),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [BRIEFING, SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def recording_smoke() -> RecordingSmokeScenario:
    return RecordingSmokeScenario(
        knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
    )


async def test_every_response_is_gated_after_its_request_was_announced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = recording_smoke()
    await run_recording(scenario=scenario, tmp_path=tmp_path, monkeypatch=monkeypatch)
    for agent_id in (FIRST_AGENT_ID, SECOND_AGENT_ID):
        sequence = [kind for kind, agent in scenario.calls if agent == agent_id]
        assert sequence[0] == "request"
        assert sequence[-1] == "retired"
        requests_so_far = 0
        gates_so_far = 0
        for kind in sequence:
            if kind == "request":
                requests_so_far += 1
            if kind == "gate":
                gates_so_far += 1
                assert gates_so_far <= requests_so_far


async def test_parking_and_resuming_alternate_and_the_run_stops_before_agents_retire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = recording_smoke()
    await run_recording(scenario=scenario, tmp_path=tmp_path, monkeypatch=monkeypatch)
    for agent_id in (FIRST_AGENT_ID, SECOND_AGENT_ID):
        transitions = [
            kind
            for kind, agent in scenario.calls
            if agent == agent_id and kind in {"parked", "resumed"}
        ]
        expected = ["parked", "resumed"] * (len(transitions) // 2)
        assert transitions[: len(expected)] == expected
        assert transitions[len(expected) :] in ([], ["parked"])
    kinds = [kind for kind, _ in scenario.calls]
    assert kinds.count("stopping") == 1
    assert kinds.index("stopping") < kinds.index("retired")


async def test_a_wait_timeout_is_armed_and_fired_by_the_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = recording_smoke()
    result = await run_recording(scenario=scenario, tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert (FIRST_AGENT_ID, 5.0) in scenario.timeouts
    wait = next(
        e
        for e in result.of_type(event_type=WaitRegistered)
        if e.agent_id == FIRST_AGENT_ID and e.wait_for == "message"
    )
    resume = next(e for e in result.of_type(event_type=AgentResumed) if e.wait_id == wait.wait_id)
    assert resume.wake_reasons == ["timeout"]


class SteppingClockSmokeScenario(RecordingSmokeScenario):
    """Its clock moves seven seconds every time anything reads it."""

    def __init__(self, knobs: SmokeKnobs) -> None:
        super().__init__(knobs=knobs)
        self._now = 0.0

    def clock_now_s(self) -> float:
        self._now += 7.0
        return self._now


async def test_waits_measure_their_duration_on_the_scenarios_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = SteppingClockSmokeScenario(
        knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
    )
    result = await run_recording(scenario=scenario, tmp_path=tmp_path, monkeypatch=monkeypatch)
    waited = [e.waited_seconds for e in result.of_type(event_type=AgentResumed)]
    assert waited
    # Both agents read the one stepping clock, so a wait can span several steps;
    # on the wall clock these would be small fractions, not whole steps.
    assert all(seconds > 0 and seconds % 7.0 == 0 for seconds in waited)
