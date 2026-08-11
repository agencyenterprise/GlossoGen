"""Run a simulation in-process and return its event log.

The MCP server listens on a port, agents connect over HTTP, tool calls reach the
runtime, the clock advances rounds and the logger writes JSONL. Only the LLM is
replaced, by a script saying what each agent does on each cycle.
"""

import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.autonomous_supervisor import AutonomousSupervisor
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.llm.token_counter import TokenCounter
from glossogen.runners.pydantic_ai_runner import PydanticAIRunner
from glossogen.scenario_protocol import SimulationScenario
from tests.fakes.scripted_agent_model import (
    SayTurn,
    ScriptedTurn,
    ToolTurn,
    build_scripted_model,
)

MAX_AGENT_TURNS = 30
RUN_ID = "smoke-test"

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


def free_port() -> int:
    """Reserve an unused localhost port for the MCP server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class SimulationResult:
    """A finished run: the events it wrote and where they were written."""

    events: list[dict[str, Any]]
    log_path: Path

    def of_type(self, *, event_type: str) -> list[dict[str, Any]]:
        """Return every event of one type, in the order logged."""
        return [e for e in self.events if e.get("event_type") == event_type]

    def types(self) -> list[str]:
        """Return the event types present, deduplicated, in first-seen order."""
        seen: list[str] = []
        for event in self.events:
            kind = str(event.get("event_type"))
            if kind not in seen:
                seen.append(kind)
        return seen

    def tool_calls(self, *, tool_name: str) -> list[dict[str, Any]]:
        """Return every invocation of one tool."""
        return [
            e
            for e in self.of_type(event_type="tool_call_invoked")
            if e.get("tool_name") == tool_name
        ]

    def failed_tool_calls(self) -> list[tuple[str, str]]:
        """Return (tool_name, result) for every tool call that reported an error.

        Tool failures are returned to the agent as text rather than raised, so a
        run completes happily with every call broken. Asserting invocation alone
        would not notice.
        """
        failures: list[tuple[str, str]] = []
        for event in self.of_type(event_type="tool_result_received"):
            result = str(event.get("result", ""))
            if result.startswith("Error executing tool") or "validation error" in result:
                failures.append((str(event.get("tool_name")), result[:160]))
        return failures

    def conflicted_sends(self) -> list[str]:
        """Return the results of sends rejected by optimistic concurrency.

        A conflicted send is not an error: the tool returns ``status="conflict"``
        and the message is never delivered. Nothing raises, so a test asserting
        only that ``send_message`` was invoked would not notice the message
        going nowhere.
        """
        out: list[str] = []
        for event in self.of_type(event_type="tool_result_received"):
            if event.get("tool_name") != "send_message":
                continue
            result = str(event.get("result", ""))
            if '"conflict"' in result or "conflict" in result[:60]:
                out.append(result[:160])
        return out

    def messages_on(self, *, channel_id: str) -> list[dict[str, Any]]:
        """Return the messages sent to one channel."""
        out: list[dict[str, Any]] = []
        for event in self.of_type(event_type="message_sent"):
            message: dict[str, Any] | None = event.get("message")
            if message is not None and message.get("channel_id") == channel_id:
                out.append(message)
        return out


async def run_simulation(
    *,
    scenario: SimulationScenario,
    scripts: Mapping[str, Sequence[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Run ``scenario`` to completion with each agent following its script.

    ``scripts`` maps agent_id to the turns that agent takes, one per cycle. An
    agent that runs out of script raises, so a test cannot quietly pass while an
    agent loops somewhere nobody described.
    """
    log_path = tmp_path / "smoke.jsonl"
    event_bus = EventBus(max_queue_size=10_000)
    event_logger = EventLogger(log_path=log_path, event_bus=event_bus)

    agent_configs = scenario.get_agents(
        default_model="scripted-model",
        default_provider="anthropic",
    )
    missing = {a.agent_id for a in agent_configs} - set(scripts)
    if missing:
        raise AssertionError(f"no script provided for {sorted(missing)}")

    # One scripted model per agent, chosen by the model name the runner asks for.
    # The runner passes agent_config.model straight through, so naming each
    # agent's model after its id is enough to route them apart.
    for config in agent_configs:
        config.model = f"scripted::{config.agent_id}"

    def scripted_model_for(model: str, provider: str) -> object:
        _ = provider
        agent_id = model.removeprefix("scripted::")
        return build_scripted_model(
            turns=list(scripts[agent_id]),
            # Out of script means "nothing left to do", not "broken": park on a
            # poll so the round can end on idle instead of the agent dying.
            when_exhausted=IDLE_CYCLE,
        )

    monkeypatch.setattr(
        "glossogen.runners.pydantic_ai_runner.build_pydantic_ai_model",
        scripted_model_for,
    )

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

    # A round cannot end before MIN_ROUND_DURATION_SECONDS even once every agent
    # is idle, so a round is not declared over before the agents have had a
    # chance to act. It stays above the idle-check interval, so idle detection
    # races the floor exactly as it does in a real run.
    monkeypatch.setattr("glossogen.runtime.game_clock.MIN_ROUND_DURATION_SECONDS", 0.05)
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
        mcp_server_port=free_port(),
        runner_factory=make_runner,
        resume_state=None,
        run_id=RUN_ID,
        provider="anthropic",
        log_path=log_path,
    )
    await supervisor.run()

    events: list[dict[str, Any]] = [
        orjson.loads(line) for line in log_path.read_bytes().splitlines() if line.strip()
    ]
    return SimulationResult(events=events, log_path=log_path)
