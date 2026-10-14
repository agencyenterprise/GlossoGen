"""A dead_drop round started on a real runtime, with each agent's tools called directly.

The tests call the tool functions the runner would build, in an order the test
chooses, so who wrote before whom is the test's decision rather than the
scheduler's.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

import pytest

from glossogen.llm.token_counter import TokenCounter
from glossogen.models.event_base import EventBase
from glossogen.runners.agent_tools import build_agent_tools
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.scenarios.dead_drop.case_generation import RoundCase
from glossogen.scenarios.dead_drop.ids import AGENT_IDS
from glossogen.scenarios.dead_drop.scenario import DeadDropScenario
from glossogen.testing.scenario_runtime import build_scenario

EventT = TypeVar("EventT", bound=EventBase)


class RecordingLogger:
    """Keeps logged events in memory."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


class WordCounter(TokenCounter):
    """Counts words, so no provider is contacted."""

    async def _count_impl(self, text: str) -> int:
        return len(text.split())


def local_token_counter(provider: str, model: str) -> TokenCounter:
    """Stand in for the provider-backed counter."""
    _ = provider, model
    return WordCounter()


class Wired:
    """A started dead_drop run, with the tools each agent is offered."""

    def __init__(
        self, scenario: DeadDropScenario, logger: RecordingLogger, runtime: SimulationRuntime
    ) -> None:
        self.scenario = scenario
        self.logger = logger
        self.runtime = runtime

    def tools_of(self, agent_id: str) -> dict[str, Any]:
        """The tools the runner would offer ``agent_id``, by name."""
        tools = build_agent_tools(
            runtime=self.runtime, agent_id=agent_id, termination=RunTermination()
        )
        return {tool.name: tool.function for tool in tools}

    async def run(self, agent_id: str, command: str) -> str:
        """``agent_id`` runs one command line."""
        return await self.tools_of(agent_id=agent_id)["run_command"](command=command)

    async def submit(self, agent_id: str, answers: Mapping[str, str | int]) -> str:
        """``agent_id`` submits its answer."""
        return await self.tools_of(agent_id=agent_id)["submit_answer"](answers=answers)

    def case(self, round_number: int) -> RoundCase:
        """The generated case for ``round_number``."""
        return self.scenario._cases[round_number - 1]  # pyright: ignore[reportPrivateUsage]

    def of_type(self, event_type: type[EventT]) -> list[EventT]:
        """Every logged event of one type, in order."""
        return [event for event in self.logger.events if isinstance(event, event_type)]

    def read_briefings(self) -> None:
        """Both agents have read the current round's briefing.

        Stands in for the ``read_notifications`` call the runner makes; that path is
        covered by the round-loop tests.
        """
        for agent_id in AGENT_IDS:
            self.scenario._briefed_round[agent_id] = (  # pyright: ignore[reportPrivateUsage]
                self.runtime.current_round
            )

    async def finish_round(self, trigger: str, read_briefings: bool) -> None:
        """End the current round the way the game clock does, then open the next.

        ``read_briefings`` has both agents read the new round's briefing.
        """
        round_number = self.runtime.current_round
        await self.scenario.on_round_ended(round_number=round_number, trigger=trigger)
        self.runtime.set_current_round(round_number=round_number + 1)
        await self.scenario.on_round_advanced(round_number=round_number + 1)
        if read_briefings:
            self.read_briefings()


def bind(scenario: DeadDropScenario, logger: RecordingLogger) -> SimulationRuntime:
    """A runtime for ``scenario`` at round one, logging to ``logger``."""
    agents = scenario.get_agents(default_model="test", default_provider="self-hosted")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    world_context = WorldContext(
        agent_sessions=sessions, event_logger=logger  # type: ignore[arg-type]
    )
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,  # type: ignore[arg-type]
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=world_context,
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    runtime.set_current_round(round_number=1)
    return runtime


def build(preset_name: str, overrides: dict[str, Any]) -> DeadDropScenario:
    """The scenario from one of its presets plus ``overrides``."""
    scenario = build_scenario(
        scenario_name="dead_drop", preset_name=preset_name, overrides=overrides
    )
    assert isinstance(scenario, DeadDropScenario)
    return scenario


async def wire(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, overrides: dict[str, Any]
) -> Wired:
    """Round one of a dead_drop run, laid out and ready for tool calls."""
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter", local_token_counter
    )
    scenario = build(preset_name=preset_name, overrides=overrides)
    logger = RecordingLogger()
    runtime = bind(scenario=scenario, logger=logger)
    await scenario.on_round_advanced(round_number=1)
    wired = Wired(scenario=scenario, logger=logger, runtime=runtime)
    wired.read_briefings()
    return wired


def codebook_lines(case: RoundCase, agent_id: str) -> str:
    """``agent_id``'s codebook as ``KEY=VALUE`` lines, the way a test agent shares it."""
    return "\n".join(f"{key}={value}" for key, value in case.by_agent[agent_id].codebook.items())


def codebook_keys(cases: list[RoundCase]) -> set[str]:
    """Every key in the codebooks of ``cases``."""
    return {
        key
        for case in cases
        for agent_case in case.by_agent.values()
        for key in agent_case.codebook
    }
