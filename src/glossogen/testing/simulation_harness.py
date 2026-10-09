"""Run a simulation in-process and return its event log.

Tool calls reach the runtime, the clock advances rounds and the logger writes
JSONL. Only the LLM is replaced, by a script saying what each agent does on each
cycle.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import pytest
from pydantic import ValidationError
from pydantic_ai.models.function import FunctionModel

from glossogen.autonomous_supervisor import AutonomousSupervisor
from glossogen.evaluation.log_reader import load_events
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.llm.token_counter import TokenCounter
from glossogen.message_rewind import RewindState
from glossogen.models.event import (
    MessageSent,
    SimulationEvent,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase
from glossogen.models.mcp_responses import SendReceipt, SendStatus
from glossogen.models.message import SimulationMessage
from glossogen.resume_state_loader import load_resume_state
from glossogen.runners.pydantic_ai_runner import PydanticAIRunner
from glossogen.runtime.activity_notification import NewInfoNotification
from glossogen.runtime.communication_tools import SEND_MESSAGE_TOOL_NAME
from glossogen.runtime.game_clock import PhaseTimeoutCheck
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.scenario_event_types import run_event_parser
from glossogen.scenario_protocol import SimulationScenario
from glossogen.testing.scripted_agent import (
    PacedTurn,
    SayTurn,
    ScriptedTurn,
    ToolTurn,
    build_round_paced_model,
    build_scripted_model,
)

# Well above what any scripted run spends. A round-paced agent takes extra
# cycles draining wakes and other agents' sends between its own turns, and an
# agent that hits the cap stops silently, so its remaining rounds play without it.
MAX_AGENT_TURNS = 200
RUN_ID = "smoke-test"

EventT = TypeVar("EventT", bound=EventBase)

ScriptedModelBuilder = Callable[[str, Callable[[], int]], FunctionModel]
"""Build one agent's model from its agent id and a live current-round reader."""

# What an agent does once its script is spent: poll, then answer. The poll
# blocks until a notification or the round ends, so this idles rather than spins.
IDLE_CYCLE: tuple[ScriptedTurn, ...] = (
    ToolTurn(tool_name="read_notifications", args={}),
    SayTurn(text="idle"),
)


class _WordCountTokenCounter(TokenCounter):
    """Count tokens locally, so the suite never reaches a provider."""

    async def _count_impl(self, text: str) -> int:
        """Approximate a token count without leaving the process."""
        return len(text.split())


def send_status_of(result: str) -> SendStatus | None:
    """The ``status`` a recorded ``send_message`` result carries, or None when it is not one."""
    try:
        return SendReceipt.model_validate_json(result).status
    except ValidationError:
        return None


@dataclass(frozen=True)
class SimulationResult:
    """A finished run: the events it wrote, where, and the scenario that ran.

    ``events`` is the log parsed into typed events, the scenario's own included.
    The scenario is kept because some of what a run decides never reaches the
    event log. Whether the discussion phase was left open, for one, is world
    state that shuts the task channel without recording anything.
    """

    events: list[SimulationEvent]
    log_path: Path
    scenario: SimulationScenario

    def of_type(self, *, event_type: type[EventT]) -> list[EventT]:
        """Return every event of one type, in the order logged."""
        return [e for e in self.events if isinstance(e, event_type)]

    def first_index(self, *, event_type: type[EventBase], round_number: int | None) -> int:
        """Return the position of the first matching event in the log.

        ``round_number=None`` matches any round. Event-ordering assertions
        (an advance before its injections, a swap before its first read) hang
        on these positions.
        """
        return next(
            index
            for index, event in enumerate(self.events)
            if isinstance(event, event_type)
            and (round_number is None or event.round_number == round_number)
        )

    def tool_calls(self, *, tool_name: str) -> list[ToolCallInvoked]:
        """Return every invocation of one tool."""
        return [e for e in self.of_type(event_type=ToolCallInvoked) if e.tool_name == tool_name]

    def failed_tool_calls(self) -> list[tuple[str, str]]:
        """Return (tool_name, result) for every tool call that reported an error.

        Tool failures are returned to the agent as text rather than raised, so a
        run completes happily with every call broken. Asserting invocation alone
        would not notice.
        """
        failures: list[tuple[str, str]] = []
        for event in self.of_type(event_type=ToolResultReceived):
            result = event.result
            if result.startswith("Error executing tool") or "validation error" in result:
                failures.append((event.tool_name, result[:160]))
        return failures

    def conflicted_sends(self) -> list[str]:
        """Return the results of sends rejected by optimistic concurrency.

        A conflicted send is not an error: the tool returns ``SendStatus.CONFLICT``
        and the message is never delivered. Nothing raises, so a test asserting
        only that ``send_message`` was invoked would not notice the message
        going nowhere.
        """
        out: list[str] = []
        for event in self.of_type(event_type=ToolResultReceived):
            if event.tool_name != SEND_MESSAGE_TOOL_NAME:
                continue
            if send_status_of(result=event.result) == SendStatus.CONFLICT:
                out.append(event.result[:160])
        return out

    def messages_on(self, *, channel_id: str) -> list[SimulationMessage]:
        """Return the messages sent to one channel."""
        return [
            event.message
            for event in self.of_type(event_type=MessageSent)
            if event.message.channel_id == channel_id
        ]


