"""An ``EventGate`` orders one scripted agent's turn after another's within a round.

Left to the event loop, an agent whose script sends at once sends before one that
reads first. These gate the eager agent on the other's send and check the log
shows the gate's order, not the loop's.
"""

import asyncio
from pathlib import Path

import pytest

from glossogen.models.event import MessageSent
from glossogen.testing.scripted_agent import EventGate, GatedTurn, SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


def send(text: str) -> ToolTurn:
    """A send on the smoke scenario's one channel."""
    return ToolTurn(
        tool_name="send_message",
        args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
    )


def once_sent_by(agent_id: str) -> EventGate:
    """Holds a script until ``agent_id`` has sent a message."""

    def sent_by_agent(event: dict[str, object]) -> bool:
        if event["event_type"] != "message_sent":
            return False
        return MessageSent.model_validate(event).message.sender_agent_id == agent_id

    return EventGate(matches=sent_by_agent, description=f"{agent_id} sends a message")


async def run(
    scripts: dict[str, list[GatedTurn]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    """One smoke round, inside a timeout so a gate that never opens fails the test."""
    async with asyncio.timeout(60):
        return await run_simulation(
            scenario=SmokeScenario(
                knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
            ),
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )


def senders(result: SimulationResult) -> list[str]:
    return [event.message.sender_agent_id for event in result.of_type(event_type=MessageSent)]


async def test_a_gated_send_waits_for_the_send_it_is_gated_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ungated, the first agent's send would come first: it does not read before sending."""
    result = await run(
        scripts={
            FIRST_AGENT_ID: [
                once_sent_by(agent_id=SECOND_AGENT_ID),
                send(text="after you"),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [
                ToolTurn(tool_name="read_notifications", args={}),
                send(text="me first"),
                SayTurn(text="done"),
            ],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert senders(result=result) == [SECOND_AGENT_ID, FIRST_AGENT_ID]


async def test_a_gate_on_an_event_already_logged_opens_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_started = EventGate(
        matches=lambda event: event["event_type"] == "simulation_started",
        description="the simulation has started",
    )
    result = await run(
        scripts={
            FIRST_AGENT_ID: [
                ToolTurn(tool_name="read_notifications", args={}),
                already_started,
                send(text="hello"),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert senders(result=result) == [FIRST_AGENT_ID]