def never_times_out(phase_age: float, limit: float) -> bool:
    """A phase is never over on time alone: it ends when the agents finish.

    Scripted agents take as long as the machine takes, so a limit that fires
    first truncates the run and changes what the scenario decided. Saying the
    limit never fires is what makes the outcome the same everywhere.
    """
    _ = phase_age, limit
    return False


def always_timed_out(phase_age: float, limit: float) -> bool:
    """Every phase is over on time alone, for runs that must exercise timeout.

    A run that passes this also has the idle check switched off: a scripted
    agent parks on ``read_notifications`` once its turns run out, and whether
    both agents are parked at the clock's next tick is a race, so idle must not
    be able to end a phase that the test wants ended by the clock.
    """
    _ = phase_age, limit
    return True


async def run_simulation(
    *,
    scenario: SimulationScenario,
    scripts: Mapping[str, Sequence[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_timed_out: PhaseTimeoutCheck,
) -> SimulationResult:
    """Run ``scenario`` to completion with each agent following its script.

    ``scripts`` maps agent_id to the turns that agent takes, one per cycle. An
    agent that runs out of script raises, so a test cannot quietly pass while an
    agent loops somewhere nobody described.

    ``phase_timed_out`` decides when a phase is over on time alone. Pass
    ``never_times_out`` for a run whose phases should end because the agents
    finished, and ``always_timed_out`` for one that has to exercise the
    timeout. Neither waits, which is what keeps the answer the same on a loaded
    machine as on an idle one.
    """

    def cycle_scripted_model(agent_id: str, current_round: Callable[[], int]) -> FunctionModel:
        _ = current_round
        return build_scripted_model(turns=list(scripts[agent_id]), when_exhausted=IDLE_CYCLE)

    return await _run_supervised(
        scenario=scenario,
        scripted_agent_ids=set(scripts),
        scripted_model_for=cycle_scripted_model,
        log_path=tmp_path / "smoke.jsonl",
        monkeypatch=monkeypatch,
        phase_timed_out=phase_timed_out,
        resume_state=None,
    )


async def run_round_paced_simulation(
    *,
    scenario: SimulationScenario,
    scripts: Mapping[str, Sequence[PacedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_timed_out: PhaseTimeoutCheck,
) -> SimulationResult:
    """Run ``scenario`` with round-gated scripts, waking every agent per round.

    Where a plain script's turn lands is the event loop's to choose: cycles run
    back to back, so an agent can spend a whole multi-round script inside round
    one. A ``RoundGate`` in the script instead holds the turns behind it until
    the simulation's own round counter reaches the gate, which is what makes
    "who said what in which round" a statement of the script rather than of
    scheduling.

    The harness makes one adjustment:

    - Rounds are an internal concept and production agents are never told one
      started. A gated agent must still observe the advance, and a scenario is
      free to deliver no injection to some agent in some round, so injection
      delivery is wrapped to first push a wake notification to every scripted
      agent. The wake is a queue entry only; nothing extra reaches the event
      log.
    """
    agent_ids = sorted(scripts)
    deliver = SimulationRuntime.deliver_round_injections

    async def wake_then_deliver(self: SimulationRuntime, round_number: int) -> None:
        for agent_id in agent_ids:
            self.resolve_session(agent_id=agent_id).push_notification(
                notification=NewInfoNotification(
                    text=f"Round {round_number} has begun.", kind="injection"
                )
            )
        await deliver(self, round_number=round_number)

    monkeypatch.setattr(SimulationRuntime, "deliver_round_injections", wake_then_deliver)

    def round_paced_model(agent_id: str, current_round: Callable[[], int]) -> FunctionModel:
        return build_round_paced_model(
            turns=list(scripts[agent_id]),
            when_exhausted=IDLE_CYCLE,
            current_round=current_round,
        )

    return await _run_supervised(
        scenario=scenario,
        scripted_agent_ids=set(scripts),
        scripted_model_for=round_paced_model,
        log_path=tmp_path / "smoke.jsonl",
        monkeypatch=monkeypatch,
        phase_timed_out=phase_timed_out,
        resume_state=None,
    )


async def resume_simulation(
    *,
    scenario: SimulationScenario,
    scripts: Mapping[str, Sequence[ScriptedTurn]],
    run_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_timed_out: PhaseTimeoutCheck,
) -> SimulationResult:
    """Resume the run in ``run_dir`` in-process, with each agent following its script.

    Mirrors the CLI's ``--resume`` path: loads the run's events, builds the
    rewind state through :func:`load_resume_state` (so a fork clone's manifest
    drives channel visibility and the advance-into-round decision), restores
    the scenario's world from the events, and appends new events to the same
    JSONL. The returned events cover the whole log, pre-boundary lines
    included.
    """
    log_path = run_dir / f"{scenario.name()}.jsonl"
    events = await load_events(log_path=log_path)
    resume_state = await load_resume_state(run_dir=run_dir, events=events)
    scenario.set_run_dir(run_dir=run_dir)
    scenario.restore_state_from_events(events=events)

    def cycle_scripted_model(agent_id: str, current_round: Callable[[], int]) -> FunctionModel:
        _ = current_round
        return build_scripted_model(turns=list(scripts[agent_id]), when_exhausted=IDLE_CYCLE)

    return await _run_supervised(
        scenario=scenario,
        scripted_agent_ids=set(scripts),
        scripted_model_for=cycle_scripted_model,
        log_path=log_path,
        monkeypatch=monkeypatch,
        phase_timed_out=phase_timed_out,
        resume_state=resume_state,
    )


async def _run_supervised(
    *,
    scenario: SimulationScenario,
    scripted_agent_ids: set[str],
    scripted_model_for: ScriptedModelBuilder,
    log_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_timed_out: PhaseTimeoutCheck,
    resume_state: RewindState | None,
) -> SimulationResult:
    """Wire the supervisor with scripted models and run it to completion.

    ``scripted_model_for`` builds one agent's model from its id and a live
    reader of the supervisor's current round; a cycle-scripted run ignores the
    reader, a round-paced one hands it to the gates.
    """
    event_bus = EventBus(max_queue_size=10_000)
    event_logger = EventLogger(log_path=log_path, event_bus=event_bus)

    agent_configs = scenario.get_agents(
        default_model="scripted-model",
        default_provider="anthropic",
    )
    missing = {a.agent_id for a in agent_configs} - scripted_agent_ids
    if missing:
        raise AssertionError(f"no script provided for {sorted(missing)}")

    # One scripted model per agent, chosen by the model name the runner asks for.
    # The runner passes agent_config.model straight through, so naming each
    # agent's model after its id is enough to route them apart.
    for config in agent_configs:
        config.model = f"scripted::{config.agent_id}"

    def idle_is_enough(round_age: float) -> bool:
        """The test's answer to "have the agents finished?": the idle check itself.

        An idle agent is blocked on ``read_notifications`` with an empty queue
        and nothing in flight, so it cannot act again until something wakes it.
        That is a state, not a guess, and needs no duration to confirm it. A run
        waits out a floor instead because a real model can be slow between
        turns; here nothing is, so the floor only adds a race between the clock
        and the agents. See "Tests and time" in CLAUDE.md.
        """
        _ = round_age
        return True

    def idle_never_ends(round_age: float) -> bool:
        """Only the clock ends a phase, for a run on ``always_timed_out``."""
        _ = round_age
        return False

    idle_round_may_end = idle_is_enough
    if phase_timed_out is always_timed_out:
        idle_round_may_end = idle_never_ends

    # Token counting otherwise calls the Anthropic count-tokens endpoint for
    # every message. It fails closed on a bad key and falls back to a word
    # count, so a run still completes. But the suite would be posting message
    # text to a provider, slowly and flakily, for a number nothing here checks.
    def local_token_counter(provider: str, model: str) -> TokenCounter:
        """Stand in for the provider-backed counter."""
        _ = provider
        _ = model
        return _WordCountTokenCounter()

    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter",
        local_token_counter,
    )

    monkeypatch.setattr("glossogen.runtime.game_clock.IDLE_CHECK_INTERVAL_SECONDS", 0.01)

    def make_runner() -> PydanticAIRunner:
        """Build a runner the same way the CLI does."""
        return PydanticAIRunner(
            max_turns=MAX_AGENT_TURNS,
            event_bus=event_bus,
            run_id=RUN_ID,
            scenario_name=scenario.name(),
            telemetry_enabled=False,
        )

    supervisor = AutonomousSupervisor(
        scenario=scenario,
        agent_configs=agent_configs,
        event_logger=event_logger,
        idle_round_may_end=idle_round_may_end,
        phase_timed_out=phase_timed_out,
        runner_factory=make_runner,
        resume_state=resume_state,
        run_id=RUN_ID,
        provider="anthropic",
        log_path=log_path,
    )

    def model_for_agent(model: str, provider: str) -> object:
        """Route the runner's model request to that agent's scripted model.

        Models are built while :meth:`AutonomousSupervisor.run` is launching
        runners, which is after it has built the runtime, so the round reader
        handed to the builder is live by the time anything calls it.
        """
        _ = provider
        agent_id = model.removeprefix("scripted::")
        return scripted_model_for(agent_id, supervisor.current_round)

    monkeypatch.setattr(
        "glossogen.runners.pydantic_ai_runner.build_pydantic_ai_model",
        model_for_agent,
    )

    await supervisor.run()

    parser = run_event_parser(scenario_cls=type(scenario))
    events = [
        parser.validate_json(line) for line in log_path.read_bytes().splitlines() if line.strip()
    ]
    return SimulationResult(events=events, log_path=log_path, scenario=scenario)
